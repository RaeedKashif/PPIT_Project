# -*- mode: python ; coding: utf-8 -*-
# Windows build spec for Image-to-Word Converter
# Run with: pyinstaller windows.spec  (from inside phase1/)

block_cipher = None

a = Analysis(
    ['main.py'],
    pathex=[],
    binaries=[
        # Conda puts Tcl/Tk DLLs in Library\bin rather than DLLs, so PyInstaller misses them
        (r'C:\Users\Shekhani Laptops\anaconda3\Library\bin\tcl86t.dll', '.'),
        (r'C:\Users\Shekhani Laptops\anaconda3\Library\bin\tk86t.dll', '.'),
    ],
    datas=[],
    hiddenimports=[
        'pytesseract',
        'cv2',
        'PIL',
        'PIL.Image',
        'PIL.ImageTk',
        'docx',
        'docx.oxml',
        'docx.oxml.ns',
        'numpy',
        'lxml',
        'lxml.etree',
        'lxml._elementpath',
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
    [],
    exclude_binaries=True,
    name='ImageToWordConverter',
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
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='ImageToWordConverter',
)
