"""Doctor Prospector desktop launcher (Windows).

This is the entry point of the installed app (DoctorProspector.exe, built with
PyInstaller). It:

  1. Points the app's data at %LOCALAPPDATA%\\DoctorProspector (the install
     folder is read-only) and seeds it from the bundled data on first run
  2. Shows a native window right away (pywebview + Edge WebView2)
  3. Creates/migrates the SQLite database and imports the bundled physician
     history snapshot (first run only, a few seconds)
  4. Starts the API + web pages on a free localhost port and loads them
  5. Shuts the server down when the window closes

Other modes (also used by the Start-menu shortcuts):
  DoctorProspector.exe --refresh [refresh_all options]   refresh data in a console
  DoctorProspector.exe --data-folder                     open the data folder

Running from a source checkout works too, for development:
  python desktop/launcher.py
"""

import json
import logging
import logging.handlers
import os
import secrets
import shutil
import socket
import sys
import threading
import time
from pathlib import Path

APP_NAME = "Doctor Prospector"
FROZEN = getattr(sys, "frozen", False)
# Code + bundled files (PyInstaller unpacks them to sys._MEIPASS)
BUNDLE = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parents[1]))
# Writable data. Set before importing any app module: they read it at import.
CUSTOM_HOME = bool(os.environ.get("DOCTOR_PROSPECTOR_HOME"))
HOME = Path(os.environ.get("DOCTOR_PROSPECTOR_HOME") or Path(os.environ["LOCALAPPDATA"]) / "DoctorProspector")
os.environ["DOCTOR_PROSPECTOR_HOME"] = str(HOME)


def migrate_old_install() -> None:
    """Move data from the app's previous name (Doctor Grabby) on first run.

    The installer keeps the same AppId, so upgrading replaces the old app;
    this carries its data folder over and renames the files inside it.
    """
    old_home = Path(os.environ["LOCALAPPDATA"]) / "DoctorGrabby"
    if CUSTOM_HOME or HOME.exists() or not old_home.is_dir():
        return
    try:
        old_home.rename(HOME)
    except OSError:
        return  # e.g. old app still running; start fresh rather than fail
    renames = {
        "data/doctor_grabby.db": "data/doctor_prospector.db",
        "data/doctor_grabby.db-wal": "data/doctor_prospector.db-wal",
        "data/doctor_grabby.db-shm": "data/doctor_prospector.db-shm",
        "data/cache/tavr_prospector.db": "data/cache/doctor_prospector.db",
    }
    for old, new in renames.items():
        if (HOME / old).exists() and not (HOME / new).exists():
            (HOME / old).rename(HOME / new)
    env_file = HOME / ".env"
    if env_file.exists():
        text = env_file.read_text(encoding="utf-8")
        env_file.write_text(text.replace("doctor_grabby.db", "doctor_prospector.db"), encoding="utf-8")


migrate_old_install()

# Our code ships as plain source folders in the bundle (same layout as the repo)
for sub in ("src", "backend", "scripts", ""):
    path = str(BUNDLE / sub) if sub else str(BUNDLE)
    if path not in sys.path:
        sys.path.insert(0, path)

log = logging.getLogger("desktop")

# Files copied from the bundle into HOME. config.yaml and the hospital files are
# the user's to change (refresh_all rewrites the hospital files), so they're
# only replaced by a newer bundle if the user hasn't refreshed since.
SEED_FILES = [
    "config.yaml",
    "data/output/all_hospitals.json",
    "data/output/cms_discovered_hospitals.json",
]
SEED_DIRS = ["data/cms_historical"]


# ── setup ──────────────────────────────────────────────────────────────────

_log_handler: logging.Handler | None = None


def setup_logging(redirect_stdio: bool = True) -> Path:
    """Log to HOME/logs/app.log. Safe to call again: Alembic's fileConfig()
    replaces the root handlers during migrations, so the launcher re-attaches."""
    global _log_handler
    log_dir = HOME / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    log_file = log_dir / "app.log"
    if _log_handler is None:
        _log_handler = logging.handlers.RotatingFileHandler(
            log_file, maxBytes=5_000_000, backupCount=3, encoding="utf-8")
        _log_handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s [%(name)s] %(message)s"))
    root = logging.getLogger()
    root.setLevel(logging.INFO)
    if _log_handler not in root.handlers:
        root.addHandler(_log_handler)
    if FROZEN and redirect_stdio and not getattr(sys.stdout, "_doctor_prospector", False):
        # Windowed exe: stdout/stderr go nowhere (PyInstaller gives a dummy
        # stream). Capture print() and uvicorn's own output, tracebacks included.
        stream = open(log_dir / "console.log", "a", encoding="utf-8", buffering=1)
        stream._doctor_prospector = True
        sys.stdout = sys.stderr = stream
    return log_file


