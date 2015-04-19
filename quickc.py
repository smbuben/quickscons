#!/usr/bin/env python
# encoding: utf-8

# This file is part of the quickscons project. This project is used to build
# other software that MAY or MAY NOT be licensed under the same terms as this
# project. This project is licensed under the below:
#
# The MIT License (MIT)
#
# Copyright © 2015 Stephen M Buben <smbuben@gmail.com>
#
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to
# deal in the Software without restriction, including without limitation the
# rights to use, copy, modify, merge, publish, distribute, sublicense, and/or
# sell copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:

# The above copyright notice and this permission notice shall be included in
# all copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING
# FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS
# IN THE SOFTWARE.

"""
quickscons.quickc

Wrapper around SCons to simplify SConstruct and SConscript files for C/C++
projects assuming that some basic project hierarchy standards are followed.

The quickscons Python package should be placed in your site_scons directory.

Example:

    Given the following directory hierarchy:

    Project/
        SConstruct
        Program/
            SConscript
            src/
                ... source files and private headers ...
        SharedLib/
            SConscript
            inc/
                ... public headers ...
            src/
                ... source files and private headers ...
        StaticLib/
            SConscript
            inc/
                ... public headers ...
            src/
                ... source files and private headers ...
        site_scons/
            quickscons/
                __init__.py
                quickc.py <-- this file

    Only the following SCons declarations are needed:

    Project/SConstruct:

        from quickscons import quickc
        env = Environment()
        quickc.Enable(env)
        env.QuickBuild('Program')

    Program/SConscript:

        Import('env')
        result = env.QuickProgram('progname', deps=['SharedLib', 'StaticLib'])
        env.ExportBin(result)

    SharedLib/SConscript:

        Import('env')
        result = env.QuickSharedLib()
        env.ExportLib(result)

    StaticLib/SConscript:

        Import('env')
        env.QuickStaticLib()

    Starting with any "quick builds" in the SConstruct, quickscons will
    traverse the project hierarchy to resolve defined dependencies, execute
    the SConscript files for those dependencies, and then update the build
    environment for the dependent unit so that it can compile and link.
    Dependencies are defined using path semantics (separated with a
    forward-slash) and will be resolved as the first matching path on a
    directory walk backwards from the current unit to the project root.

    Assuming that the current working directory is 'Project', after running
    SCons the following output hierarchy will be produced:

    Project/
        build/
            debug/
                Program/
                    ... intermediate build files ...
                SharedLib/
                    ... intermediate build files ...
                StaticLib/
                    ... intermediate build files ...
        export/
            debug/
                bin/
                    progname
                lib/
                    SharedLib.so

    And, the program can be run with:

        $ LD_LIBRARY_PATH=export/debug/lib export/debug/bin/progname

    Note that 'debug' in the above should be replaced with 'release' if the
    flag '--release' is passed to SCons as part of the build. This construct
    allows, primarily, for build flags to be set independently for debug and
    release versions of a project.
"""

import fnmatch
import os
import sys

from SCons.Errors import StopError, UserError
from SCons.Script import AddOption, GetOption, Flatten, SConscript
from SCons.Node.FS import Base as SConsFSBase


# ---------------------------------------------------------
#   General Utility
# ---------------------------------------------------------

def _get_project_dir(env):
    """
    Retrieve the absolute path of the project (i.e. SConstruct) directory.
    """
    project_dir = env.Dir('.').srcnode().abspath
    while not os.path.exists(os.path.join(project_dir, 'SConstruct')):
        parent_dir = os.path.normpath(os.path.join(project_dir, os.path.pardir))
        if parent_dir == project_dir:
            raise StopError('Could not find project root (i.e. SConstruct).')
        project_dir = parent_dir
    return project_dir


# ---------------------------------------------------------
#   Variants
# ---------------------------------------------------------

def _set_variant(env, variant):
    """
    Set the variant (e.g. debug or release) that is being built.
    """
    env['X_BUILD_VARIANT'] = variant

def _get_variant(env):
    """
    Retrieve the current build variant (e.g. debug or release).
    """
    return env['X_BUILD_VARIANT']

AddOption(
    '--release',
    action='store_true',
    help='Build release variant.',
    default=False)


