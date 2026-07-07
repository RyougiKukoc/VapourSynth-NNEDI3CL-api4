from __future__ import annotations

import os
import platform
import shutil
import subprocess
import sys
import tempfile
import tomllib
import urllib.request
import zipfile
from pathlib import Path
from typing import Any

from hatchling.builders.hooks.plugin.interface import BuildHookInterface
from packaging import tags


ROOT = Path(__file__).resolve().parent
PLUGIN_NAME = "nnedi3cl"
DEFAULT_REPOSITORY = "RyougiKukoc/VapourSynth-NNEDI3CL-api4"
DEFAULT_PREBUILT_ASSET = "nnedi3cl-msys2-ucrt64.zip"
DEFAULT_PREBUILT_TAG_TEMPLATE = "v{version}-api4-msys2"


def _prepend_path_entries(env: dict[str, str], entries: list[Path]) -> None:
    parts = [str(entry) for entry in entries if entry.exists()]
    if not parts:
        return
    existing = env.get("PATH")
    if existing:
        env["PATH"] = os.pathsep.join(parts + [existing])
    else:
        env["PATH"] = os.pathsep.join(parts)


def _configure_windows_build_env(env: dict[str, str]) -> dict[str, str]:
    if sys.platform != "win32":
        return env

    msystem_prefix = env.get("MSYSTEM_PREFIX")
    path_entries: list[Path] = []
    python_scripts = Path(sys.executable).resolve().parent / "Scripts"
    if python_scripts.exists():
        path_entries.append(python_scripts)

    if msystem_prefix:
        prefix_path = Path(msystem_prefix)
        path_entries.append(prefix_path / "bin")
        path_entries.append(prefix_path.parent / "usr" / "bin")
    else:
        path_entries.extend(
            [
                Path(r"C:\msys64\ucrt64\bin"),
                Path(r"C:\msys64\usr\bin"),
            ]
        )

    _prepend_path_entries(env, path_entries)

    path_value = env.get("PATH")
    if "CC" not in env and shutil.which("gcc", path=path_value):
        env["CC"] = "gcc"
    if "CXX" not in env and shutil.which("g++", path=path_value):
        env["CXX"] = "g++"

    return env


def _run(cmd: list[str], *, env: dict[str, str]) -> None:
    subprocess.run(cmd, cwd=ROOT, check=True, env=env)


def _truthy(value: str | None) -> bool:
    return bool(value and value.strip().lower() not in {"", "0", "false", "no", "off"})


def _default_prebuilt_url(version: str) -> str:
    repository = os.environ.get("NNEDI3CL_PREBUILT_REPOSITORY") or os.environ.get("GITHUB_REPOSITORY") or DEFAULT_REPOSITORY
    tag = os.environ.get("NNEDI3CL_PREBUILT_TAG") or DEFAULT_PREBUILT_TAG_TEMPLATE.format(version=version)
    asset = os.environ.get("NNEDI3CL_PREBUILT_ASSET_NAME") or DEFAULT_PREBUILT_ASSET
    return f"https://github.com/{repository}/releases/download/{tag}/{asset}"


def _project_version() -> str:
    override = os.environ.get("NNEDI3CL_PREBUILT_VERSION")
    if override:
        return override
    with (ROOT / "pyproject.toml").open("rb") as handle:
        data = tomllib.load(handle)
    version = data.get("project", {}).get("version")
    if not isinstance(version, str) or not version.strip():
        raise RuntimeError("project.version missing from pyproject.toml")
    return version


def _prebuilt_source(version: str) -> tuple[str, bool]:
    explicit = os.environ.get("NNEDI3CL_PREBUILT_URL")
    if explicit:
        return explicit, True
    return _default_prebuilt_url(version), False


def _supports_prebuilt() -> bool:
    return sys.platform == "win32" and platform.machine().lower() in {"amd64", "x86_64"}


def _fetch_prebuilt_archive(source: str, destination: Path) -> None:
    candidate = Path(source)
    if candidate.exists():
        shutil.copy2(candidate, destination)
        return

    request = urllib.request.Request(source, headers={"User-Agent": "vapoursynth-nnedi3cl-build-hook"})
    with urllib.request.urlopen(request, timeout=60) as response, destination.open("wb") as handle:
        shutil.copyfileobj(response, handle)