def _bundle_seed_version() -> str:
    try:
        return (BUNDLE / "data" / "seed" / "VERSION").read_text(encoding="utf-8").strip()
    except OSError:
        return "0"


def seed_home() -> None:
    """Create HOME on first run; refresh bundled data after an app update."""
    (HOME / "data").mkdir(parents=True, exist_ok=True)
    marker = HOME / "data" / ".seed_version"
    applied = marker.read_text(encoding="utf-8").strip() if marker.exists() else ""
    bundle_version = _bundle_seed_version()

    # A newer app version ships newer data, unless the user refreshed since
    last_refresh = HOME / "data" / "output" / "last_refresh.json"
    user_refreshed_after = False
    if last_refresh.exists() and applied:
        try:
            finished = json.loads(last_refresh.read_text(encoding="utf-8")).get("finished_at", "")
            user_refreshed_after = finished[:10] > applied
        except (OSError, ValueError):
            pass
    upgrade = bool(applied) and bundle_version > applied and not user_refreshed_after

    for rel in SEED_FILES:
        src, dst = BUNDLE / rel, HOME / rel
        if src.exists() and (not dst.exists() or (upgrade and rel != "config.yaml")):
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dst)
    for rel in SEED_DIRS:
        src, dst = BUNDLE / rel, HOME / rel
        if src.exists():
            dst.mkdir(parents=True, exist_ok=True)
            for f in src.iterdir():
                if f.is_file() and (not (dst / f.name).exists() or upgrade):
                    shutil.copy2(f, dst / f.name)

    env_file = HOME / ".env"
    if not env_file.exists():
        template = (BUNDLE / ".env.example").read_text(encoding="utf-8")
        lines = [f"SECRET_KEY={secrets.token_urlsafe(48)}" if ln.startswith("SECRET_KEY=") else ln
                 for ln in template.splitlines()]
        env_file.write_text("\n".join(lines) + "\n", encoding="utf-8")

    if not applied or upgrade:
        marker.write_text(bundle_version, encoding="utf-8")


def prepare_database(status) -> None:
    """Create/migrate the database and import the bundled history (first run)."""
    status("Preparing the database...")
    from app.db.migrate import upgrade_to_head

    upgrade_to_head()
    setup_logging()  # Alembic's fileConfig() just replaced the root handlers

    seed = BUNDLE / "data" / "seed" / "physician_volumes.csv.gz"
    if seed.exists():
        import sqlalchemy as sa
        from db import database_url
        from history_seed import import_seed, years_in

        engine = sa.create_engine(database_url())
        try:
            if not years_in(engine):
                status("Loading physician history (first run only)...")
                count = import_seed(engine, seed)
                log.info("Imported %d history rows from snapshot", count)
        finally:
            engine.dispose()


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def start_server(port: int):
    os.environ.update({
        "SERVE_FRONTEND": "true",
        "FRONTEND_DIST": str(BUNDLE / "frontend" / "dist"),
        "DOCTOR_PROSPECTOR_SKIP_MIGRATIONS": "1",
        "HOST": "127.0.0.1",
        "PORT": str(port),
    })
    import uvicorn
    from app.main import app

    server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=port, log_level="info"))
    threading.Thread(target=server.run, name="api", daemon=True).start()
    return server


def wait_for_health(url: str, timeout: float = 120.0) -> bool:
    import urllib.request

    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(f"{url}/api/v1/health", timeout=2) as r:
                if r.status == 200:
                    return True
        except OSError:
            time.sleep(0.5)
    return False


# ── modes ──────────────────────────────────────────────────────────────────