# ---------------------------------------------------------
#   Exports
# ---------------------------------------------------------

def _is_excluded(name, exclude):
    """
    Return true if given name matches the exclude list.
    """
    if not exclude:
        return False
    return any((fnmatch.fnmatchcase(name, i) for i in exclude))

def _is_globbed(name, glob):
    """
    Return true if given name matches the glob list.
    """
    if not glob:
        return True
    return any((fnmatch.fnmatchcase(name, i) for i in glob))

def _get_files(target, source, exclude, glob, recurse):
    """
    Resolve contents of install sources that are directories.
    """
    spath = os.path.normpath(str(source))
    tpath = os.path.normpath(target.abspath)

    if not os.path.isdir(spath):
        return [(os.path.join(tpath, os.path.basename(spath)), spath)]

    results = []
    for (root, dirs, files) in os.walk(spath):
        reldir = root[len(spath):]
        while reldir and reldir[0] == os.sep:
            reldir = reldir[1:]
        if reldir:
            destdir = os.path.join(tpath, reldir)
        else:
            destdir = tpath

        for i in files:
            if _is_excluded(i, exclude):
                continue
            if not _is_globbed(i, glob):
                continue
            results.append((os.path.join(destdir, i), os.path.join(root, i)))

        i = 0
        while i < len(dirs):
            if recurse and not _is_excluded(dirs[i], exclude):
                i += 1
            else:
                del dirs[i]

    return results

def _install_files(env, target, source, exclude=None, glob=None, recurse=True):
    """
    Install the given source paths to the given target location(s).
    """
    if exclude is None:
        exclude = []
    exclude = Flatten([exclude])
    exclude.extend(['.*', '*~', '*.pyc', '*.o', '*.os'])

    if glob is None:
        glob = []
    glob = Flatten([glob])

    target = Flatten([target])
    source = Flatten([source])
    if len(target) != len(source):
        if len(target) == 1:
            target = target * len(source)
        else:
            raise UserError('Export files mismatch')

    results = []
    for (t, s) in zip(target, source):
        if not isinstance(t, SConsFSBase):
            t = env.Dir(t)
        if not isinstance(s, SConsFSBase):
            s = env.Entry(s)
        for (dest, src) in _get_files(t, s, exclude, glob, recurse):
            results.extend(env.InstallAs(dest, src))
    return results

def _get_export_dir(env):
    """
    Return the export directory path.
    """
    # 'export/variant' directory at the project root
    return os.path.join(_get_project_dir(env), 'export', _get_variant(env))

def _export_bin(env, source):
    """
    Export the given files to 'bin'.
    """
    bin_dir = os.path.join(_get_export_dir(env), 'bin')
    return _install_files(env, bin_dir, source, recurse=False)

def _export_lib(env, source):
    """
    Export the given files to 'lib'.
    """
    lib_dir = os.path.join(_get_export_dir(env), 'lib')
    return _install_files(env, lib_dir, source, recurse=False)

def _export_include(env, source, prefix=''):
    """
    Export the given files to 'include'.
    """
    include_dir = os.path.join(_get_export_dir(env), 'include', prefix)
    return _install_files(env, include_dir, source)


# ---------------------------------------------------------
#   Quick Build
# ---------------------------------------------------------

def _get_unit_name(env, unit=None):
    """
    Retrieve the full name (relative path from the project root) of a unit.

    A 'unit' is an buildable component that can be referenced and required
    as a dependency of another buildable component. Although Sconscripts can
    reference other units by a shortened path, internally they are
    referenced using the relative path from the root to avoid conflicts.

    If the unit keyword parameter is not given then the name of the unit
    calling this function is returned.
    """
    # Given unit name can be given in shortened form. Search from the
    # current directory to find the intended unit.
    start_dir = env.Dir('.').srcnode().abspath

    # Determine the name of the calling unit when none is given.
    if unit is None:
        unit = os.path.basename(start_dir)

    # Find the unit and return the name (relative path from the root).
    root_dir = _get_project_dir(env)
    unit = unit.replace('/', os.path.sep)
    search_dir = start_dir
    while True:
        unit_dir = os.path.join(search_dir, unit)
        if os.path.exists(os.path.join(unit_dir, 'SConscript')):
            return os.path.relpath(unit_dir, root_dir)
        if search_dir == root_dir:
            raise StopError('Could not find unit %s' % unit)
        search_dir = os.path.normpath(os.path.join(search_dir, os.path.pardir))

