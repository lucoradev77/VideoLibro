"""Prefer the DLLs bundled with the frozen app over system copies."""

import ctypes
import os
import sys


if sys.platform == "win32" and hasattr(os, "add_dll_directory"):
    # PyInstaller extracts one-file binaries into _MEIPASS. Register that
    # directory and put it first on PATH before QtNetwork/OpenSSL imports any
    # of its dependencies. Preload the matching OpenSSL pair from the Python
    # runtime so Qt cannot pick up an incompatible copy from System32.
    bundle_dir = sys._MEIPASS
    os.environ["PATH"] = bundle_dir + os.pathsep + os.environ.get("PATH", "")
    _dll_directory_handle = os.add_dll_directory(bundle_dir)
    _openssl_handles = (
        ctypes.WinDLL(os.path.join(bundle_dir, "libcrypto-3-x64.dll")),
        ctypes.WinDLL(os.path.join(bundle_dir, "libssl-3-x64.dll")),
    )
