from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
import sysconfig
import tarfile
import urllib.request
import zipfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DEPS = ROOT / "_deps"

VAPOURSYNTH_VERSION = "R73"
VAPOURSYNTH_ZIP = f"VapourSynth64-Portable-{VAPOURSYNTH_VERSION}.zip"
VAPOURSYNTH_URL = f"https://github.com/vapoursynth/vapoursynth/releases/download/{VAPOURSYNTH_VERSION}/{VAPOURSYNTH_ZIP}"

BOOST_VERSION = "1.71.0"
BOOST_ARCHIVE = "boost_1_71_0.tar.gz"
BOOST_URL = f"https://archives.boost.io/release/{BOOST_VERSION}/source/{BOOST_ARCHIVE}"

OPENCL_TAG = "v2024.10.24"
OPENCL_HEADERS_URL = "https://github.com/KhronosGroup/OpenCL-Headers.git"
OPENCL_LOADER_URL = "https://github.com/KhronosGroup/OpenCL-ICD-Loader.git"


def run(cmd: list[str], cwd: Path | None = None) -> None:
    print("+ " + subprocess.list2cmdline(cmd), flush=True)
    subprocess.run(cmd, cwd=cwd, check=True)


def find_tool(name: str) -> str | None:
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


def require_tool(name: str) -> str:
    tool = find_tool(name)
    if tool is None:
        raise RuntimeError(f"{name} is not on PATH; install it before running this script.")
    return tool


def require_msvc() -> None:
    cl = shutil.which("cl")
    if cl is None:
        raise RuntimeError("MSVC cl.exe is not on PATH. Run from an x64 Developer Command Prompt or run the workflow after the MSVC setup step.")
    completed = subprocess.run(["cl"], stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, encoding="utf-8", errors="replace")
    output = completed.stdout
    if "Microsoft" not in output or "C/C++" not in output:
        raise RuntimeError(f"cl.exe on PATH does not look like MSVC: {cl}")
    print(output.splitlines()[0] if output.splitlines() else f"MSVC={cl}")


def download(url: str, out: Path) -> None:
    if out.exists():
        return
    out.parent.mkdir(parents=True, exist_ok=True)
    print(f"download {url} -> {out}", flush=True)
    with urllib.request.urlopen(url) as response, out.open("wb") as f:
        shutil.copyfileobj(response, f)


