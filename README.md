quickscons
==========

Wrapper around SCons to simplify SConstruct and SConscript files assuming that
some basic project hierarchy standards are followed.

Getting Started
---------------

The quickscons Python package should be placed in your site_scons directory.

quickc
------

Wrapper to simplify SConstruct and SConscript files for C/C++ projects.
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

The following methods are added to the SCons environment:

* env.GetProjectRoot()
* env.GetVariant()
* env.InstallFiles()
* env.ExportBin()
* env.ExportLib()
* env.ExportInclude()
* env.ManifestBuildSettings()
* env.QuickBuild()
* env.QuickProgram()
* env.QuickStaticLib()
* env.QuickSharedLib()

License
-------

This project is licensed under The MIT License.

Note that this project is used to build other software that MAY or MAY NOT be
licensed under the same terms as this project. Use of this project does not
have any implications on the licensing terms of any other software that makes
use of this project.

