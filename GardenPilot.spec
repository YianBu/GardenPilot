# -*- mode: python ; coding: utf-8 -*-

from PyInstaller.utils.hooks import collect_all

datas = [("assets", "assets")]
binaries = []
hiddenimports = []

for package in ("onnxocr", "openvino"):
    package_datas, package_binaries, package_hidden = collect_all(package)
    datas += package_datas
    binaries += package_binaries
    hiddenimports += package_hidden

# Let Windows supply the VC/UCRT runtime: the ones bundled by some wheels are
# older than what Qt 6.12 expects and cause "DLL load failed" at startup.
blocked_prefixes = (
    "vcruntime140",
    "msvcp140",
    "api-ms-win-",
    "ucrtbase",
    "icuuc",
    "icudt",
    "icuin",
    "zlib1",
)

a = Analysis(
    ["garden_app.py"],
    pathex=[],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
)

a.binaries = [item for item in a.binaries if not item[0].lower().startswith(blocked_prefixes)]

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="GardenPilot",
    debug=False,
    strip=False,
    upx=False,
    console=False,
    icon="assets/icon.png",
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    name="GardenPilot",
)