def extract_zip(zip_path: Path, out_dir: Path, marker: Path) -> None:
    if marker.exists():
        return
    if out_dir.exists():
        shutil.rmtree(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(zip_path) as zf:
        zf.extractall(out_dir)


def extract_tar(tar_path: Path, out_dir: Path, marker: Path) -> None:
    if marker.exists():
        return
    if out_dir.exists():
        shutil.rmtree(out_dir)
    tmp_dir = out_dir.parent / f"{out_dir.name}.tmp"
    if tmp_dir.exists():
        shutil.rmtree(tmp_dir)
    tmp_dir.mkdir(parents=True, exist_ok=True)
    with tarfile.open(tar_path, "r:gz") as tf:
        tf.extractall(tmp_dir)
    roots = [p for p in tmp_dir.iterdir() if p.is_dir()]
    if len(roots) != 1:
        raise RuntimeError(f"expected one root directory in {tar_path}, got {roots}")
    roots[0].rename(out_dir)
    shutil.rmtree(tmp_dir)


def clone_or_update(url: str, tag: str, path: Path, recursive: bool = False) -> None:
    if path.exists():
        return
    git = require_tool("git")
    cmd = [git, "clone", "--depth", "1", "--branch", tag]
    if recursive:
        cmd.append("--recursive")
    cmd.extend([url, str(path)])
    run(cmd)


def prepare_vapoursynth(deps: Path) -> Path:
    archive = deps / "downloads" / VAPOURSYNTH_ZIP
    out = deps / f"vapoursynth-portable-{VAPOURSYNTH_VERSION}"
    download(VAPOURSYNTH_URL, archive)
    extract_zip(archive, out, out / "sdk" / "include" / "vapoursynth" / "VapourSynth4.h")
    required = [
        out / "sdk" / "include" / "vapoursynth" / "VapourSynth4.h",
        out / "sdk" / "include" / "vapoursynth" / "VSHelper4.h",
        out / "sdk" / "lib64" / "VapourSynth.lib",
    ]
    for p in required:
        if not p.exists():
            raise FileNotFoundError(p)
    return out


def install_vapoursynth_wheel(vs_root: Path) -> None:
    wheel_dir = vs_root / "wheel"
    wheels = sorted(wheel_dir.glob("vapoursynth-73-*.whl"))
    if not wheels:
        raise FileNotFoundError(wheel_dir / "vapoursynth-73-*.whl")
    run(
        [
            sys.executable,
            "-m",
            "pip",
            "install",
            "--no-index",
            "--no-deps",
            "--force-reinstall",
            "--find-links",
            str(wheel_dir),
            "vapoursynth==73",
        ]
    )
    site_packages = Path(sysconfig.get_paths()["platlib"]).resolve()
    shutil.copy2(vs_root / "portable.vs", site_packages / "portable.vs")
    coreplugins_src = vs_root / "vs-coreplugins"
    coreplugins_dst = site_packages / "vs-coreplugins"
    if coreplugins_dst.exists():
        shutil.rmtree(coreplugins_dst)
    shutil.copytree(coreplugins_src, coreplugins_dst)


def prepare_boost(deps: Path) -> Path:
    out = deps / f"boost-{BOOST_VERSION}"
    archive = deps / "downloads" / BOOST_ARCHIVE
    download(BOOST_URL, archive)
    extract_tar(archive, out, out / "boost" / "compute" / "core.hpp")
    if not (out / "boost" / "compute" / "core.hpp").exists():
        raise FileNotFoundError(out / "boost" / "compute" / "core.hpp")
    return out


def prepare_opencl(deps: Path) -> tuple[Path, Path]:
    headers = deps / "OpenCL-Headers"
    loader = deps / "OpenCL-ICD-Loader"
    build = deps / "OpenCL-ICD-Loader-build"
    install = deps / "OpenCL-ICD-Loader-install"
    clone_or_update(OPENCL_HEADERS_URL, OPENCL_TAG, headers)
    clone_or_update(OPENCL_LOADER_URL, OPENCL_TAG, loader)
    if not (install / "lib" / "OpenCL.lib").exists() or not (install / "bin" / "OpenCL.dll").exists():
        require_msvc()
        cmake = require_tool("cmake")
        ninja = require_tool("ninja")
        for path in [build, install]:
            if path.exists():
                shutil.rmtree(path)
        run(
            [
                cmake,
                "-S",
                str(loader),
                "-B",
                str(build),
                "-G",
                "Ninja",
                f"-DCMAKE_MAKE_PROGRAM={ninja}",
                f"-DOPENCL_ICD_LOADER_HEADERS_DIR={headers}",
                "-DOPENCL_ICD_LOADER_BUILD_SHARED_LIBS=ON",
                "-DENABLE_OPENCL_LAYERS=OFF",
                "-DENABLE_OPENCL_LAYERINFO=OFF",
                "-DBUILD_TESTING=OFF",
                "-DCMAKE_BUILD_TYPE=Release",
                "-DCMAKE_INSTALL_LIBDIR=lib",
                f"-DCMAKE_INSTALL_PREFIX={install}",
            ]
        )
        run([cmake, "--build", str(build), "--config", "Release"])
        run([cmake, "--install", str(build), "--config", "Release"])
    for p in [install / "lib" / "OpenCL.lib", install / "bin" / "OpenCL.dll"]:
        if not p.exists():
            found = sorted(install.rglob("*OpenCL*")) + sorted(build.rglob("*OpenCL*"))
            details = "\n".join(str(path) for path in found)
            raise FileNotFoundError(f"{p}\nOpenCL files found:\n{details}")
    return headers, install


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description="Prepare Windows CI dependencies for NNEDI3CL.")
    parser.add_argument("--deps-dir", default=str(DEFAULT_DEPS), help="Dependency cache/work directory.")
    args = parser.parse_args(argv)

    deps = Path(args.deps_dir).resolve()
    deps.mkdir(parents=True, exist_ok=True)

    vs = prepare_vapoursynth(deps)
    install_vapoursynth_wheel(vs)
    boost = prepare_boost(deps)
    opencl_headers, opencl_loader = prepare_opencl(deps)

    print("Prepared dependencies:")
    print(f"VAPOURSYNTH_ROOT={vs}")
    print(f"BOOST_ROOT={boost}")
    print(f"OPENCL_HEADERS={opencl_headers}")
    print(f"OPENCL_LOADER_ROOT={opencl_loader}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
