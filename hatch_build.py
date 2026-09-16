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
WINDOWS_PREBUILT_ASSET = "nnedi3cl-msys2-ucrt64.zip"
LINUX_PREBUILT_ASSET = "nnedi3cl-linux-x86_64.zip"


def _prepend_path_entries(env: dict[str, str], entries: list[Path]) -> None:
    parts = [str(entry) for entry in entries if entry.exists()]
    if not parts:
        return
    existing = env.get("PATH")
    env["PATH"] = os.pathsep.join(parts + ([existing] if existing else []))


def _prepend_pkg_config_path(env: dict[str, str], entry: Path) -> None:
    if not entry.is_dir():
        return
    existing = env.get("PKG_CONFIG_PATH")
    env["PKG_CONFIG_PATH"] = os.pathsep.join([str(entry)] + ([existing] if existing else []))


def _candidate_msys2_prefixes(env: dict[str, str]) -> list[Path]:
    prefixes: list[Path] = []
    msystem_prefix = env.get("MSYSTEM_PREFIX")
    if msystem_prefix:
        prefixes.append(Path(msystem_prefix))
    prefixes.extend([Path(r"C:\msys64\ucrt64"), Path(r"C:\msys64\mingw64")])
    seen: set[str] = set()
    unique: list[Path] = []
    for prefix in prefixes:
        key = str(prefix).lower()
        if key not in seen:
            seen.add(key)
            unique.append(prefix)
    return unique


def _configure_windows_build_env(env: dict[str, str]) -> dict[str, str]:
    vs_wheel_dir = ROOT / "_deps" / "vapoursynth-wheel-R77"
    path_entries = [Path(sys.executable).resolve().parent / "Scripts", vs_wheel_dir]
    msys2_prefixes = _candidate_msys2_prefixes(env)
    for prefix in msys2_prefixes:
        path_entries.extend([prefix / "bin", prefix.parent / "usr" / "bin"])
    _prepend_path_entries(env, path_entries)

    if "PKG_CONFIG" not in env:
        shim = vs_wheel_dir / "pkg-config.cmd"
        if shim.exists():
            env["PKG_CONFIG"] = str(shim)
        else:
            for prefix in msys2_prefixes:
                for candidate in (
                    prefix.parent / "usr" / "bin" / "pkg-config.exe",
                    prefix.parent / "usr" / "bin" / "pkgconf.exe",
                    prefix / "bin" / "pkg-config.exe",
                    prefix / "bin" / "pkgconf.exe",
                ):
                    if candidate.exists():
                        env["PKG_CONFIG"] = str(candidate)
                        break
                if "PKG_CONFIG" in env:
                    break
    _prepend_pkg_config_path(env, vs_wheel_dir / "vapoursynth" / "lib" / "pkgconfig")

    if "CC" not in env or "CXX" not in env:
        for prefix in msys2_prefixes:
            gcc = prefix / "bin" / "gcc.exe"
            gxx = prefix / "bin" / "g++.exe"
            if gcc.exists() and "CC" not in env:
                env["CC"] = str(gcc)
            if gxx.exists() and "CXX" not in env:
                env["CXX"] = str(gxx)
            if "CC" in env and "CXX" in env:
                break
    path_value = env.get("PATH")
    if "CC" not in env and shutil.which("gcc", path=path_value):
        env["CC"] = "gcc"
    if "CXX" not in env and shutil.which("g++", path=path_value):
        env["CXX"] = "g++"
    return env


def _configure_build_env(env: dict[str, str]) -> dict[str, str]:
    if sys.platform == "win32":
        return _configure_windows_build_env(env)

    try:
        import vapoursynth
    except ImportError:
        return env
    _prepend_pkg_config_path(env, Path(vapoursynth.__file__).resolve().parent / "pkgconfig")
    return env


def _meson_command() -> list[str]:
    meson = shutil.which("meson")
    if meson:
        return [meson]
    for module in ("mesonbuild", "mesonbuild.mesonmain"):
        command = [sys.executable, "-m", module]
        if subprocess.run(command + ["--version"], cwd=ROOT, capture_output=True).returncode == 0:
            return command
    raise FileNotFoundError("Meson is unavailable; install meson in the build environment")


def _run(command: list[str], *, env: dict[str, str]) -> None:
    subprocess.run(command, cwd=ROOT, check=True, env=env)


def _truthy(value: str | None) -> bool:
    return bool(value and value.strip().lower() not in {"", "0", "false", "no", "off"})


def _architecture_supported() -> bool:
    return platform.machine().lower() in {"amd64", "x86_64"}


def _prebuilt_asset_name() -> str:
    if sys.platform == "linux" and _architecture_supported():
        return LINUX_PREBUILT_ASSET
    return WINDOWS_PREBUILT_ASSET


def _plugin_filename() -> str:
    if sys.platform == "win32":
        return f"{PLUGIN_NAME}.dll"
    if sys.platform == "darwin":
        return f"{PLUGIN_NAME}.dylib"
    return f"{PLUGIN_NAME}.so"


def _default_prebuilt_url(version: str) -> str:
    repository = os.environ.get("NNEDI3CL_PREBUILT_REPOSITORY") or os.environ.get("GITHUB_REPOSITORY") or DEFAULT_REPOSITORY
    tag = os.environ.get("NNEDI3CL_PREBUILT_TAG") or f"v{version}"
    asset = os.environ.get("NNEDI3CL_PREBUILT_ASSET_NAME") or _prebuilt_asset_name()
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
    return sys.platform in {"win32", "linux"} and _architecture_supported()


