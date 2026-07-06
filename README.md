Description
===========

NNEDI3 is an intra-field only deinterlacer. It takes in a frame, throws away one field, and then interpolates the missing pixels using only information from the kept field. It has same rate and double rate modes, and works with YV12, YUY2, and RGB24 input. NNEDI3 is also very good for enlarging images by powers of 2.

Ported from AviSynth plugin http://bengal.missouri.edu/~kes25c/ and borrowed some codes from https://github.com/dubhater/vapoursynth-nnedi3 & https://forum.doom9.org/showthread.php?t=169766.


Usage
=====

The file `nnedi3_weights.bin` is required. On Windows, it must be located in the same folder as `NNEDI3CL.dll`. Everywhere else it can be located either in the same folder as `libnnedi3cl.so`/`libnnedi3cl.dylib`, or in `$prefix/share/NNEDI3CL/`. The build system installs it at the latter location automatically.

    nnedi3cl.NNEDI3CL(clip, int field[, bint dh=False, bint dw=False, int[] planes=[0, 1, 2], int nsize=6, int nns=1, int qual=1, int etype=0, int pscrn=2, int device=-1, bint list_device=False, bint info=False])

* clip: Clip to process. Any planar format with either integer sample type of 8-16 bit depth or float sample type of 32 bit depth is supported.

* field: Controls the mode of operation (double vs same rate) and which field is kept.
  * 0 = same rate, keep bottom field
  * 1 = same rate, keep top field
  * 2 = double rate (alternates each frame), starts with bottom
  * 3 = double rate (alternates each frame), starts with top

* dh: Doubles the height of the input. Each line of the input is copied to every other line of the output and the missing lines are interpolated. If field=0, the input is copied to the odd lines of the output. If field=1, the input is copied to the even lines of the output. field must be set to either 0 or 1 when using dh=True.

* dw: Doubles the width of the input. It does the same thing as `Transpose().nnedi3(dh=True).Transpose()` but also avoids unnecessary data copies when you scale both dimensions.

* planes: Sets which planes will be processed. Planes that are not processed will contain uninitialized memory.

* nsize: Sets the size of the local neighborhood around each pixel (x_diameter x y_diameter) that is used by the predictor neural network. For image enlargement it is recommended to use 0 or 4. Larger y_diameter settings will result in sharper output. For deinterlacing larger x_diameter settings will allow connecting lines of smaller slope. However, what setting to use really depends on the amount of aliasing (lost information) in the source. If the source was heavily low-pass filtered before interlacing then aliasing will be low and a large x_diameter setting wont be needed, and vice versa.
  * 0 = 8x6
  * 1 = 16x6
  * 2 = 32x6
  * 3 = 48x6
  * 4 = 8x4
  * 5 = 16x4
  * 6 = 32x4

* nns: Sets the number of neurons in the predictor neural network. 0 is fastest. 4 is slowest, but should give the best quality. This is a quality vs speed option; however, differences are usually small. The difference in speed will become larger as `qual` is increased.
  * 0 = 16
  * 1 = 32
  * 2 = 64
  * 3 = 128
  * 4 = 256

* qual: Controls the number of different neural network predictions that are blended together to compute the final output value. Each neural network was trained on a different set of training data. Blending the results of these different networks improves generalization to unseen data. Possible values are 1 or 2. Essentially this is a quality vs speed option. Larger values will result in more processing time, but should give better results. However, the difference is usually pretty small. I would recommend using `qual>1` for things like single image enlargement.

* etype: Controls which set of weights to use in the predictor nn.
  * 0 = weights trained to minimize absolute error
  * 1 = weights trained to minimize squared error

* pscrn: Controls whether or not the prescreener neural network is used to decide which pixels should be processed by the predictor neural network and which can be handled by simple cubic interpolation. The prescreener is trained to know whether cubic interpolation will be sufficient for a pixel or whether it should be predicted by the predictor nn. The computational complexity of the prescreener nn is much less than that of the predictor nn. Since most pixels can be handled by cubic interpolation, using the prescreener generally results in much faster processing. The prescreener is pretty accurate, so the difference between using it and not using it is almost always unnoticeable. The new prescreener is faster than the old one, and it also causes more pixels to be handled by cubic interpolation.
  * 1 = old prescreener
  * 2 = new prescreener (unavailable with float input)

* device: Sets target OpenCL device. Use `list_device` to get the index of the available devices. By default the default device is selected.

* list_device: Whether to draw the devices list on the frame.

* info: Whether to draw the OpenCL-related info on the frame.


Compilation
===========

The preferred reproducible Windows build is the MSYS2/UCRT64 workflow in
`.github/workflows/build-msys2.yml`. It uses the VapourSynth R77 wheel for API4
headers and smoke loading, and uses MSYS2 packages for the C++ compiler, Boost,
OpenCL headers, and the Khronos OpenCL ICD loader.

The uploaded artifact is laid out as a VapourSynth plugin package:

