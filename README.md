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

The easiest reproducible Windows build is the GitHub Actions workflow in
`.github/workflows/build-windows.yml`. It downloads the exact SDK/dependencies,
builds `nnedi3cl.dll`, smoke-loads the result with VapourSynth, and uploads an
artifact containing:

```
nnedi3cl.dll
nnedi3_weights.bin
OpenCL.dll
```

Download the artifact and put these files in the same plugin directory. On
Windows the weights file must sit next to `nnedi3cl.dll`. `OpenCL.dll` is the Khronos
ICD loader used for linking and loading; a real OpenCL runtime/driver is still
required when actually running the filter.


Windows CI Pipeline
-------------------

The workflow performs these steps:

1. Install Python build tools: `meson` and `ninja`.
2. Enter an x64 MSVC developer environment.
3. Download `VapourSynth64-Portable-R73.zip` from the official VapourSynth
   release and use its API4 SDK headers/import library.
4. Download Boost 1.71.0. The default build only needs Boost headers. Boost
   filesystem/system libraries are only needed if `-Doffline_cache=true` is
   enabled.
5. Download Khronos OpenCL headers and build the Khronos OpenCL ICD loader with
   MSVC to obtain `OpenCL.lib` and `OpenCL.dll`.
6. Configure Meson with explicit dependency paths.
7. Build `nnedi3cl.dll`.
8. Copy `nnedi3_weights.bin` and `OpenCL.dll` next to the DLL and smoke-load
   the plugin with VapourSynth.

This intentionally avoids requiring a full CUDA installation just to compile.
The bundled `OpenCL.dll` is only the Khronos ICD loader; a real OpenCL
runtime/driver is still required when actually running the filter.


Local Windows Build
-------------------

Required tools:

- Visual Studio Build Tools or Visual Studio with the x64 C++ toolchain.
- Python 3.12+ for the bundled VapourSynth R73 wheel used by the smoke test.
- Git.
- CMake.

From an x64 Developer Command Prompt:

```bat
python -m pip install --upgrade meson ninja
python tools\ci_prepare_windows.py
python tools\ci_build_windows.py --clean
python tools\smoke_load_artifact.py --vapoursynth-root _deps\vapoursynth-portable-R73 --artifact-dir dist\windows-x64
```

Output:

```text
dist/windows-x64/nnedi3cl.dll
dist/windows-x64/nnedi3_weights.bin
dist/windows-x64/OpenCL.dll
```

If `tools\ci_prepare_windows.py` reports that CMake used GCC/MinGW or cannot
find `OpenCL.lib`, start a fresh x64 Developer Command Prompt and rerun it. The
plugin is built with MSVC, so the OpenCL import library must be produced by the
same toolchain family.

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
