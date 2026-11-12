# -*- mode: python ; coding: utf-8 -*-
# Build:  pyinstaller packaging/ZaloMarketing.spec --noconfirm
import os

ROOT = os.path.abspath(os.path.join(SPECPATH, ".."))

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
    version=os.path.join(ROOT, "packaging", "version_info.txt"),
    upx=False,
)
coll = COLLECT(exe, a.binaries, a.datas, name="ZaloMarketing", upx=False)
