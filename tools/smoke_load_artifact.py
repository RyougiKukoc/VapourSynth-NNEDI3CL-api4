from __future__ import annotations

import argparse
import os
import site
import sys
import sysconfig
from pathlib import Path


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description="Smoke-load a built NNEDI3CL artifact with VapourSynth.")
    parser.add_argument("--vapoursynth-root", required=True)
    parser.add_argument("--artifact-dir", required=True)
    args = parser.parse_args(argv)

    vs_root = Path(args.vapoursynth_root).resolve()
    artifact = Path(args.artifact_dir).resolve()
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

    for path in [
        artifact,
        vs_root,
        vs_root / "Lib" / "site-packages",
        Path(sys.executable).resolve().parent,
        Path(sysconfig.get_paths().get("platlib", "")),
        Path(sysconfig.get_paths().get("purelib", "")),
        *(Path(p) for p in site.getsitepackages()),
    ]:
        if path.exists():
            os.add_dll_directory(str(path))

    try:
        import vapoursynth as vs
    except ImportError as exc:
        print(f"failed to import VapourSynth Python module: {exc}", file=sys.stderr)
        print("run tools/ci_prepare_windows.py first so the R73 wheel is installed into this Python", file=sys.stderr)
        return 1

    core = vs.core
    try:
        env = vs.create_environment(flags=vs.DISABLE_AUTO_LOADING)
        core = env.get_core()
    except AttributeError:
        pass

    core.std.LoadPlugin(str(plugin))
    if not hasattr(core, "nnedi3cl") or not hasattr(core.nnedi3cl, "NNEDI3CL"):
        print("core.nnedi3cl.NNEDI3CL missing after LoadPlugin", file=sys.stderr)
        return 1
    print(core.nnedi3cl.NNEDI3CL)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