```
vapoursynth/plugins/nnedi3cl/
  manifest.vs
  nnedi3cl.dll
  nnedi3_weights.bin
  OpenCL.dll
  libgcc_s_seh-1.dll
  libstdc++-6.dll
  libwinpthread-1.dll
```

Install it by copying the `nnedi3cl` directory under
`<site-packages>/vapoursynth/plugins/`, or unzip the artifact at
`<site-packages>` so the path above is preserved. For testing without
installing, set `VAPOURSYNTH_EXTRA_PLUGIN_PATH` to the artifact's
`vapoursynth/plugins` directory.

`manifest.vs` tells VapourSynth to load only `nnedi3cl.dll` from this directory.
The remaining DLLs are support libraries and are kept next to the plugin so the
Windows loader can resolve them. `OpenCL.dll` is only the Khronos ICD loader; a
real OpenCL driver/runtime is still required when actually running the filter.


MSYS2/R77 CI Pipeline
---------------------

The workflow performs these steps:

1. Install MSYS2 UCRT64 packages: GCC, Meson, Ninja, pkgconf, Boost, OpenCL
   headers, and OpenCL ICD loader.
2. Download the VapourSynth R77 wheel with normal CPython and extract it under
   `_deps/vapoursynth-wheel-R77`.
3. Generate a normalized `vapoursynth.pc` for the extracted wheel. The wheel
   already ships headers, but its pkg-config file is meant for installed wheel
   layout, not direct extraction.
4. Configure Meson through pkg-config.
5. Build `nnedi3cl.dll` with MinGW/UCRT64.
6. Package the plugin as `vapoursynth/plugins/nnedi3cl/`.
7. Recursively scan DLL dependencies with `objdump -p` and copy needed MSYS2
   runtime DLLs next to the plugin.
8. Smoke-load the result with VapourSynth R77.

The build defines `CL_TARGET_OPENCL_VERSION=120`. This keeps Boost.Compute
compatible with current Khronos OpenCL headers, whose default target is OpenCL
3.0.


Local MSYS2 Build
-----------------

Required tools:

- A UCRT64 MSYS2 environment.
- Normal Windows CPython, or another Python able to run `pip download`, for
  `tools/ci_prepare_msys2.py`.

Install the MSYS2 packages:

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

Prepare the R77 wheel files from a normal Windows shell:

```bat
python tools\ci_prepare_msys2.py
```

Build from an MSYS2 UCRT64 shell:

```bash
/ucrt64/bin/python tools/ci_build_msys2.py --clean
```

Smoke-load from the normal Windows Python used above:

```bat
python tools\smoke_load_artifact.py --vapoursynth-root _deps\vapoursynth-wheel-R77 --artifact-dir dist\msys2-ucrt64
```

Output layout:

```text
dist/msys2-ucrt64/vapoursynth/plugins/nnedi3cl/
```


MSVC Compatibility Build
------------------------

`.github/workflows/build-windows.yml` is retained as a compatibility build. It
uses MSVC, the official VapourSynth R73 portable SDK, Boost 1.71.0 headers, and
a locally built Khronos OpenCL ICD loader. It uploads a flat artifact:

```text
nnedi3cl.dll
nnedi3_weights.bin
OpenCL.dll
```

Local MSVC builds still require an x64 Developer Command Prompt:

```bat
python -m pip install --upgrade meson ninja
python tools\ci_prepare_windows.py
python tools\ci_build_windows.py --clean
python tools\smoke_load_artifact.py --vapoursynth-root _deps\vapoursynth-portable-R73 --artifact-dir dist\windows-x64
```

If you already have dependencies installed, Meson can be invoked directly:

```bat
meson setup build --buildtype release ^
  -Dvapoursynth_incdir=C:/path/to/vapoursynth/sdk/include/vapoursynth ^
  -Dboost_root=C:/path/to/boost_1_71_0 ^
  -Dopencl_incdir=C:/path/to/opencl-headers ^
  -Dopencl_libdir=C:/path/to/opencl/lib ^
  -Dvapoursynth_plugindir=C:/path/to/output
ninja -C build
```

The important dependency paths are:

- `vapoursynth_incdir`: directory containing `VapourSynth4.h` and
  `VSHelper4.h`.
- `boost_root`: directory containing `boost/compute/core.hpp`.
- `opencl_incdir`: directory containing `CL/opencl.h`.
- `opencl_libdir`: directory containing `OpenCL.lib`.
- `offline_cache`: optional Boost.Compute offline kernel cache. The default is
  `false` to avoid requiring compiled Boost libraries.


Linux/macOS Build
-----------------

The original Meson flow is still supported when the dependencies are discoverable
through normal system mechanisms:

```bash
meson setup build --buildtype release
ninja -C build
```

You need:

- VapourSynth API4 development headers and library/pkg-config metadata.
- Boost headers, plus Boost filesystem/system libraries only if
  `-Doffline_cache=true`.
- OpenCL headers and loader library.

If pkg-config cannot find VapourSynth, use the explicit Meson options shown in
the Windows section.
