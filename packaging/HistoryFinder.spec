from pathlib import Path


project_root = Path(SPECPATH).parent

datas = [
    (str(project_root / "player" / "dist"), "player/dist"),
    (str(project_root / "viewer" / "static"), "viewer/static"),
    (str(project_root / "data" / "research_catalog.json"), "data"),
]

a = Analysis(
    [str(project_root / "release_launcher.py")],
    pathex=[str(project_root)],
    binaries=[],
    datas=datas,
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        "IPython",
        "PIL",
        "PyQt5",
        "llama_cpp",
        "matplotlib",
        "pandas",
        "psutil",
        "pygame",
        "pygments",
        "pytest",
        "scipy",
        "tkinter",
    ],
    noarchive=False,
    optimize=1,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="HistoryFinder",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    version=str(project_root / "packaging" / "version_info.txt"),
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name="HistoryFinder",
)
