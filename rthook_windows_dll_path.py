"""Prefer the DLLs bundled with the frozen app over system copies."""

import os
import sys


if sys.platform == "win32" and hasattr(os, "add_dll_directory"):
    # PyInstaller extracts one-file binaries into _MEIPASS. Register that
    # directory before QtNetwork/OpenSSL imports any of its dependencies.
    os.add_dll_directory(sys._MEIPASS)
