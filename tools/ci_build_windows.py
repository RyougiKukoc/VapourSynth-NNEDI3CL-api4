from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DEPS = ROOT / "_deps"
DEFAULT_BUILD = ROOT / "build-ci-windows"
DEFAULT_DIST = ROOT / "dist" / "windows-x64"


def find_tool(name: str, explicit: str | None = None) -> str | None:
    if explicit:
        return str(Path(explicit).resolve())
    script = Path(sys.executable).resolve().parent / "Scripts" / name
    if script.exists():
        return str(script)
    exe = Path(sys.executable).resolve().parent / "Scripts" / f"{name}.exe"
    if exe.exists():
        return str(exe)
    found = shutil.which(name)
    if found:
        return found
    return None


def run(cmd: list[str], cwd: Path | None = None) -> None:
    print("+ " + subprocess.list2cmdline(cmd), flush=True)
    subprocess.run(cmd, cwd=cwd, check=True)


def path_for_meson(path: Path) -> str:
    return path.resolve().as_posix()


def write_native_file(path: Path, ninja: Path | None = None) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = ["[binaries]", "cpp = 'cl'"]
    if ninja is not None:
        lines.append(f"ninja = {path_for_meson(ninja)!r}")
    lines.append("")
    path.write_text("\n".join(lines), encoding="utf-8", newline="\n")
    return path


def require_msvc() -> None:
    cl = shutil.which("cl")
    if cl is None:
        raise RuntimeError("MSVC cl.exe is not on PATH. Run from an x64 Developer Command Prompt or use the GitHub Actions MSVC setup step.")
    completed = subprocess.run(["cl"], stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, encoding="utf-8", errors="replace")
    output = completed.stdout
    if "Microsoft" not in output or "C/C++" not in output:
        raise RuntimeError(f"cl.exe on PATH does not look like MSVC: {cl}")
    print(output.splitlines()[0] if output.splitlines() else f"MSVC={cl}")


def find_opencl_libdir(opencl_root: Path, explicit: str | None = None) -> Path:
    if explicit:
        libdir = Path(explicit).resolve()
        if not (libdir / "OpenCL.lib").exists():
            raise FileNotFoundError(libdir / "OpenCL.lib")
        return libdir
    for candidate in [
        opencl_root / "lib",
        opencl_root / "lib64",
        opencl_root / "lib" / "Release",
        opencl_root / "Release",
    ]:
        if (candidate / "OpenCL.lib").exists():
            return candidate
    matches = sorted(opencl_root.rglob("OpenCL.lib"))
    if matches:
        return matches[0].parent
    raise FileNotFoundError(opencl_root / "**" / "OpenCL.lib")


def find_opencl_runtime(opencl_root: Path) -> Path | None:
    for candidate in [
        opencl_root / "bin" / "OpenCL.dll",
        opencl_root / "lib" / "OpenCL.dll",
        opencl_root / "OpenCL.dll",
    ]:
        if candidate.exists():
            return candidate
    matches = sorted(opencl_root.rglob("OpenCL.dll"))
    return matches[0] if matches else None


def find_vapoursynth_root(deps: Path, explicit: str | None) -> Path:
    if explicit:
        root = Path(explicit).resolve()
    else:
        matches = sorted(deps.glob("vapoursynth-portable-R*"))
        if not matches:
            raise FileNotFoundError("missing VapourSynth portable tree; run tools/ci_prepare_windows.py first")
        root = matches[-1]
    for p in [
        root / "sdk" / "include" / "vapoursynth" / "VapourSynth4.h",
        root / "sdk" / "include" / "vapoursynth" / "VSHelper4.h",
        root / "sdk" / "lib64" / "VapourSynth.lib",
    ]:
        if not p.exists():
            raise FileNotFoundError(p)
    return root


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description="Build NNEDI3CL on Windows using prepared dependencies.")
    parser.add_argument("--deps-dir", default=str(DEFAULT_DEPS))
    parser.add_argument("--build-dir", default=str(DEFAULT_BUILD))
    parser.add_argument("--dist-dir", default=str(DEFAULT_DIST))
    parser.add_argument("--vapoursynth-root")
    parser.add_argument("--boost-root")
    parser.add_argument("--opencl-headers")
    parser.add_argument("--opencl-root")
    parser.add_argument("--opencl-libdir")
    parser.add_argument("--meson")
    parser.add_argument("--clean", action="store_true")
    args = parser.parse_args(argv)

    deps = Path(args.deps_dir).resolve()
    build_dir = Path(args.build_dir).resolve()
    dist_dir = Path(args.dist_dir).resolve()

    vapoursynth_root = find_vapoursynth_root(deps, args.vapoursynth_root)
    boost_root = Path(args.boost_root).resolve() if args.boost_root else deps / "boost-1.71.0"
    opencl_root = Path(args.opencl_root).resolve() if args.opencl_root else deps / "OpenCL-ICD-Loader-install"
    opencl_headers = Path(args.opencl_headers).resolve() if args.opencl_headers else deps / "OpenCL-Headers"
    opencl_libdir = find_opencl_libdir(opencl_root, args.opencl_libdir)

    for p in [
        boost_root / "boost" / "compute" / "core.hpp",
        opencl_headers / "CL" / "opencl.h",
        opencl_libdir / "OpenCL.lib",
    ]:
        if not p.exists():
            raise FileNotFoundError(p)

    require_msvc()

    if args.clean and build_dir.exists():
        shutil.rmtree(build_dir)
    meson = find_tool("meson", args.meson)
    if meson is None:
        raise RuntimeError("meson is not on PATH; install it with `python -m pip install meson ninja`")
    ninja = find_tool("ninja")
    if ninja is None:
        raise RuntimeError("ninja is not on PATH; install it with `python -m pip install meson ninja`")

    native = write_native_file(build_dir.parent / "native-windows.ini", Path(ninja))

    setup_cmd = [
        meson,
        "setup",
        str(build_dir),
        str(ROOT),
        "--native-file",
        str(native),
        "--backend",
        "ninja",
        "--buildtype",
        "release",
        f"-Dvapoursynth_incdir={path_for_meson(vapoursynth_root / 'sdk' / 'include' / 'vapoursynth')}",
        f"-Dvapoursynth_plugindir={path_for_meson(dist_dir)}",
        f"-Dboost_root={path_for_meson(boost_root)}",
        f"-Dopencl_incdir={path_for_meson(opencl_headers)}",
        f"-Dopencl_libdir={path_for_meson(opencl_libdir)}",
    ]
    if build_dir.exists():
        setup_cmd.insert(2, "--reconfigure")
    run(setup_cmd, cwd=ROOT)
    run([ninja, "-C", str(build_dir), "-v"], cwd=ROOT)

    dist_dir.mkdir(parents=True, exist_ok=True)
    dll = build_dir / "nnedi3cl.dll"
    weights = ROOT / "NNEDI3CL" / "nnedi3_weights.bin"
    for p in [dll, weights]:
        if not p.exists():
            raise FileNotFoundError(p)
    shutil.copy2(dll, dist_dir / "nnedi3cl.dll")
    shutil.copy2(weights, dist_dir / "nnedi3_weights.bin")
    opencl_runtime = find_opencl_runtime(opencl_root)
    if opencl_runtime is not None:
        shutil.copy2(opencl_runtime, dist_dir / "OpenCL.dll")
    print(f"artifact_dir={dist_dir}")
    for p in sorted(dist_dir.iterdir()):
        print(p)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
