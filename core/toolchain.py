"""Locate the native Yosys / SBY / Yices toolchain.

The prototype used to rely on the ``uarchifi`` Docker image.  The miter flow
now only needs the standard Yosys ecosystem, so the same code can run in a
native OSS CAD Suite installation or inside the Docker image.

Search order for every executable:

1. ``FORMACUT_<TOOL>`` environment variable (exact executable path).
2. ``FORMACUT_TOOLCHAIN`` environment variable (a ``bin`` directory or the
   OSS CAD Suite root directory).
3. ``PATH``.
4. A few well-known OSS CAD Suite installation directories.
"""

import os
import shutil


def _exe_name(name):
    return name + ".exe" if os.name == "nt" else name


def _candidate_dirs():
    dirs = []

    root = os.environ.get("FORMACUT_TOOLCHAIN")
    if root:
        dirs.append(root)
        dirs.append(os.path.join(root, "bin"))

    dirs.extend([
        r"D:\EDA\oss-cad-suite\bin",
        r"C:\EDA\oss-cad-suite\bin",
        r"C:\oss-cad-suite\bin",
        "/opt/oss-cad-suite/bin",
        "/usr/local/bin",
        "/usr/bin",
    ])
    return dirs


def find_tool(name):
    """Return the absolute path of *name*, or ``None`` when it is missing."""
    override = os.environ.get("FORMACUT_" + name.upper().replace("-", "_"))
    if override:
        if os.path.isfile(override):
            return os.path.abspath(override)
        found = shutil.which(override)
        if found:
            return found

    found = shutil.which(name)
    if found:
        return found

    for directory in _candidate_dirs():
        for filename in (name, _exe_name(name)):
            candidate = os.path.join(directory, filename)
            if os.path.isfile(candidate):
                return os.path.abspath(candidate)
    return None


def get_env():
    """Environment for Yosys/SBY subprocesses.

    SBY launches ``yosys`` and ``yosys-smtbmc`` itself, so the directory that
    contains ``sby`` has to be on ``PATH`` even when the scripts are invoked by
    their absolute path.
    """
    env = os.environ.copy()
    bin_dirs = []

    for tool in ("yosys", "sby", "yosys-smtbmc", "yices-smt2"):
        path = find_tool(tool)
        if not path:
            continue
        directory = os.path.dirname(os.path.abspath(path))
        if directory not in bin_dirs:
            bin_dirs.append(directory)
        # OSS CAD Suite keeps its runtime DLLs in <suite>/lib; Yosys.exe needs
        # them on PATH on Windows.
        lib_dir = os.path.join(os.path.dirname(directory), "lib")
        if os.path.isdir(lib_dir) and lib_dir not in bin_dirs:
            bin_dirs.append(lib_dir)

    if bin_dirs:
        env["PATH"] = os.pathsep.join(bin_dirs + [env.get("PATH", "")])
    return env


def require_tool(name):
    path = find_tool(name)
    if not path:
        raise RuntimeError(
            "找不到 {}。请安装 OSS CAD Suite，或设置环境变量 "
            "FORMACUT_TOOLCHAIN 指向它的 bin 目录。".format(name)
        )
    return path
