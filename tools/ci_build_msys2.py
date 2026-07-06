from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DEPS = ROOT / "_deps"
DEFAULT_BUILD = ROOT / "build-ci-msys2"
DEFAULT_DIST = ROOT / "dist" / "msys2-ucrt64"

SYSTEM_DLLS = {
    "ADVAPI32.dll",
    "CFGMGR32.dll",
    "COMDLG32.dll",
    "GDI32.dll",
    "KERNEL32.dll",
    "OLEAUT32.dll",
    "SHELL32.dll",
    "USER32.dll",
    "VERSION.dll",
    "WINSPOOL.DRV",
    "WS2_32.dll",
    "bcrypt.dll",
    "msvcrt.dll",
    "ntdll.dll",
    "ole32.dll",
}


def run(cmd: list[str], cwd: Path | None = None, env: dict[str, str] | None = None) -> None:
    print("+ " + subprocess.list2cmdline(cmd), flush=True)
    subprocess.run(cmd, cwd=cwd, env=env, check=True)


def find_tool(name: str) -> str:
    found = shutil.which(name)
    if found:
        return found
    raise RuntimeError(f"{name} is not on PATH")


def path_for_meson(path: Path) -> str:
    return path.resolve().as_posix()


def dll_dependencies(objdump: str, dll: Path) -> list[str]:
    completed = subprocess.run(
        [objdump, "-p", str(dll)],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=True,
    )
    deps = []
    for line in completed.stdout.splitlines():
        line = line.strip()
        if line.startswith("DLL Name: "):
            deps.append(line.removeprefix("DLL Name: "))
    return deps


def collect_runtime_dlls(pkg_dir: Path, search_dirs: list[Path]) -> None:
    objdump = find_tool("objdump")
    queue = sorted(pkg_dir.glob("*.dll"))
    seen: set[str] = set()
    while queue:
        dll = queue.pop(0)
        key = dll.name.lower()
        if key in seen:
            continue
        seen.add(key)
        for dep in dll_dependencies(objdump, dll):
            dep_key = dep.lower()
            if dep in SYSTEM_DLLS or dep_key.startswith("api-ms-win-"):
                continue
            dst = pkg_dir / dep
            if dst.exists():
                if dep_key not in seen:
                    queue.append(dst)
                continue
            for search_dir in search_dirs:
                src = search_dir / dep
                if src.exists():
                    shutil.copy2(src, dst)
                    queue.append(dst)
                    break


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description="Build and package NNEDI3CL with MSYS2 UCRT64.")
    parser.add_argument("--deps-dir", default=str(DEFAULT_DEPS))
    parser.add_argument("--build-dir", default=str(DEFAULT_BUILD))
    parser.add_argument("--dist-dir", default=str(DEFAULT_DIST))
    parser.add_argument("--vapoursynth-wheel-root")
    parser.add_argument("--clean", action="store_true")
    args = parser.parse_args(argv)

    deps = Path(args.deps_dir).resolve()
    build_dir = Path(args.build_dir).resolve()
    dist_dir = Path(args.dist_dir).resolve()
    pkg_dir = dist_dir / "nnedi3cl"
    vs_root = Path(args.vapoursynth_wheel_root).resolve() if args.vapoursynth_wheel_root else deps / "vapoursynth-wheel-R77"
    vs_pkg = vs_root / "vapoursynth"
    for p in [
        vs_pkg / "include" / "VapourSynth4.h",
        vs_pkg / "include" / "VSHelper4.h",
        vs_pkg / "lib" / "pkgconfig" / "vapoursynth.pc",
    ]:
        if not p.exists():
            raise FileNotFoundError(p)

    meson = find_tool("meson")
    ninja = find_tool("ninja")
    opencl_runtime: Path | None = None
    found_opencl = shutil.which("OpenCL.dll")
    if found_opencl:
        opencl_runtime = Path(found_opencl)
    if opencl_runtime is None or not opencl_runtime.exists():
        opencl_runtime = None
        for path in os.environ.get("PATH", "").split(os.pathsep):
            if not path:
                continue
            candidate = Path(path) / "OpenCL.dll"
            if candidate.exists():
                opencl_runtime = candidate
                break
    if opencl_runtime is None or not opencl_runtime.exists():
        raise FileNotFoundError("OpenCL.dll")

    if args.clean and build_dir.exists():
        shutil.rmtree(build_dir)
    if args.clean and dist_dir.exists():
        shutil.rmtree(dist_dir)

    env = os.environ.copy()
    pc_paths = [
        str((vs_pkg / "lib" / "pkgconfig").resolve()),
        str((vs_pkg / "pkgconfig").resolve()),
    ]
    env["PKG_CONFIG_PATH"] = os.pathsep.join(pc_paths + [env.get("PKG_CONFIG_PATH", "")])

    setup_cmd = [
        meson,
        "setup",
        str(build_dir),
        str(ROOT),
        "--backend",
        "ninja",
        "--buildtype",
        "release",
        f"-Dvapoursynth_plugindir={path_for_meson(pkg_dir)}",
    ]
    if build_dir.exists():
        setup_cmd.insert(2, "--reconfigure")
    run(setup_cmd, cwd=ROOT, env=env)
    run([ninja, "-C", str(build_dir), "-v"], cwd=ROOT, env=env)

    pkg_dir.mkdir(parents=True, exist_ok=True)
    dll = build_dir / "libnnedi3cl.dll"
    if not dll.exists():
        dll = build_dir / "nnedi3cl.dll"
    weights = ROOT / "NNEDI3CL" / "nnedi3_weights.bin"
    for p in [dll, weights]:
        if not p.exists():
            raise FileNotFoundError(p)
    shutil.copy2(dll, pkg_dir / "nnedi3cl.dll")
    shutil.copy2(weights, pkg_dir / "nnedi3_weights.bin")
    shutil.copy2(opencl_runtime, pkg_dir / "OpenCL.dll")
    (pkg_dir / "manifest.vs").write_text("[VapourSynth Manifest V1]\nnnedi3cl\n", encoding="ascii", newline="\n")

    search_dirs = [Path(p) for p in os.environ.get("PATH", "").split(os.pathsep) if p]
    collect_runtime_dlls(pkg_dir, search_dirs)

    print(f"artifact_dir={dist_dir}")
    for p in sorted(pkg_dir.iterdir()):
        print(p)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
