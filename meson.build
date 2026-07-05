project('NNEDI3CL', 'cpp',
  default_options : ['buildtype=release', 'b_ndebug=if-release', 'cpp_std=c++14'],
  meson_version : '>=0.48.0',
  version : '8'
)

cpp = meson.get_compiler('cpp')
include_arg_prefix = cpp.get_id() == 'msvc' ? '/I' : '-I'

if cpp.get_id() == 'msvc'
  add_project_arguments('/fp:fast', '-DBOOST_ALL_NO_LIB', language : 'cpp')
else
  add_project_arguments('-ffast-math', language : 'cpp')
endif

add_project_arguments('-DNNEDI3_DATADIR="@0@"'.format(join_paths(get_option('prefix'), get_option('datadir'), meson.project_name())), language : 'cpp')

sources = [
  'NNEDI3CL/NNEDI3CL.cpp'
]

vapoursynth_incdir = get_option('vapoursynth_incdir')
if vapoursynth_incdir != ''
  vapoursynth_dep = declare_dependency(compile_args : [include_arg_prefix + vapoursynth_incdir])
  vapoursynth_libdir = get_option('libdir')
else
  vapoursynth_dep = dependency('vapoursynth').partial_dependency(compile_args : true, includes : true)
  vapoursynth_libdir = dependency('vapoursynth').get_pkgconfig_variable('libdir')
endif

boost_root = get_option('boost_root')
if boost_root != ''
  boost_dep = declare_dependency(compile_args : [include_arg_prefix + boost_root])
else
  if get_option('offline_cache')
    boost_dep = dependency('boost', modules : ['filesystem', 'system'])
  else
    boost_dep = dependency('boost')
  endif
endif

if get_option('offline_cache')
  add_project_arguments('-DNNEDI3CL_ENABLE_OFFLINE_CACHE', language : 'cpp')
endif

opencl_incdir = get_option('opencl_incdir')
opencl_libdir = get_option('opencl_libdir')
if opencl_incdir != '' or opencl_libdir != ''
  opencl_compile_args = []
  if opencl_incdir != ''
    opencl_compile_args = [include_arg_prefix + opencl_incdir]
  endif
  opencl_lib = cpp.find_library('OpenCL', dirs : opencl_libdir != '' ? [opencl_libdir] : [])
  opencl_dep = declare_dependency(compile_args : opencl_compile_args, dependencies : opencl_lib)
else
  opencl_dep = dependency('OpenCL', required : false)
  if not opencl_dep.found()
    opencl_dep = cpp.find_library('OpenCL')
  endif
endif

deps = [vapoursynth_dep, boost_dep, opencl_dep]

if host_machine.cpu_family().startswith('x86') and cpp.get_id() != 'msvc'
  add_project_arguments('-mfpmath=sse', '-msse2', language : 'cpp')
endif

plugin_dir = get_option('vapoursynth_plugindir')
if plugin_dir == ''
  plugin_dir = join_paths(vapoursynth_libdir, 'vapoursynth')
endif

shared_module('nnedi3cl', sources,
  dependencies : deps,
  install : true,
  install_dir : plugin_dir,
  gnu_symbol_visibility : 'hidden'
)

install_data('NNEDI3CL/nnedi3_weights.bin')
