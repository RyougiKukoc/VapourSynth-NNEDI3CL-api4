#!/usr/bin/env python3
"""Explicitly load an NNEDI3CL package and exercise its OpenCL backend."""

from __future__ import annotations

import argparse
import ctypes
import hashlib
import json
import os
import shutil
import sys
import tempfile
import zipfile
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
PLUGIN_NAME = "nnedi3cl"
NO_DEVICE_MARKERS = ("no device", "no opencl", "cl_device_not_found", "device not found")


def plugin_filename() -> str:
    if sys.platform == "win32":
        return f"{PLUGIN_NAME}.dll"
    if sys.platform == "darwin":
        return f"{PLUGIN_NAME}.dylib"
    return f"{PLUGIN_NAME}.so"


def frame_hash(frame: Any) -> str:
    digest = hashlib.sha256()
    for plane in range(frame.format.num_planes):
        digest.update(bytes(frame[plane]))
    return digest.hexdigest()


def opencl_devices() -> list[str]:
    library_name = "OpenCL.dll" if sys.platform == "win32" else "libOpenCL.so.1"
    library = ctypes.WinDLL(library_name) if sys.platform == "win32" else ctypes.CDLL(library_name)
    platform_id = ctypes.c_void_p
    device_id = ctypes.c_void_p
    count = ctypes.c_uint()
    get_platforms = library.clGetPlatformIDs
    get_platforms.argtypes = [ctypes.c_uint, ctypes.POINTER(platform_id), ctypes.POINTER(ctypes.c_uint)]
    get_platforms.restype = ctypes.c_int
    if get_platforms(0, None, ctypes.byref(count)) != 0 or not count.value:
        return []
    platforms = (platform_id * count.value)()
    if get_platforms(count.value, platforms, None) != 0:
        return []

    get_devices = library.clGetDeviceIDs
    get_devices.argtypes = [platform_id, ctypes.c_ulonglong, ctypes.c_uint, ctypes.POINTER(device_id), ctypes.POINTER(ctypes.c_uint)]
    get_devices.restype = ctypes.c_int
    get_info = library.clGetDeviceInfo
    get_info.argtypes = [device_id, ctypes.c_uint, ctypes.c_size_t, ctypes.c_void_p, ctypes.POINTER(ctypes.c_size_t)]
    get_info.restype = ctypes.c_int
    devices: list[str] = []
    for platform in platforms:
        if get_devices(platform, 0xFFFFFFFF, 0, None, ctypes.byref(count)) != 0:
            continue
        ids = (device_id * count.value)()
        if get_devices(platform, 0xFFFFFFFF, count.value, ids, None) != 0:
            continue
        for device in ids:
            labels = []
            for parameter in (0x102C, 0x102B):  # CL_DEVICE_VENDOR, CL_DEVICE_NAME
                size = ctypes.c_size_t()
                if get_info(device, parameter, 0, None, ctypes.byref(size)) != 0:
                    continue
                buffer = ctypes.create_string_buffer(size.value)
                if get_info(device, parameter, size.value, buffer, None) == 0:
                    labels.append(buffer.value.decode("utf-8", "replace"))
            devices.append(" / ".join(labels))
    return devices


def resolve_artifact_dir(artifact_dir_arg: str | None, artifact_zip_arg: str | None) -> tuple[Path, Path | None]:
    if artifact_zip_arg:
        archive = (ROOT / artifact_zip_arg).resolve()
        if not archive.is_file():
            raise FileNotFoundError(f"missing artifact zip: {archive}")
        temporary = Path(tempfile.mkdtemp(prefix="nnedi3cl-package-"))
        with zipfile.ZipFile(archive) as zip_file:
            zip_file.extractall(temporary)
        candidates = [path for path in temporary.iterdir() if path.is_dir()]
        if len(candidates) != 1 or candidates[0].name != PLUGIN_NAME:
            raise RuntimeError(f"expected one top-level {PLUGIN_NAME}/ directory in {archive}, found {candidates}")
        return candidates[0], temporary
    return (ROOT / (artifact_dir_arg or f"dist/msys2-ucrt64/{PLUGIN_NAME}")).resolve(), None


class IsolatedEnvironmentPolicy:
    """Create a single VapourSynth core with autoload disabled."""

    def __init__(self, flags: int) -> None:
        self._api: Any = None
        self._environment: Any = None
        self._flags = flags

    def on_policy_registered(self, api: Any) -> None:
        self._api = api
        self._environment = api.create_environment(self._flags)

    def on_policy_cleared(self) -> None:
        self._api = None
        self._environment = None

    def get_current_environment(self) -> Any:
        return self._environment

    def set_environment(self, environment: Any) -> Any:
        previous = self._environment
        if environment is not None:
            self._environment = environment
        return previous

    def is_alive(self, environment: Any) -> bool:
        return environment is self._environment

    def close(self) -> None:
        if self._api is not None and self._environment is not None:
            self._api.destroy_environment(self._environment)
            self._environment = None


def install_isolated_policy(vs: Any) -> IsolatedEnvironmentPolicy | None:
    if not hasattr(vs, "register_policy") or vs.has_policy():
        return None
    policy = IsolatedEnvironmentPolicy(int(vs.DISABLE_AUTO_LOADING))
    vs.register_policy(policy)
    return policy


