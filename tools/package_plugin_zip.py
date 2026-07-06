from __future__ import annotations

import argparse
import sys
import zipfile
from pathlib import Path


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description="Create a release zip for a packaged VapourSynth plugin directory.")
    parser.add_argument("--input-dir", required=True, help="Directory containing the top-level nnedi3cl package directory.")
    parser.add_argument("--output", required=True, help="Output zip path.")
    args = parser.parse_args(argv)

    input_dir = Path(args.input_dir).resolve()
    output = Path(args.output).resolve()
    package_dir = input_dir / "nnedi3cl"
    if not package_dir.is_dir():
        print(f"missing package directory: {package_dir}", file=sys.stderr)
        return 1
    for required in [
        package_dir / "manifest.vs",
        package_dir / "nnedi3cl.dll",
        package_dir / "nnedi3_weights.bin",
        package_dir / "OpenCL.dll",
    ]:
        if not required.exists():
            print(f"missing required package file: {required}", file=sys.stderr)
            return 1

    output.parent.mkdir(parents=True, exist_ok=True)
    if output.exists():
        output.unlink()

    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for path in sorted(package_dir.rglob("*")):
            if path.is_file():
                zf.write(path, path.relative_to(input_dir).as_posix())

    with zipfile.ZipFile(output) as zf:
        names = zf.namelist()
    print(f"release_asset={output}")
    for name in names:
        print(name)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
