from __future__ import annotations

import argparse
import os
import site
import sys
import sysconfig
from pathlib import Path


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description="Smoke-load a built NNEDI3CL artifact with VapourSynth.")
    parser.add_argument("--vapoursynth-root", help="VapourSynth portable root or extracted wheel root.")
    parser.add_argument("--artifact-dir", required=True)
    parser.add_argument("--autoload", action="store_true", help="Load through VAPOURSYNTH_EXTRA_PLUGIN_PATH instead of std.LoadPlugin.")
    args = parser.parse_args(argv)

    vs_root = Path(args.vapoursynth_root).resolve() if args.vapoursynth_root else None
    artifact_root = Path(args.artifact_dir).resolve()
    artifact = artifact_root
    if not (artifact / "nnedi3cl.dll").exists():
        for nested in [
            artifact / "nnedi3cl",
            artifact / "vapoursynth" / "plugins" / "nnedi3cl",
        ]:
            if (nested / "nnedi3cl.dll").exists():
                artifact = nested
                break
    plugin = artifact / "nnedi3cl.dll"
    weights = artifact / "nnedi3_weights.bin"
    opencl_runtime = artifact / "OpenCL.dll"
    for p in [
        plugin,
        weights,
        opencl_runtime,
    ]:
        if not p.exists():
            print(f"missing required path: {p}", file=sys.stderr)
            return 1

    dll_paths = [
        artifact,
        Path(sys.executable).resolve().parent,
        Path(sysconfig.get_paths().get("platlib", "")),
        Path(sysconfig.get_paths().get("purelib", "")),
        *(Path(p) for p in site.getsitepackages()),
    ]
    if vs_root is not None:
        dll_paths.extend(
            [
                vs_root,
                vs_root / "Lib" / "site-packages",
                vs_root / "vapoursynth",
            ]
        )
        if (vs_root / "vapoursynth").exists():
            sys.path.insert(0, str(vs_root))

    for path in dll_paths:
        if path.exists():
            os.add_dll_directory(str(path))

    if args.autoload:
        plugin_root = artifact.parent
        if artifact_root.joinpath("vapoursynth", "plugins").exists():
            plugin_root = artifact_root / "vapoursynth" / "plugins"
        elif artifact_root.joinpath("nnedi3cl").exists():
            plugin_root = artifact_root
        os.environ["VAPOURSYNTH_EXTRA_PLUGIN_PATH"] = str(plugin_root)

    try:
        import vapoursynth as vs
    except ImportError as exc:
        print(f"failed to import VapourSynth Python module: {exc}", file=sys.stderr)
        print("install VapourSynth into this Python or pass --vapoursynth-root pointing at an extracted wheel", file=sys.stderr)
        return 1

    try:
        env = vs.create_environment(flags=vs.DISABLE_AUTO_LOADING)
        core = env.get_core()
    except AttributeError:
        core = vs.core

    if not args.autoload:
        core.std.LoadPlugin(str(plugin))
    if not hasattr(core, "nnedi3cl") or not hasattr(core.nnedi3cl, "NNEDI3CL"):
        print("core.nnedi3cl.NNEDI3CL missing after LoadPlugin", file=sys.stderr)
        return 1
    print(core.nnedi3cl.NNEDI3CL)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
