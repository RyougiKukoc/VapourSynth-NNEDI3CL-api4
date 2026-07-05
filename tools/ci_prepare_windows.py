from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
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
    cmd = ["git", "clone", "--depth", "1", "--branch", tag]
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
    if not (install / "lib" / "OpenCL.lib").exists():
        run(
            [
                "cmake",
                "-S",
                str(loader),
                "-B",
                str(build),
                "-G",
                "Ninja",
                f"-DOPENCL_ICD_LOADER_HEADERS_DIR={headers}",
                "-DOPENCL_ICD_LOADER_BUILD_SHARED_LIBS=ON",
                "-DENABLE_OPENCL_LAYERS=OFF",
                "-DENABLE_OPENCL_LAYERINFO=OFF",
                "-DBUILD_TESTING=OFF",
                f"-DCMAKE_INSTALL_PREFIX={install}",
            ]
        )
        run(["cmake", "--build", str(build), "--config", "Release"])
        run(["cmake", "--install", str(build), "--config", "Release"])
    return headers, install


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description="Prepare Windows CI dependencies for NNEDI3CL.")
    parser.add_argument("--deps-dir", default=str(DEFAULT_DEPS), help="Dependency cache/work directory.")
    args = parser.parse_args(argv)

    deps = Path(args.deps_dir).resolve()
    deps.mkdir(parents=True, exist_ok=True)

    vs = prepare_vapoursynth(deps)
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
