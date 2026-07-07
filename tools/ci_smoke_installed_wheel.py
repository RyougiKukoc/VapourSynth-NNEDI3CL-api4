#!/usr/bin/env python3
"""Smoke test an installed NNEDI3CL wheel."""

from __future__ import annotations

import argparse
import json
import site
import sys


NO_DEVICE_MARKERS = (
    "no device",
    "no opencl",
    "cl_device_not_found",
    "device not found",
)


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description="Smoke test an installed NNEDI3CL wheel.")
    parser.add_argument("--exercise-filter", action="store_true", help="Try to render one frame if OpenCL is available.")
    parser.add_argument("--json", action="store_true", help="Emit JSON result.")
    args = parser.parse_args(argv)

    import vapoursynth as vs  # pylint: disable=import-outside-toplevel

    core = vs.core
    namespace = getattr(core, "nnedi3cl", None)
    if namespace is None or not hasattr(namespace, "NNEDI3CL"):
        raise RuntimeError("nnedi3cl plugin namespace was not autoloaded from the installed wheel")

    result = {
        "vapoursynth_module": vs.__file__,
        "site_packages": site.getsitepackages(),
        "namespace_loaded": True,
        "callable_loaded": True,
    }

    if args.exercise_filter:
        clip = core.std.BlankClip(format=vs.YUV420P8, width=64, height=32, length=1)
        try:
            out = namespace.NNEDI3CL(clip, field=1, dh=True)
            frame = out.get_frame(0)
            stats = dict(core.std.PlaneStats(out).get_frame(0).props)
            result.update(
                {
                    "exercise_filter": True,
                    "exercise_skipped": False,
                    "width": frame.width,
                    "height": frame.height,
                    "format": frame.format.name,
                    "plane_stats_average": float(stats["PlaneStatsAverage"]),
                    "plane_stats_min": float(stats["PlaneStatsMin"]),
                    "plane_stats_max": float(stats["PlaneStatsMax"]),
                }
            )
        except Exception as exc:
            message = str(exc)
            if any(marker in message.lower() for marker in NO_DEVICE_MARKERS):
                result.update(
                    {
                        "exercise_filter": True,
                        "exercise_skipped": True,
                        "exercise_skip_reason": message,
                    }
                )
            else:
                raise

    if args.json:
        print(json.dumps(result, indent=2, sort_keys=True))
    else:
        for key, value in result.items():
            print(f"{key}={value}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