def _stage_prebuilt_plugin(version: str, target_dir: Path) -> bool:
    if _truthy(os.environ.get("NNEDI3CL_FORCE_BUILD")):
        print("NNEDI3CL wheel build: skipping prebuilt asset because NNEDI3CL_FORCE_BUILD is set")
        return False
    if not _supports_prebuilt():
        print("NNEDI3CL wheel build: prebuilt release asset path only applies to Windows x86_64; falling back to local build")
        return False

    source, explicit = _prebuilt_source(version)
    asset_name = Path(source).name or DEFAULT_PREBUILT_ASSET
    try:
        with tempfile.TemporaryDirectory(prefix="nnedi3cl-prebuilt-") as temp_dir_text:
            temp_dir = Path(temp_dir_text)
            archive_path = temp_dir / asset_name
            _fetch_prebuilt_archive(source, archive_path)
            with zipfile.ZipFile(archive_path) as zf:
                package_members = [
                    name
                    for name in zf.namelist()
                    if name.replace("\\", "/").startswith(f"{PLUGIN_NAME}/") and not name.endswith("/")
                ]
                if not package_members:
                    raise FileNotFoundError(f"prebuilt archive does not contain a {PLUGIN_NAME}/ package directory")

                for member in package_members:
                    normalized = member.replace("\\", "/")
                    relative = normalized.split("/", 1)[1]
                    out_path = target_dir / relative
                    out_path.parent.mkdir(parents=True, exist_ok=True)
                    with zf.open(member) as src, out_path.open("wb") as dst:
                        shutil.copyfileobj(src, dst)

            required = [
                target_dir / "nnedi3cl.dll",
                target_dir / "nnedi3_weights.bin",
                target_dir / "OpenCL.dll",
            ]
            for path in required:
                if not path.exists():
                    raise FileNotFoundError(f"prebuilt archive did not provide {path.name}")
            manifest = target_dir / "manifest.vs"
            if not manifest.exists():
                manifest.write_text(
                    "[VapourSynth Manifest V1]\n"
                    f"{PLUGIN_NAME}\n",
                    encoding="ascii",
                    newline="\n",
                )
    except Exception as exc:
        if explicit:
            raise RuntimeError(f"failed to use explicit NNEDI3CL prebuilt asset {source!r}") from exc
        print(f"NNEDI3CL wheel build: prebuilt asset unavailable at {source}; falling back to local build ({exc})")
        return False

    print(f"NNEDI3CL wheel build: using prebuilt release asset {source}")
    return True


class CustomHook(BuildHookInterface[Any]):
    build_root = ROOT / "build-wheel-msys2"
    dist_dir = ROOT / "vapoursynth" / "plugins" / PLUGIN_NAME

    def initialize(self, version: str, build_data: dict[str, Any]) -> None:
        del version
        build_data["pure_python"] = False
        build_data["tag"] = f"py3-none-{next(tags.platform_tags())}"
        project_version = _project_version()

        shutil.rmtree(self.build_root, ignore_errors=True)
        shutil.rmtree(self.dist_dir.parent.parent, ignore_errors=True)
        self.build_root.mkdir(parents=True, exist_ok=True)
        self.dist_dir.mkdir(parents=True, exist_ok=True)

        if _stage_prebuilt_plugin(project_version, self.dist_dir):
            return

        env = _configure_windows_build_env(os.environ.copy())
        _run([sys.executable, "tools/ci_prepare_msys2.py"], env=env)
        _run(
            [
                sys.executable,
                "tools/ci_build_msys2.py",
                "--clean",
                "--build-dir",
                str(self.build_root / "build"),
                "--dist-dir",
                str(self.build_root / "dist"),
            ],
            env=env,
        )

        built_package = self.build_root / "dist" / PLUGIN_NAME
        if not built_package.is_dir():
            raise FileNotFoundError(f"missing built package directory: {built_package}")
        for path in sorted(built_package.rglob("*")):
            if not path.is_file():
                continue
            out_path = self.dist_dir / path.relative_to(built_package)
            out_path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(path, out_path)

    def finalize(self, version: str, build_data: dict[str, Any], artifact_path: str) -> None:
        del version, build_data, artifact_path
        shutil.rmtree(self.build_root, ignore_errors=True)
        shutil.rmtree(self.dist_dir.parent.parent, ignore_errors=True)
