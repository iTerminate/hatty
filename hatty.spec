# PyInstaller spec — build with: uv run pyinstaller --noconfirm hatty.spec
from PyInstaller.utils.hooks import collect_submodules

# hatty: the dashboard widget factory table resolves widget modules via
# importlib.import_module, which static analysis can't trace.
# textual.widgets: Textual lazy-loads widget submodules the same way.
hiddenimports = collect_submodules("hatty") + collect_submodules("textual.widgets")

a = Analysis(
    ["src/hatty/__main__.py"],
    pathex=["src"],
    binaries=[],
    datas=[],
    hiddenimports=hiddenimports,
    hookspath=[],
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="hatty",
    debug=False,
    strip=False,
    upx=False,
    console=True,
)
