# NNEDI3CL

NNEDI3 is an intra-field only deinterlacer. It throws away one field, then
interpolates the missing pixels from the kept field. It also works well for
enlarging images by powers of two.

This repository is the API4 port plus the Windows-first packaging/release flow
for `NNEDI3CL`.

## Installation

Recommended on Windows x86_64:

```powershell
pip install "vapoursynth-nnedi3cl @ git+https://github.com/RyougiKukoc/VapourSynth-NNEDI3CL-api4.git"
```

That install path builds a wheel from the repository metadata, but the build
hook first tries to reuse the matching GitHub Release asset:

```text
nnedi3cl-msys2-ucrt64.zip
```

for version `8.0`, currently from release tag:

```text
v8.0-api4-msys2
```

If the prebuilt asset is available, `pip` repackages that tested plugin payload
into the wheel. If it is unavailable, the build hook falls back to a local
MSYS2/UCRT64 build.

Direct wheel install is also supported. Download the wheel from the repository
Releases page and install it with:

```powershell
pip install vapoursynth_nnedi3cl-8.0-py3-none-win_amd64.whl
```

The wheel installs the plugin package under:

```text
site-packages/vapoursynth/plugins/nnedi3cl/
```

so users do not need to manually copy `dll` files into a plugin directory.

Useful install controls:

```powershell
$env:NNEDI3CL_FORCE_BUILD = "1"
pip install --no-build-isolation "vapoursynth-nnedi3cl @ git+https://github.com/RyougiKukoc/VapourSynth-NNEDI3CL-api4.git"
```

forces a local build instead of using a Release asset.

```powershell
$env:NNEDI3CL_PREBUILT_URL = "C:\path\to\nnedi3cl-msys2-ucrt64.zip"
pip install --no-build-isolation "vapoursynth-nnedi3cl @ git+https://github.com/RyougiKukoc/VapourSynth-NNEDI3CL-api4.git"
```

forces a specific local or remote prebuilt zip.

## Usage

This package does not expose a separate helper module. After installation, use
the normal VapourSynth plugin namespace:

```python
import vapoursynth as vs

core = vs.core
clip = core.std.BlankClip(width=640, height=360, format=vs.YUV420P8)
out = core.nnedi3cl.NNEDI3CL(clip, field=1, dh=True)
```

The required `nnedi3_weights.bin` file is installed beside `nnedi3cl.dll`
automatically.

Function signature:

```text
nnedi3cl.NNEDI3CL(clip, int field[, bint dh=False, bint dw=False, int[] planes=[0, 1, 2], int nsize=6, int nns=1, int qual=1, int etype=0, int pscrn=2, int device=-1, bint list_device=False, bint info=False])
```

- `clip`: planar integer 8-16 bit or float 32 bit clip to process.
- `field`: same-rate or double-rate mode, and which field to keep.
  `0` bottom, `1` top, `2` double-rate starting bottom, `3` double-rate starting top.
- `dh`: doubles height. Requires `field` to be `0` or `1`.
- `dw`: doubles width.
- `planes`: planes to process. Unprocessed planes are left uninitialized.
- `nsize`: predictor neighborhood size.
  `0=8x6`, `1=16x6`, `2=32x6`, `3=48x6`, `4=8x4`, `5=16x4`, `6=32x4`.
- `nns`: predictor neuron count.
  `0=16`, `1=32`, `2=64`, `3=128`, `4=256`.
- `qual`: number of blended predictor outputs. Valid values are `1` or `2`.
- `etype`: weight set.
  `0` absolute-error trained, `1` squared-error trained.
- `pscrn`: prescreener mode.
  `1` old prescreener, `2` new prescreener.
- `device`: OpenCL device index.
- `list_device`: draw the device list on the frame.
- `info`: draw OpenCL info on the frame.

## Build And Release

The primary Windows workflow is `.github/workflows/build-msys2.yml`. It builds
with MSYS2/UCRT64, smoke-loads the packaged plugin, builds a wheel, smoke-tests
the installed wheel, and publishes both the tested package zip and the wheel as
Release assets.