def _fetch_prebuilt_archive(source: str, destination: Path) -> None:
    candidate = Path(source)
    if candidate.exists():
        shutil.copy2(candidate, destination)
        return
    request = urllib.request.Request(source, headers={"User-Agent": "vapoursynth-nnedi3cl-build-hook"})
    with urllib.request.urlopen(request, timeout=60) as response, destination.open("wb") as handle:
        shutil.copyfileobj(response, handle)


def _write_manifest(target_dir: Path) -> None:
    (target_dir / "manifest.vs").write_text(
        "[VapourSynth Manifest V1]\n" f"{PLUGIN_NAME}\n", encoding="ascii", newline="\n"
    )


def _stage_prebuilt_plugin(version: str, target_dir: Path) -> bool:
    if _truthy(os.environ.get("NNEDI3CL_FORCE_BUILD")):
        print("NNEDI3CL wheel build: skipping prebuilt asset because NNEDI3CL_FORCE_BUILD is set")
        return False
    if not _supports_prebuilt():
        print("NNEDI3CL wheel build: no matching Release payload for this platform; falling back to a native build")
        return False

    source, explicit = _prebuilt_source(version)
    try:
        with tempfile.TemporaryDirectory(prefix="nnedi3cl-prebuilt-") as temp_dir_text:
            archive_path = Path(temp_dir_text) / (Path(source).name or _prebuilt_asset_name())
            _fetch_prebuilt_archive(source, archive_path)
            with zipfile.ZipFile(archive_path) as archive:
                members = [
                    name
                    for name in archive.namelist()
                    if name.replace("\\", "/").startswith(f"{PLUGIN_NAME}/") and not name.endswith("/")
                ]
                if not members:
                    raise FileNotFoundError(f"prebuilt archive does not contain a {PLUGIN_NAME}/ package directory")
                for member in members:
                    relative = member.replace("\\", "/").split("/", 1)[1]
                    out_path = target_dir / relative
                    out_path.parent.mkdir(parents=True, exist_ok=True)
                    with archive.open(member) as src, out_path.open("wb") as dst:
                        shutil.copyfileobj(src, dst)

        required = [target_dir / _plugin_filename(), target_dir / "nnedi3_weights.bin"]
        if sys.platform == "win32":
            required.append(target_dir / "OpenCL.dll")
        for path in required:
            if not path.is_file():
                raise FileNotFoundError(f"prebuilt archive did not provide {path.name}")
        if not (target_dir / "manifest.vs").exists():
            _write_manifest(target_dir)
    except Exception as exc:
        if explicit:
            raise RuntimeError(f"failed to use explicit NNEDI3CL prebuilt asset {source!r}") from exc
        print(f"NNEDI3CL wheel build: prebuilt asset unavailable at {source}; falling back to local build ({exc})")
        return False

    print(f"NNEDI3CL wheel build: using prebuilt release asset {source}")
    return True


def _find_built_plugin(build_dir: Path) -> Path:
    suffix = _plugin_filename().removeprefix(PLUGIN_NAME)
    for stem in (PLUGIN_NAME, f"lib{PLUGIN_NAME}"):
        candidate = build_dir / f"{stem}{suffix}"
        if candidate.is_file():
            return candidate
    for candidate in build_dir.rglob(f"*{suffix}"):
        if candidate.stem.removeprefix("lib") == PLUGIN_NAME:
            return candidate
    raise FileNotFoundError(f"missing {_plugin_filename()} under {build_dir}")


class CustomHook(BuildHookInterface[Any]):
    build_root = ROOT / "build-wheel"
    dist_dir = ROOT / "vapoursynth" / "plugins" / PLUGIN_NAME

    def initialize(self, version: str, build_data: dict[str, Any]) -> None:
        del version
        build_data["pure_python"] = False
        platform_tag = os.environ.get("NNEDI3CL_PLATFORM_TAG") or str(next(tags.platform_tags()))
        build_data["tag"] = f"py3-none-{platform_tag}"
        project_version = _project_version()

        shutil.rmtree(self.build_root, ignore_errors=True)
        shutil.rmtree(self.dist_dir.parent.parent, ignore_errors=True)
        self.build_root.mkdir(parents=True, exist_ok=True)
        self.dist_dir.mkdir(parents=True, exist_ok=True)

        if _stage_prebuilt_plugin(project_version, self.dist_dir):
            return

        env = _configure_build_env(os.environ.copy())
        if sys.platform == "win32":
            _run([sys.executable, "tools/ci_prepare_msys2.py"], env=env)
            env = _configure_build_env(env)
            _run(
                [
                    sys.executable,
                    "tools/ci_build_msys2.py",
                    "--clean",
                    "--build-dir",
                    str(self.build_root / "native"),
                    "--dist-dir",
                    str(self.build_root / "dist"),
                ],
                env=env,
            )
            built_package = self.build_root / "dist" / PLUGIN_NAME
            if not built_package.is_dir():
                raise FileNotFoundError(f"missing built package directory: {built_package}")
            for path in built_package.rglob("*"):
                if path.is_file():
                    out_path = self.dist_dir / path.relative_to(built_package)
                    out_path.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(path, out_path)
            return

        meson = _meson_command()
        build_dir = self.build_root / "native"
        _run(meson + ["setup", str(build_dir), "--wipe", "--buildtype", "release"], env=env)
        _run(meson + ["compile", "-C", str(build_dir)], env=env)
        shutil.copy2(_find_built_plugin(build_dir), self.dist_dir / _plugin_filename())
        shutil.copy2(ROOT / "NNEDI3CL" / "nnedi3_weights.bin", self.dist_dir / "nnedi3_weights.bin")
        _write_manifest(self.dist_dir)

    def finalize(self, version: str, build_data: dict[str, Any], artifact_path: str) -> None:
        del version, build_data, artifact_path
        shutil.rmtree(self.build_root, ignore_errors=True)
        shutil.rmtree(self.dist_dir.parent.parent, ignore_errors=True)