def _build_units(env, units):
    """
    For each given unit, check the build manifest to see if it has been
    built. If not, execute the unit's SConscript.
    """
    project_dir = _get_project_dir(env)
    for unit in Flatten([units]):
        unit_name = _get_unit_name(env, unit)
        if env['X_BUILD_MANIFEST'].has_key(unit_name):
            continue
        unit_dir = os.path.join(project_dir, unit_name)
        variant_dir = os.path.join(
            project_dir,
            'build',
            _get_variant(env),
            unit_name)
        SConscript(
            dirs=unit_dir,
            exports='env',
            variant_dir=variant_dir,
            duplicate=0)
        # Make sure that the build manifest has been updated.
        if not env['X_BUILD_MANIFEST'].has_key(unit_name):
            env['X_BUILD_MANIFEST'][unit_name] = {}

def _build_deps(env, bld_env, deps):
    """
    Update the current unit's build environment with dependency results.
    Trigger their builds if necessary.
    """
    if deps:
        for dep in deps:
            dep_name = _get_unit_name(env, dep)
            if not env['X_BUILD_MANIFEST'].has_key(dep_name):
                _build_units(env, dep)
            settings = env['X_BUILD_MANIFEST'][dep_name]
            bld_env.AppendUnique(**settings)

def _manifest_build_settings(env, settings):
    """
    Store the build settings (compiler/linker flags, include paths etc...)
    that dependent units need to use to build against a given dependency.
    """
    env['X_BUILD_MANIFEST'][_get_unit_name(env)] = settings

def _quick_name(env, name):
    """
    Quick-build helper function to name the build result.
    """
    # Without a provided name, name the result based on the unit directory.
    if name is None:
        name = os.path.basename(env.Dir('.').srcnode().path)
    return name

def _quick_glob(env):
    """
    Quick-build helper function to glob source files.
    """
    return [env.Glob('src/*.' + ext) for ext in ['c', 'cpp', 'cc']]

def _quick_program(env, name=None, deps=None):
    """
    Quick-build a program that uses the standard hierarchy.
    """
    bld_env = env.Clone()

    # Build dependencies, update build environment with results.
    _build_deps(env, bld_env, deps)

    # Add local headers to build environment.
    bld_env.AppendUnique(CPPPATH=[env.Dir(x).srcnode() for x in ['inc', 'src']])

    # Create the program.
    return bld_env.Program(_quick_name(bld_env, name), _quick_glob(bld_env))

def _quick_static_lib(env, name=None, deps=None):
    """
    Quick-build a static library that uses the standard hierarchy.
    """
    bld_env = env.Clone()

    # Build dependencies, update build environment with results.
    _build_deps(env, bld_env, deps)

    # Add local headers to build environment.
    bld_env.AppendUnique(CPPPATH=[env.Dir(x).srcnode() for x in ['inc', 'src']])

    # Create the library.
    name = _quick_name(env, name)
    env.ManifestBuildSettings(
        {
            'CPPPATH' : [env.Dir('inc').srcnode()],
            'LIBS' :    [name],
            'LIBPATH' : [env.Dir('.')],
        })
    return bld_env.StaticLibrary(name, _quick_glob(bld_env))

def _quick_shared_lib(env, name=None, deps=None):
    """
    Quick-build a shared library that uses the standard hierarchy.
    """
    bld_env = env.Clone()

    # Build dependencies, update build environment with results.
    _build_deps(env, bld_env, deps)

    # Add local headers to the build environment.
    bld_env.AppendUnique(CPPPATH=[env.Dir(x).srcnode() for x in ['inc', 'src']])

    # Create the library.
    name = _quick_name(env, name)
    env.ManifestBuildSettings(
        {
            'CPPPATH' : [env.Dir('inc').srcnode()],
            'LIBS' :    [name],
            'LIBPATH' : [env.Dir('.')],
        })
    return bld_env.SharedLibrary(name, _quick_glob(bld_env))


