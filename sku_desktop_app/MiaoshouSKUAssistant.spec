# -*- mode: python ; coding: utf-8 -*-
import os
import sys

block_cipher = None

app_dir = SPECPATH

datas = [
    (os.path.join(app_dir, 'web'), 'web'),
    (os.path.join(app_dir, 'assets'), 'assets'),
]

binaries = []

hiddenimports = [
    'tkinter',
    'tkinter.ttk',
    'tkinter.filedialog',
    'tkinter.messagebox',
    'requests',
    'urllib',
    'urllib.parse',
    'urllib.request',
    'json',
    'threading',
    'queue',
    'subprocess',
    'playwright',
    'playwright.sync_api',
    'core',
    'core.browser_manager',
    'core.executor',
    'core.parser',
    'core.scraper_1688',
    'core.login_helper',
    'core.plugin_server',
    'core.plugin_overlay_injector',
    'gui',
    'gui.app_window',
    'gui.preview_1688_dialog',
    'gui.floating_dock',
    'config',
]

a = Analysis(
    ['main.py'],
    pathex=[app_dir],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        'torch',
        'torchvision',
        'torchaudio',
        'paddle',
        'pyarrow',
        'cv2',
        'opencv_python',
        'onnxruntime',
        'scipy',
        'pandas',
        'pygame',
        'spacy',
        'matplotlib',
        'tokenizers',
        'transformers',
        'datasets',
        'timm',
        'mysql',
        'mysqlconnector',
        'sqlalchemy',
        'Cython',
        'pytest',
        'pytest_asyncio',
        'thinc',
        'srsly',
        'preshed',
        'blis',
        'safetensors',
        'tensorboard',
        'IPython',
        'jupyter',
        'notebook',
        'scikit-learn',
        'sklearn',
    ],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='MiaoshouSKUAssistant',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=os.path.join(app_dir, 'assets', 'AppIcon.icns'),
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name='MiaoshouSKUAssistant',
)

app = BUNDLE(
    coll,
    name='MiaoshouSKUAssistant.app',
    icon=os.path.join(app_dir, 'assets', 'AppIcon.icns'),
    bundle_identifier='com.miaoshou.skuassistant',
    info_plist={
        'CFBundleDisplayName': '跨境电商智能工作台',
        'CFBundleName': 'MiaoshouSKUAssistant',
        'CFBundleIdentifier': 'com.miaoshou.skuassistant',
        'CFBundleVersion': '1.0.0',
        'CFBundleShortVersionString': '1.0.0',
        'NSHighResolutionCapable': 'True',
        'LSMinimumSystemVersion': '10.13.0',
        'NSRequiresAquaSystemAppearance': 'False',
    },
)
