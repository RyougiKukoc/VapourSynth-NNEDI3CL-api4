#!/usr/bin/env python3
"""Smoke test the NNEDI3CL plugin autoloaded from an installed wheel."""

from __future__ import annotations

import argparse
import json
import site
import sys
from typing import Any

from ci_smoke_package import exercise_filter, invalid_input_result


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description="Smoke test an installed NNEDI3CL wheel.")
    parser.add_argument("--exercise-filter", action="store_true", help="Request deterministic OpenCL frames when an ICD is available.")
    parser.add_argument("--require-opencl", action="store_true", help="Fail rather than skip when no OpenCL device can execute NNEDI3CL.")
    parser.add_argument("--expect-device", help="Require OpenCL information to name this device/vendor substring.")
    parser.add_argument("--json", action="store_true", help="Emit JSON result.")
    args = parser.parse_args(argv)
    if args.require_opencl and not args.exercise_filter:
        parser.error("--require-opencl requires --exercise-filter")

    import vapoursynth as vs  # pylint: disable=import-outside-toplevel

    core = vs.core
    namespace = getattr(core, "nnedi3cl", None)
    if namespace is None or not hasattr(namespace, "NNEDI3CL"):
        raise RuntimeError("nnedi3cl plugin namespace was not autoloaded from the installed wheel")

    result: dict[str, Any] = {
        "vapoursynth_module": vs.__file__,
        "site_packages": site.getsitepackages(),
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


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
