# -*- mode: python ; coding: utf-8 -*-
from PyInstaller.utils.hooks import collect_submodules
from PyInstaller.utils.hooks import collect_all

datas = [('frontend/index.standalone.html', 'frontend'), ('frontend/index.html', 'frontend'), ('frontend/js', 'frontend/js'), ('frontend/css', 'frontend/css'), ('frontend/vendor', 'frontend/vendor'), ('frontend/tiptap-bundle.mjs', 'frontend'), ('backend/hooks_forward.py', 'backend'), ('backend/templates', 'backend/templates'), ('backend/AiClientConfig', 'backend/AiClientConfig')]
binaries = []
hiddenimports = []
hiddenimports += collect_submodules('yaml')
hiddenimports += collect_submodules('git')
hiddenimports += collect_submodules('aiosqlite')
hiddenimports += collect_submodules('multipart')
hiddenimports += collect_submodules('fastapi')
hiddenimports += collect_submodules('starlette')
tmp_ret = collect_all('uvicorn')
datas += tmp_ret[0]; binaries += tmp_ret[1]; hiddenimports += tmp_ret[2]
tmp_ret = collect_all('pydantic')
datas += tmp_ret[0]; binaries += tmp_ret[1]; hiddenimports += tmp_ret[2]
tmp_ret = collect_all('mcp')
datas += tmp_ret[0]; binaries += tmp_ret[1]; hiddenimports += tmp_ret[2]


a = Analysis(
    ['backend/desktop_server.py'],
    pathex=[],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=['matplotlib', 'PIL', 'lxml', 'jedi', 'numpy', 'gevent', 'pandas', 'scipy', 'IPython', 'pytest', 'tkinter'],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='myknowledge-backend',
    debug=False,
    bootloader_ignore_signals=False,
    strip=True,
    upx=True,
    console=True,
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
    strip=True,
    upx=True,
    upx_exclude=[],
    name='myknowledge-backend',
)
