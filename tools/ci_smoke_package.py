#!/usr/bin/env python3
"""Smoke-load a packaged NNEDI3CL plugin directory or zip."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
import tempfile
import zipfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
NO_DEVICE_MARKERS = (
    "no device",
    "no opencl",
    "cl_device_not_found",
    "device not found",
)


def resolve_artifact_dir(artifact_dir_arg: str | None, artifact_zip_arg: str | None) -> tuple[Path, Path | None]:
    if artifact_zip_arg:
        archive = (ROOT / artifact_zip_arg).resolve()
        if not archive.exists():
            raise FileNotFoundError(f"missing artifact zip: {archive}")
        temp_dir = Path(tempfile.mkdtemp(prefix="nnedi3cl-package-"))
        with zipfile.ZipFile(archive) as zf:
            zf.extractall(temp_dir)
        candidates = [path for path in temp_dir.iterdir() if path.is_dir()]
        if len(candidates) != 1:
            raise RuntimeError(f"expected one top-level package directory in {archive}, found {len(candidates)}")
        return candidates[0], temp_dir

    artifact_dir = (ROOT / (artifact_dir_arg or "dist/msys2-ucrt64/nnedi3cl")).resolve()
    return artifact_dir, None


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description="Smoke test a packaged NNEDI3CL plugin.")
    parser.add_argument("--artifact-dir", help="Packaged plugin directory.")
    parser.add_argument("--artifact-zip", help="Packaged plugin zip asset.")
    parser.add_argument("--exercise-filter", action="store_true", help="Try to render one frame if OpenCL is available.")
    parser.add_argument("--json", action="store_true", help="Emit JSON result.")
    args = parser.parse_args(argv)

    artifact_dir, temp_dir = resolve_artifact_dir(args.artifact_dir, args.artifact_zip)
    plugin = artifact_dir / "nnedi3cl.dll"
    manifest = artifact_dir / "manifest.vs"
    weights = artifact_dir / "nnedi3_weights.bin"
    opencl_runtime = artifact_dir / "OpenCL.dll"
    for path in [plugin, manifest, weights, opencl_runtime]:
        if not path.exists():
            raise FileNotFoundError(f"missing required file: {path}")

    add_dll_directory = getattr(os, "add_dll_directory", None)
    dll_handles = []
    if add_dll_directory is not None:
        dll_handles.append(add_dll_directory(str(artifact_dir)))

    import vapoursynth as vs  # pylint: disable=import-outside-toplevel

    try:
        env = vs.create_environment(flags=vs.DISABLE_AUTO_LOADING)
        core = env.get_core()
    except AttributeError:
        core = vs.core

    core.std.LoadPlugin(str(plugin))
    result = {
        "plugin": str(plugin),
        "manifest": str(manifest),
        "weights": str(weights),
        "namespace_loaded": hasattr(core, "nnedi3cl"),
        "callable_loaded": hasattr(getattr(core, "nnedi3cl", object()), "NNEDI3CL"),
    }

    if args.exercise_filter:
        clip = core.std.BlankClip(format=vs.YUV420P8, width=64, height=32, length=1)
        try:
            out = core.nnedi3cl.NNEDI3CL(clip, field=1, dh=True)
            frame = out.get_frame(0)
            stats = dict(core.std.PlaneStats(out).get_frame(0).props)
            result.update(
                {
                    "exercise_filter": True,
                    "exercise_skipped": False,
                    "width": frame.width,
                    "height": frame.height,
                    "format": frame.format.name,
                    "plane_stats_average": float(stats["PlaneStatsAverage"]),
                    "plane_stats_min": float(stats["PlaneStatsMin"]),
                    "plane_stats_max": float(stats["PlaneStatsMax"]),
                }
            )
        except Exception as exc:
            message = str(exc)
            if any(marker in message.lower() for marker in NO_DEVICE_MARKERS):
                result.update(
                    {
                        "exercise_filter": True,
                        "exercise_skipped": True,
                        "exercise_skip_reason": message,
                    }
                )
            else:
                raise

    try:
        if args.json:
            print(json.dumps(result, indent=2, sort_keys=True))
        else:
            for key, value in result.items():
                print(f"{key}={value}")
        return 0
    finally:
        for handle in dll_handles:
            handle.close()
        if temp_dir is not None:
            shutil.rmtree(temp_dir, ignore_errors=True)


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