The packaged plugin layout is:

```text
nnedi3cl/
  manifest.vs
  nnedi3cl.dll
  nnedi3_weights.bin
  OpenCL.dll
  libgcc_s_seh-1.dll
  libstdc++-6.dll
  libwinpthread-1.dll
```

`manifest.vs` ensures VapourSynth loads only `nnedi3cl.dll` from this
directory. The other `dll` files are support/runtime libraries. `OpenCL.dll`
here is the Khronos ICD loader; actual filtering still needs a real OpenCL
driver/runtime.

The MSYS2 workflow does this:

1. Install GCC, Meson, Ninja, pkgconf, Boost, OpenCL headers, and the OpenCL ICD loader.
2. Download and normalize the VapourSynth R77 wheel for API4 headers and `pkg-config`.
3. Build `nnedi3cl.dll`.
4. Package `nnedi3cl/` and smoke-load it.
5. Build `vapoursynth-nnedi3cl` wheel metadata from the repository.
6. Create release assets:
   `nnedi3cl-msys2-ucrt64.zip` and `vapoursynth_nnedi3cl-*.whl`.
7. Smoke-test the installed wheel.
8. Smoke-test source install from repository metadata while forcing the local release zip as the prebuilt asset.

Push a `v*` tag or publish a GitHub Release to upload the assets automatically.

### Local MSYS2 Build

Install packages:

```bash
pacman -S --needed \
  mingw-w64-ucrt-x86_64-gcc \
  mingw-w64-ucrt-x86_64-python \
  mingw-w64-ucrt-x86_64-meson \
  mingw-w64-ucrt-x86_64-ninja \
  mingw-w64-ucrt-x86_64-pkgconf \
  mingw-w64-ucrt-x86_64-boost \
  mingw-w64-ucrt-x86_64-opencl-headers \
  mingw-w64-ucrt-x86_64-opencl-icd
```

Prepare the extracted VapourSynth wheel from a normal Windows shell:

```bat
python tools\ci_prepare_msys2.py
```

Build from an MSYS2 UCRT64 shell:

```bash
/ucrt64/bin/python tools/ci_build_msys2.py --clean
```

Build a wheel from the repository:

```powershell
python -m pip install --upgrade build hatchling packaging VapourSynth
$env:NNEDI3CL_FORCE_BUILD = "1"
python -m build --wheel --no-isolation --outdir dist\wheels
```

Smoke-load the packaged directory:

```bat
python tools\smoke_load_artifact.py --vapoursynth-root _deps\vapoursynth-wheel-R77 --artifact-dir dist\msys2-ucrt64 --exercise-filter
```

### MSVC Compatibility Build

`.github/workflows/build-windows.yml` is kept as a manual-only compatibility
workflow. It uses MSVC, the VapourSynth R73 portable SDK, Boost 1.71.0 headers,
and a locally built Khronos OpenCL ICD loader.

Local MSVC build:

```bat
python -m pip install --upgrade meson ninja
python tools\ci_prepare_windows.py
python tools\ci_build_windows.py --clean
python tools\smoke_load_artifact.py --vapoursynth-root _deps\vapoursynth-portable-R73 --artifact-dir dist\windows-x64 --exercise-filter
```

Direct Meson invocation is also possible:

```bat
meson setup build --buildtype release ^
  -Dvapoursynth_incdir=C:/path/to/vapoursynth/sdk/include/vapoursynth ^
  -Dboost_root=C:/path/to/boost_1_71_0 ^
  -Dopencl_incdir=C:/path/to/opencl-headers ^
  -Dopencl_libdir=C:/path/to/opencl/lib ^
  -Dvapoursynth_plugindir=C:/path/to/output
ninja -C build
```

### Linux Or macOS

The original Meson flow is still supported when dependencies are discoverable:

```bash
meson setup build --buildtype release
ninja -C build
```

Required dependencies:

- VapourSynth API4 development headers and library/pkg-config metadata.
- Boost headers, plus Boost filesystem/system only if `-Doffline_cache=true`.
- OpenCL headers and loader library.
