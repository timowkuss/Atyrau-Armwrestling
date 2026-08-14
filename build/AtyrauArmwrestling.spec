# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec для AtyrauArmwrestling.exe.

Сборка:  pyinstaller build/AtyrauArmwrestling.spec --noconfirm
(проще — запускать build_installer.bat, который вызывает этот spec)

--onefile: один exe, распаковывается в %TEMP% при каждом запуске.
Данные (armwrestling.db, sync_state.db, photos/, backups/, photo_cache/)
живут в %APPDATA%\AtyrauArmwrestling (см. paths.py) — вне exe, writable.

Внутрь exe попадают: код, logo (assets/), sync_config.json (для API URL и
токена по умолчанию — его можно переопределить файлом рядом с exe или в
AppData; см. paths.config_file()).
"""

from pathlib import Path

BUILD = Path(SPECPATH).resolve()          # .../Armwrestling/build
ROOT = BUILD.parent / "desktop-app"       # .../Armwrestling/desktop-app

a = Analysis(
    [str(ROOT / "armwrestling_tournament.py")],
    pathex=[str(ROOT)],
    binaries=[],
    datas=[
        (str(ROOT / "assets" / "logo-atyrau-city.png"), "assets"),
        (str(ROOT / "sync_config.json"), "."),
    ],
    hiddenimports=[
        "customtkinter",
        "PIL._tkinter_finder",
        "flask",
        "flask.json",
        "werkzeug",
        "requests",
        "dotenv",
        "reportlab",
        "reportlab.graphics.barcode.code128",
        "club_rating",
        "ui_theme",
        "paths",
        "sync.config",
        "sync.state",
        "sync.api_client",
        "sync.sync_manager",
        "sync.pull_sync",
        "sync.photo_cache",
        "sync.cloudinary_client",
        "transfer.pack",
        "transfer.exporter",
        "transfer.importer",
        "transfer.backup_manager",
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["tkinter.test", "unittest", "pydoc"],
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="AtyrauArmwrestling",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,  # GUI-приложение без консольного окна
    disable_windowed_traceback=False,
    icon=str(BUILD / "AtyrauArmwrestling.ico"),
)
