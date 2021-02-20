# -*- mode: python ; coding: utf-8 -*-

import os
import platform
import re

block_cipher = None

datas_dict = list()
datas_dict.append((os.path.join('res', 'bgg_ludo.png'), 'res'))

# Get all qt platform files
virtual_env_dir = os.environ['VIRTUAL_ENV']
qt_plugin_platform_dir = os.path.join(virtual_env_dir, 'Lib', 'site-packages', 'PySide6', 'plugins', 'platforms')
plugin_platform_dest = os.path.join('plugins', 'platforms')
for _, _, files in os.walk(qt_plugin_platform_dir):
    for file in files:
        datas_dict.append((os.path.join(qt_plugin_platform_dir, file), plugin_platform_dest))

# Choose icon file to use for the binary
icon = os.path.join('res', 'bgg_ludo.ico') if platform.system() == 'Windows' else os.path.join('res', 'bgg_ludo.icns')

a = Analysis(['importador.py'],
             pathex=[os.getcwd()],
             binaries=[],
             datas=datas_dict,
             hiddenimports=[],
             hookspath=[],
             runtime_hooks=[],
             excludes=[],
             win_no_prefer_redirects=False,
             win_private_assemblies=False,
             cipher=block_cipher,
             noarchive=False)
pyz = PYZ(a.pure, a.zipped_data,
             cipher=block_cipher)
exe = EXE(pyz,
          a.scripts,
          a.binaries,
          a.zipfiles,
          a.datas,
          [],
          name='importador',
          debug=False,
          bootloader_ignore_signals=False,
          strip=False,
          upx=True,
          upx_exclude=[],
          runtime_tmpdir=None,
          console=False,
          icon=icon)
