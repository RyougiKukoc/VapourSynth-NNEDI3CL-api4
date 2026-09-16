from __future__ import annotations

import argparse
import sys
import zipfile
from pathlib import Path


PLUGIN_NAME = "nnedi3cl"


def plugin_filename() -> str:
    if sys.platform == "win32":
        return f"{PLUGIN_NAME}.dll"
    if sys.platform == "darwin":
        return f"{PLUGIN_NAME}.dylib"
    return f"{PLUGIN_NAME}.so"


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description="Create a release zip for a packaged NNEDI3CL plugin directory.")
    parser.add_argument("--input-dir", required=True, help="Directory containing the top-level nnedi3cl package directory.")
    parser.add_argument("--output", required=True, help="Output zip path.")
    args = parser.parse_args(argv)

    input_dir = Path(args.input_dir).resolve()
    output = Path(args.output).resolve()
    package_dir = input_dir / PLUGIN_NAME
    if not package_dir.is_dir():
        raise FileNotFoundError(f"missing package directory: {package_dir}")
    required = [package_dir / "manifest.vs", package_dir / plugin_filename(), package_dir / "nnedi3_weights.bin"]
    if sys.platform == "win32":
        required.append(package_dir / "OpenCL.dll")
    for path in required:
        if not path.is_file():
            raise FileNotFoundError(f"missing required package file: {path}")

    output.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(package_dir.rglob("*")):
            if path.is_file():
                archive.write(path, path.relative_to(input_dir).as_posix())

    print(f"release_asset={output}")
    with zipfile.ZipFile(output) as archive:
        for name in archive.namelist():
            print(name)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
