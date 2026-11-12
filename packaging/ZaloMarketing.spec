# -*- mode: python ; coding: utf-8 -*-
# Build:  pyinstaller packaging/ZaloMarketing.spec --noconfirm
import os

import re

ROOT = os.path.abspath(os.path.join(SPECPATH, ".."))

# Sinh thông tin phiên bản cho file .exe từ zalo_marketing/__init__.py
with open(os.path.join(ROOT, "zalo_marketing", "__init__.py"), encoding="utf-8") as _f:
    VERSION = re.search(r'__version__\s*=\s*"([^"]+)"', _f.read()).group(1)
_nums = (VERSION.split(".") + ["0", "0", "0"])[:4]
with open(os.path.join(SPECPATH, "version_info.txt"), encoding="utf-8") as _f:
    _vi = _f.read().replace("1, 0, 0, 0", ", ".join(_nums)).replace("'1.0.0'", repr(VERSION))
VERSION_FILE = os.path.join(workpath, "version_info.generated.txt")
os.makedirs(workpath, exist_ok=True)
with open(VERSION_FILE, "w", encoding="utf-8") as _f:
    _f.write(_vi)

a = Analysis(
    [os.path.join(ROOT, "run_app.py")],
    pathex=[ROOT],
    datas=[(os.path.join(ROOT, "zalo_marketing", "ui", "assets"), "zalo_marketing/ui/assets")],
    hiddenimports=[],
    excludes=[
        "tkinter", "pytest",
        "PySide6.QtWebEngineCore", "PySide6.QtWebEngineWidgets", "PySide6.QtWebEngineQuick",
        "PySide6.Qt3DCore", "PySide6.Qt3DRender", "PySide6.QtQuick", "PySide6.QtQml",
        "PySide6.QtMultimedia", "PySide6.QtCharts", "PySide6.QtDataVisualization",
        "PySide6.QtPdf", "PySide6.QtBluetooth", "PySide6.QtPositioning", "PySide6.QtSensors",
    ],
    noarchive=False,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="ZaloMarketing",
    console=False,
    icon=os.path.join(ROOT, "packaging", "icon.ico"),
    version=VERSION_FILE,
    upx=False,
)
coll = COLLECT(exe, a.binaries, a.datas, name="ZaloMarketing", upx=False)
