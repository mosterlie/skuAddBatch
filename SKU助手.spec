# -*- mode: python ; coding: utf-8 -*-


a = Analysis(
    ['sku_desktop_app/main.py'],
    pathex=[],
    binaries=[],
    datas=[('sku_desktop_app/gui', 'sku_desktop_app/gui'), ('sku_desktop_app/core', 'sku_desktop_app/core'), ('sku_desktop_app/config.py', 'sku_desktop_app'), ('sku_desktop_app/main.py', 'sku_desktop_app')],
    hiddenimports=['PIL', 'PIL._tkinter_finder', 'tkinter'],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=['pygame'],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='SKU助手',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='SKU助手',
)
app = BUNDLE(
    coll,
    name='SKU助手.app',
    icon=None,
    bundle_identifier=None,
)
