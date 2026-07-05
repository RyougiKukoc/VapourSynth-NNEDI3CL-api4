from __future__ import annotations

import argparse
import os
import sys
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
    vapoursynth_dll = vs_root / "VapourSynth.dll"
    if not vapoursynth_dll.exists():
        vapoursynth_dll = vs_root / "Lib" / "site-packages" / "vapoursynth.dll"
    for p in [
        vapoursynth_dll,
        vs_root / "Lib" / "site-packages" / "vapoursynth.pyd",
        plugin,
        weights,
    ]:
        if not p.exists():
            print(f"missing required path: {p}", file=sys.stderr)
            return 1

    os.add_dll_directory(str(vs_root))
    os.add_dll_directory(str(vs_root / "Lib" / "site-packages"))
    os.add_dll_directory(str(artifact))

    import vapoursynth as vs

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
