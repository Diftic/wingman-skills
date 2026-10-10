# -*- mode: python ; coding: utf-8 -*-


a = Analysis(
    ['C:\\Users\\larse\\PycharmProjects\\Wingman-ai_developer\\tools\\installer\\installer.py'],
    pathex=[],
    binaries=[],
    datas=[('C:\\Users\\larse\\PycharmProjects\\Wingman-ai_developer\\skills\\sc_log_reader\\release_version\\__init__.py', '.'), ('C:\\Users\\larse\\PycharmProjects\\Wingman-ai_developer\\skills\\sc_log_reader\\release_version\\debug_emitter.py', '.'), ('C:\\Users\\larse\\PycharmProjects\\Wingman-ai_developer\\skills\\sc_log_reader\\release_version\\default_config.yaml', '.'), ('C:\\Users\\larse\\PycharmProjects\\Wingman-ai_developer\\skills\\sc_log_reader\\release_version\\ledger.py', '.'), ('C:\\Users\\larse\\PycharmProjects\\Wingman-ai_developer\\skills\\sc_log_reader\\release_version\\location_names.py', '.'), ('C:\\Users\\larse\\PycharmProjects\\Wingman-ai_developer\\skills\\sc_log_reader\\release_version\\logic.py', '.'), ('C:\\Users\\larse\\PycharmProjects\\Wingman-ai_developer\\skills\\sc_log_reader\\release_version\\logo.png', '.'), ('C:\\Users\\larse\\PycharmProjects\\Wingman-ai_developer\\skills\\sc_log_reader\\release_version\\main.py', '.'), ('C:\\Users\\larse\\PycharmProjects\\Wingman-ai_developer\\skills\\sc_log_reader\\release_version\\parser.py', '.'), ('C:\\Users\\larse\\PycharmProjects\\Wingman-ai_developer\\skills\\sc_log_reader\\skill_installer_config.json', '.')],
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='SC_Log_Reader_Installer',
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
