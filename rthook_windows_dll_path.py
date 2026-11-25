"""Prefer the DLLs bundled with the frozen app over system copies."""

import os
import sys


if sys.platform == "win32" and hasattr(os, "add_dll_directory"):
    # PyInstaller extracts one-file binaries into _MEIPASS. Register that
    # directory and put it first on PATH before QtNetwork/OpenSSL imports any
    # of its dependencies. Qt's libssl and libcrypto must come from the same
    # PySide6 bundle; another copy already on PATH can otherwise be paired
    # with the wrong DLL and produce a missing CRYPTO_malloc error at startup.
    bundle_dir = sys._MEIPASS
    os.environ["PATH"] = bundle_dir + os.pathsep + os.environ.get("PATH", "")
    os.add_dll_directory(bundle_dir)
