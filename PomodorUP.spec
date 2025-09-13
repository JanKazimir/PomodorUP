# -*- mode: python ; coding: utf-8 -*-

block_cipher = None

a = Analysis(
    ['test.py'],
    pathex=[],
    binaries=[],
    datas=[('assets/fonts/*', 'assets')],
    hiddenimports=[
        'pystray._darwin',
        'pystray._appindicator',
        'pystray._base',
        'pystray._util',
        'PIL._tkinter_finder',
        'PIL.Image',
        'PIL.ImageDraw',
        'PIL.ImageFont',
        'Cocoa',
        'Foundation',
        'AppKit',
        'Quartz',
        'objc',
        'PyObjCTools',
        'CoreFoundation',
        'CoreGraphics',
        'CoreVideo',
        'ImageIO',
        'ImageKit',
        'PDFKit',
        'QuartzComposer',
        'QuartzCore',
        'QuartzFilters',
        'QuickLookUI',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name='PomodorUP',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

app = BUNDLE(
    exe,
    name='PomodorUP.app',
    icon='assets/PomodorUP.icns',
    bundle_identifier='com.pomodorup.app',
    info_plist={
        'LSUIElement': True,  # Hide from Dock, show only in menu bar
        'CFBundleName': 'PomodorUP',
        'CFBundleDisplayName': 'PomodorUP',
        'CFBundleVersion': '1.0.0',
        'CFBundleShortVersionString': '1.0.0',
        'NSHighResolutionCapable': True,
    },
)