# -*- mode: python ; coding: utf-8 -*-
"""
PyInstaller spec for ClassAssistant Backend
Bundles FastAPI + all service modules into a single directory

v1.1.1 note:
- `routers.rescue_router` is kept below only as a legacy residue for compatibility review.
- New teacher-mode features should target `question_router` instead of extending `rescue_router`.
"""

import os
import sys

from PyInstaller.utils.hooks import collect_submodules

block_cipher = None

router_hiddenimports = sorted(set(collect_submodules('routers')))
service_hiddenimports = sorted(set(collect_submodules('services')))

# Collect all service and router Python files as data
a = Analysis(
    ['main.py'],
    pathex=['.'],
    binaries=[],
    datas=[
        ('.env.example', '.'),
    ],
    hiddenimports=[
        'uvicorn',
        'uvicorn.logging',
        'uvicorn.loops',
        'uvicorn.loops.auto',
        'uvicorn.protocols',
        'uvicorn.protocols.http',
        'uvicorn.protocols.http.auto',
        'uvicorn.protocols.websockets',
        'uvicorn.protocols.websockets.auto',
        'uvicorn.lifespan',
        'uvicorn.lifespan.on',
        'uvicorn.lifespan.off',
        'fastapi',
        'starlette',
        'starlette.routing',
        'starlette.responses',
        'starlette.middleware',
        'starlette.middleware.cors',
        'pydantic',
        'multipart',
        'python_multipart',
        'config',
        'pyaudio',
        'pptx',
        'pypdf',
        'docx',
        'openai',
        'httpx',
        'httpcore',
        'anyio',
        'certifi',
        'sniffio',
        'dotenv',
        'websocket',
        'gzip',
        'aiofiles',
        'httptools',
        'websockets',
        'speech_recognition',
    ] + router_hiddenimports + service_hiddenimports,
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
    name='class-assistant-backend',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    icon=None,
)

# Filter out corrupted DLLs picked up from tesseract on system PATH
excluded_dlls = {'libfribidi-0.dll'}
filtered_binaries = [b for b in a.binaries if b[0].lower() not in excluded_dlls]

coll = COLLECT(
    exe,
    filtered_binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='class-assistant-backend',
)
