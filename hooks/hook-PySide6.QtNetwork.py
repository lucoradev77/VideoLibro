import os

from PyInstaller.utils.hooks.qt import add_qt6_dependencies


hiddenimports, binaries, datas = add_qt6_dependencies(__file__)

# Qt prefers its OpenSSL backend on Windows; use the bundled Schannel backend
# instead and keep Python's separately bundled OpenSSL pair for Python HTTPS.
binaries = [
    binary for binary in binaries
    if os.path.basename(binary[0]).lower() != "qopensslbackend.dll"
]