# ---------------------------------------------------------
#   Environment Setup
# ---------------------------------------------------------

def _set_default_build_configuration(env):
    """
    Default build environment. Can be overridden after Enable().
    """
    env.Decider('MD5-timestamp')
    env.AppendUnique(
        CCFLAGS=[
            '-Wall',
            '-Wextra',
            '-Wpedantic',
            '-Werror',
        ])

    if _get_variant(env) == 'debug':
        env.AppendUnique(
            CCFLAGS=[
                '-O0',
                '-g',
            ])
    else:
        env.AppendUnique(
            CCFLAGS=[
                '-O3',
                '-fvisibility=hidden',
            ],
            LINKFLAGS=[
                '-Wl,--strip-all',
            ])

def _set_output_colors(env):
    """
    Colorize build output if available.
    """
    if not sys.stdout.isatty():
        return
    cyan = '\033[96m'
    purple = '\033[95m'
    blue = '\033[94m'
    green = '\033[92m'
    yellow = '\033[93m'
    red = '\033[91m'
    nocolor = '\033[0m'
    env['ARCOMSTR'] = \
        '%sArchiving %s$TARGET%s\n$ARCOM' % (cyan, yellow, nocolor)
    env['ASCOMSTR'] = \
        '%sAssembling %s$SOURCE %s==> %s$TARGET%s\n$ASCOM' % \
            (blue, green, purple, yellow, nocolor)
    env['ASPCOMSTR'] = \
        '%sAssembling %s$SOURCE %s==> %s$TARGET%s\n$ASPCOM' % \
            (blue, green, purple, yellow, nocolor)
    env['CCCOMSTR'] = \
        '%sCompiling %s$SOURCE %s==> %s$TARGET%s\n$CCCOM' % \
            (blue, green, purple, yellow, nocolor)
    env['CXXCOMSTR'] = \
        '%sCompiling %s$SOURCE %s==> %s$TARGET%s\n$CXXCOM' % \
            (blue, green, purple, yellow, nocolor)
    env['INSTALLSTR'] = \
        '%sInstalling %s$SOURCE %s==> %s$TARGET%s' % \
            (cyan, nocolor, purple, yellow, nocolor)
    env['LINKCOMSTR'] = \
        '%sLinking %s==> %s$TARGET%s\n$LINKCOM' % \
            (red, purple, yellow, nocolor)
    env['RANLIBCOMSTR'] = \
        '%sIndexing %s==> %s$TARGET%s\n$RANLIBCOM' % \
            (red, purple, yellow, nocolor)
    env['SHCCCOMSTR'] = \
        '%sCompiling Shared %s$SOURCE %s==> %s$TARGET%s\n$SHCCCOM' % \
            (blue, green, purple, yellow, nocolor)
    env['SHCXXCOMSTR'] = \
        '%sCompiling Shared %s$SOURCE %s==> %s$TARGET%s\n$SHCXXCOM' % \
            (blue, green, purple, yellow, nocolor)
    env['SHLINKCOMSTR'] = \
        '%sLinking Shared Library %s==> %s$TARGET%s\n$SHLINKCOM' % \
            (red, purple, yellow, nocolor)


# ---------------------------------------------------------
#   Start It Up!
# ---------------------------------------------------------

def Enable(env):
    _set_variant(env, {True:'release', False:'debug'}[GetOption('release')])
    _set_default_build_configuration(env)
    _set_output_colors(env)

    env['X_BUILD_MANIFEST'] = {}

    env.AddMethod(_get_project_dir, 'GetProjectRoot')
    env.AddMethod(_get_variant, 'GetVariant')
    env.AddMethod(_install_files, 'InstallFiles')
    env.AddMethod(_export_bin, 'ExportBin')
    env.AddMethod(_export_lib, 'ExportLib')
    env.AddMethod(_export_include, 'ExportInclude')
    env.AddMethod(_manifest_build_settings, 'ManifestBuildSettings')
    env.AddMethod(_build_units, 'QuickBuild')
    env.AddMethod(_quick_program, 'QuickProgram')
    env.AddMethod(_quick_static_lib, 'QuickStaticLib')
    env.AddMethod(_quick_shared_lib, 'QuickSharedLib')

