# PyInstaller recipe for the Windows desktop app. Build with desktop/build.ps1.
#
# Our own code (doctor_prospector, backend app, migrations, scripts) is shipped
# as plain source files in the repo layout rather than inside PyInstaller's
# archive: the source registry discovers plugins by scanning its folder,
# Alembic loads migrations by file path, and refresh_all runs scripts by path.
# PyInstaller still analyses that code (hiddenimports below) so every
# third-party library it uses gets bundled.
# ruff: noqa

import os
from pathlib import Path

from PyInstaller.utils.hooks import collect_submodules

ROOT = Path(SPECPATH).parent

OWN_PACKAGES = ("doctor_prospector", "app", "src")
OWN_MODULES = {
    # repo scripts that refresh_all runs by path
    "discover_non_tvt_hospitals", "download_cms_data", "full_scrape_tvt",
    "refresh_all", "refresh_cache", "import_puf", "history_seed", "db",
}

hiddenimports = (
    collect_submodules("doctor_prospector")
    + collect_submodules("app")
    + sorted(OWN_MODULES)
    # loaded by name at runtime (uvicorn, SQLAlchemy dialects, passlib)
    + collect_submodules("uvicorn")
    + ["aiosqlite", "sqlalchemy.dialects.sqlite.aiosqlite", "sqlalchemy.dialects.sqlite.pysqlite",
       "passlib.handlers.bcrypt", "email_validator", "multipart"]
)


def tree(src: str, dest: str):
    """(file, folder) pairs for a source tree, skipping caches."""
    out = []
    base = ROOT / src
    for path in base.rglob("*"):
        if path.is_file() and "__pycache__" not in path.parts and path.suffix != ".pyc":
            out.append((str(path), str(Path(dest) / path.relative_to(base).parent)))
    return out


datas = (
    tree("src/doctor_prospector", "src/doctor_prospector")
    + tree("backend/app", "backend/app")
    + tree("backend/alembic", "backend/alembic")
    + [(str(ROOT / "backend/alembic.ini"), "backend")]
    + [(str(p), "scripts") for p in (ROOT / "scripts").glob("*.py")]
    + [(str(ROOT / f), ".") for f in ("discover_non_tvt_hospitals.py", "download_cms_data.py",
                                      "full_scrape_tvt.py", "config.yaml", ".env.example", "LICENSE")]
    + tree("frontend/dist", "frontend/dist")
    + tree("data/seed", "data/seed")
    + tree("data/cms_historical", "data/cms_historical")
    + [(str(ROOT / "data/output/all_hospitals.json"), "data/output"),
       (str(ROOT / "data/output/cms_discovered_hospitals.json"), "data/output")]
)

a = Analysis(
    [str(ROOT / "desktop" / "launcher.py")],
    pathex=[str(ROOT / "src"), str(ROOT / "backend"), str(ROOT / "scripts"), str(ROOT)],
    hiddenimports=hiddenimports,
    datas=datas,
    excludes=["tkinter", "matplotlib", "IPython", "pytest", "streamlit"],
    noarchive=False,
)


def is_own(name: str) -> bool:
    top = name.split(".")[0]
    return top in OWN_PACKAGES or name in OWN_MODULES


# Keep third-party code in the archive; drop our modules (shipped as files above)
a.pure = [entry for entry in a.pure if not is_own(entry[0])]

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="DoctorProspector",
    icon=str(ROOT / "desktop" / "icon.ico"),
    version=str(ROOT / "build" / "version_info.txt"),
    console=False,  # windowed app; --refresh opens its own console
    upx=False,
)

coll = COLLECT(exe, a.binaries, a.datas, name="DoctorProspector", upx=False)