SPLASH = """<!doctype html><html><head><meta charset="utf-8"><style>
body{margin:0;height:100vh;display:flex;align-items:center;justify-content:center;
font-family:Segoe UI,system-ui,sans-serif;background:#f8fafc;color:#1e293b}
.box{text-align:center}.logo{width:72px;height:72px;border-radius:16px;background:#2563eb;color:#fff;
font-size:30px;font-weight:700;display:flex;align-items:center;justify-content:center;margin:0 auto 20px}
.spin{width:28px;height:28px;border:3px solid #cbd5e1;border-top-color:#2563eb;border-radius:50%;
animation:s 1s linear infinite;margin:18px auto 0}@keyframes s{to{transform:rotate(360deg)}}
#msg{color:#64748b;margin-top:6px}</style></head><body><div class="box"><div class="logo">DG</div>
<div style="font-size:20px;font-weight:600">Doctor Prospector</div><div id="msg">Starting...</div>
<div class="spin"></div></div></body></html>"""


def run_gui() -> int:
    import webview

    log_file = setup_logging()
    log.info("Starting %s (bundle=%s, home=%s)", APP_NAME, BUNDLE, HOME)
    window = webview.create_window(APP_NAME, html=SPLASH, width=1440, height=920, min_size=(1024, 700))
    state: dict = {}

    def status(text: str) -> None:
        try:
            window.evaluate_js(f"document.getElementById('msg').textContent = {json.dumps(text)}")
        except Exception:  # window not ready yet / already closed
            pass

    def boot() -> None:
        try:
            # Already running (e.g. opened twice)? Just show that instance.
            port_file = HOME / "data" / "port"
            if port_file.exists():
                existing = f"http://127.0.0.1:{port_file.read_text(encoding='utf-8').strip()}"
                if wait_for_health(existing, timeout=1.5):
                    window.load_url(existing)
                    return
            seed_home()
            prepare_database(status)
            port = free_port()
            status("Starting...")
            state["server"] = start_server(port)
            url = f"http://127.0.0.1:{port}"
            if not wait_for_health(url):
                raise RuntimeError("the app server didn't start within 2 minutes")
            (HOME / "data" / "port").write_text(str(port), encoding="utf-8")
            window.load_url(url)
        except Exception as e:  # show it instead of a frozen splash
            log.exception("Startup failed")
            window.load_html(
                f"<body style='font-family:Segoe UI,sans-serif;padding:40px'><h2>Doctor Prospector couldn't start</h2>"
                f"<p>{type(e).__name__}: {e}</p><p>Details are in the log file:<br><code>{log_file}</code></p></body>"
            )

    # Keep localStorage (the export queue lives there) between runs
    webview.start(boot, private_mode=False, storage_path=str(HOME / "webview"))

    server = state.get("server")
    if server is not None:
        server.should_exit = True
        time.sleep(1.5)  # let the scheduler/DB connections close cleanly
    return 0


def run_refresh(args: list[str]) -> int:
    if FROZEN:
        _attach_console()
    setup_logging(redirect_stdio=False)  # output belongs in the console window
    seed_home()
    prepare_database(print)  # in case they refresh before ever opening the app
    import refresh_all

    sys.argv = ["refresh_all.py", *args]
    print(f"Refreshing Doctor Prospector data in {HOME}\n")
    try:
        code = refresh_all.main()
    except SystemExit as e:
        code = e.code if isinstance(e.code, int) else 1
    print("\nDone." if code == 0 else f"\nRefresh stopped (code {code}). See the messages above.")
    print("Restart Doctor Prospector to see refreshed hospital data.")
    if FROZEN and not os.environ.get("DOCTOR_PROSPECTOR_NO_PAUSE"):
        input("\nPress Enter to close this window...")
    return code


def _attach_console() -> None:
    """Windowed exe: open a console for --refresh output."""
    import ctypes

    ctypes.windll.kernel32.AllocConsole()
    sys.stdout = open("CONOUT$", "w", encoding="utf-8", buffering=1)
    sys.stderr = sys.stdout
    sys.stdin = open("CONIN$", "r", encoding="utf-8")


def main() -> int:
    args = sys.argv[1:]
    if args[:1] == ["--refresh"]:
        return run_refresh(args[1:])
    if args[:1] == ["--data-folder"]:
        HOME.mkdir(parents=True, exist_ok=True)
        os.startfile(HOME)  # noqa: S606 (Windows only)
        return 0
    return run_gui()


if __name__ == "__main__":
    sys.exit(main())