def exercise_filter(core: Any, namespace: Any, vs: Any, *, require_opencl: bool, expect_device: str | None) -> dict[str, Any]:
    # The built-in Text filter used by NNEDI3CL's info mode needs at least 40x48.
    clip = core.std.BlankClip(format=vs.YUV420P8, width=128, height=96, length=12, color=[96, 128, 128])
    try:
        out = namespace.NNEDI3CL(clip, field=1, dh=True)
        frames = {number: out.get_frame(number) for number in (0, 3, 11)}
        stats = dict(core.std.PlaneStats(out).get_frame(3).props)
    except Exception as exc:
        message = str(exc)
        if not require_opencl and any(marker in message.lower() for marker in NO_DEVICE_MARKERS):
            return {"exercise_filter": True, "exercise_skipped": True, "exercise_skip_reason": message}
        raise RuntimeError(f"NNEDI3CL OpenCL frame request failed: {message}") from exc

    devices = opencl_devices()
    device_info = "; ".join(devices)
    if expect_device and not any(expect_device.lower() in device.lower() for device in devices):
        raise RuntimeError(f"expected OpenCL device containing {expect_device!r}, got {devices!r}")
    hashes = {number: frame_hash(frame) for number, frame in frames.items()}
    if len(set(hashes.values())) != 1:
        raise RuntimeError(f"static input produced inconsistent NNEDI3CL hashes: {hashes}")
    return {
        "exercise_filter": True,
        "exercise_skipped": False,
        "width": frames[3].width,
        "height": frames[3].height,
        "format": frames[3].format.name,
        "frames": out.num_frames,
        "frame_hashes": hashes,
        "plane_stats_average": float(stats["PlaneStatsAverage"]),
        "plane_stats_min": float(stats["PlaneStatsMin"]),
        "plane_stats_max": float(stats["PlaneStatsMax"]),
        "opencl_device_info": device_info,
    }


def invalid_input_result(core: Any, namespace: Any, vs: Any) -> str:
    clip = core.std.BlankClip(format=vs.YUV420P8, width=64, height=32, length=1)
    try:
        namespace.NNEDI3CL(clip, field=2, dh=True)
    except vs.Error as exc:
        message = str(exc)
        if "field must be 0 or 1 when dh=True" not in message:
            raise RuntimeError(f"unexpected invalid-input error: {message}") from exc
        return message
    raise RuntimeError("NNEDI3CL accepted field=2 with dh=True")


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description="Smoke test a packaged NNEDI3CL plugin.")
    parser.add_argument("--artifact-dir", help="Packaged plugin directory.")
    parser.add_argument("--artifact-zip", help="Packaged plugin zip asset.")
    parser.add_argument("--exercise-filter", action="store_true", help="Request deterministic OpenCL frames when an ICD is available.")
    parser.add_argument("--require-opencl", action="store_true", help="Fail rather than skip when no OpenCL device can execute NNEDI3CL.")
    parser.add_argument("--expect-device", help="Require OpenCL information to name this device/vendor substring.")
    parser.add_argument("--json", action="store_true", help="Emit JSON result.")
    args = parser.parse_args(argv)
    if args.require_opencl and not args.exercise_filter:
        parser.error("--require-opencl requires --exercise-filter")

    artifact_dir, temporary = resolve_artifact_dir(args.artifact_dir, args.artifact_zip)
    plugin = artifact_dir / plugin_filename()
    required = [plugin, artifact_dir / "manifest.vs", artifact_dir / "nnedi3_weights.bin"]
    if sys.platform == "win32":
        required.append(artifact_dir / "OpenCL.dll")
    for path in required:
        if not path.is_file():
            raise FileNotFoundError(f"missing required package file: {path}")

    handles = []
    policy = None
    if sys.platform == "win32":
        handles.append(os.add_dll_directory(str(artifact_dir)))
    try:
        import vapoursynth as vs  # pylint: disable=import-outside-toplevel

        policy = install_isolated_policy(vs)
        core = vs.core
        core.std.LoadPlugin(str(plugin))
        namespace = getattr(core, PLUGIN_NAME, None)
        if namespace is None or not hasattr(namespace, "NNEDI3CL"):
            raise RuntimeError("nnedi3cl.NNEDI3CL missing after explicit LoadPlugin")

        result: dict[str, Any] = {
            "plugin": str(plugin),
            "manifest": str(artifact_dir / "manifest.vs"),
            "weights": str(artifact_dir / "nnedi3_weights.bin"),
            "namespace_loaded": True,
            "callable_loaded": True,
            "invalid_input_error": invalid_input_result(core, namespace, vs),
        }
        if args.exercise_filter:
            result.update(exercise_filter(core, namespace, vs, require_opencl=args.require_opencl, expect_device=args.expect_device))
        if args.json:
            print(json.dumps(result, indent=2, sort_keys=True))
        else:
            for key, value in result.items():
                print(f"{key}={value}")
        return 0
    finally:
        for handle in handles:
            handle.close()
        if policy is not None:
            policy.close()
        if temporary is not None:
            shutil.rmtree(temporary, ignore_errors=True)


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
