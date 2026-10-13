"""Desktop launcher: runs the Streamlit app on a private local port and shows it
in a native window (pywebview + Qt) instead of a browser tab.

Closing the window shuts the server down. If the native window can't be
created (missing system libraries), it falls back to the default browser.
"""

from __future__ import annotations

import os
import signal
import socket
import subprocess
import sys
import time
import urllib.request
import webbrowser
from pathlib import Path

APP_NAME = "Munger Lens"
APP_DIR = Path(__file__).resolve().parent.parent  # contains app.py and .streamlit/
ICON = Path(__file__).resolve().parent / "munger-lens.png"
DATA_DIR = Path(os.environ.get("STOCKPICKER_DATA", APP_DIR / ".userdata"))
LOG_FILE = DATA_DIR / "launcher.log"


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def wait_until_ready(url: str, proc: subprocess.Popen, timeout: float = 90) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        if proc.poll() is not None:
            return False  # server crashed on startup
        try:
            with urllib.request.urlopen(f"{url}/_stcore/health", timeout=2) as r:
                if r.status == 200:
                    return True
        except OSError:
            pass
        time.sleep(0.3)
    return False


def start_server(port: int, log) -> subprocess.Popen:
    cmd = [
        sys.executable, "-m", "streamlit", "run", str(APP_DIR / "app.py"),
        "--server.headless=true",
        f"--server.port={port}",
        "--server.address=127.0.0.1",
        "--browser.gatherUsageStats=false",
    ]
    # cwd matters: Streamlit reads .streamlit/config.toml (theme) from the working directory.
    # New session so we can kill the whole process group on exit.
    return subprocess.Popen(cmd, cwd=APP_DIR, stdout=log, stderr=subprocess.STDOUT, start_new_session=True)


def stop_server(proc: subprocess.Popen) -> None:
    if proc.poll() is not None:
        return
    try:
        os.killpg(proc.pid, signal.SIGTERM)
        proc.wait(timeout=5)
    except (ProcessLookupError, subprocess.TimeoutExpired):
        try:
            os.killpg(proc.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass


def notify_error(msg: str) -> None:
    print(msg, file=sys.stderr)
    try:  # desktop-launched apps have no terminal, so also try a notification
        subprocess.run(["notify-send", "-a", APP_NAME, "-i", "dialog-error", APP_NAME, msg], timeout=5, check=False)
    except (OSError, subprocess.SubprocessError):
        pass


def show_window(url: str) -> int:
    """Runs in a child process (see main) so a Qt abort() can't take the launcher down."""
    try:
        import webview
    except ImportError as exc:
        print(f"[window] pywebview missing: {exc}", file=sys.stderr)
        return 3

    # Qt derives the window class (taskbar grouping, .desktop StartupWMClass) from argv[0].
    sys.argv[0] = "munger-lens"
    window = webview.create_window(
        APP_NAME, url, width=1440, height=920, min_size=(900, 600),
        background_color="#0d0d0d", text_select=True, zoomable=True,
    )
    smoke = float(os.environ.get("MUNGER_LENS_SMOKE_TEST", "0"))  # self-test: auto-close after N seconds

    def after_start():
        if smoke:
            time.sleep(smoke)
            window.destroy()

    try:
        webview.start(after_start, gui="qt", icon=str(ICON) if ICON.exists() else None,
                      private_mode=False, storage_path=str(DATA_DIR / "webview"))
    except Exception as exc:
        print(f"[window] failed: {exc!r}", file=sys.stderr)
        return 3
    return 0


def browser_connections(port: int) -> int:
    """Established TCP connections to our port (Linux /proc), i.e. open browser tabs."""
    count = 0
    for table in ("/proc/net/tcp", "/proc/net/tcp6"):
        try:
            lines = Path(table).read_text().splitlines()[1:]
        except OSError:
            continue
        for line in lines:
            parts = line.split()
            local_port = int(parts[1].rsplit(":", 1)[1], 16)
            if local_port == port and parts[3] == "01":  # 01 = ESTABLISHED
                count += 1
    return count


def serve_in_browser(url: str, port: int, proc: subprocess.Popen, idle_minutes: float = 10) -> None:
    """Fallback mode: open the default browser and stop once every tab has been closed for a while."""
    webbrowser.open(url)
    idle_since = time.time()
    while proc.poll() is None:
        time.sleep(5)
        if browser_connections(port):
            idle_since = time.time()
        elif time.time() - idle_since > idle_minutes * 60:
            return


def main() -> int:
    if len(sys.argv) == 3 and sys.argv[1] == "--window":
        return show_window(sys.argv[2])

    DATA_DIR.mkdir(parents=True, exist_ok=True)
    port = free_port()
    url = f"http://127.0.0.1:{port}"

    def on_signal(signum, _frame):
        raise KeyboardInterrupt  # route SIGTERM/SIGHUP through the cleanup below

    signal.signal(signal.SIGTERM, on_signal)
    signal.signal(signal.SIGHUP, on_signal)

    with LOG_FILE.open("w") as log:
        proc = start_server(port, log)
        try:
            if not wait_until_ready(url, proc):
                notify_error(f"The app server failed to start. See {LOG_FILE}")
                return 1
            window = subprocess.run([sys.executable, str(Path(__file__).resolve()), "--window", url],
                                    stdout=log, stderr=subprocess.STDOUT, check=False)
            if window.returncode != 0:
                log.write(f"\n[launcher] native window exited with {window.returncode}; falling back to browser\n")
                log.flush()
                notify_error("Couldn't open the app window (missing system libraries?), so it opened in your "
                             f"browser instead. It stops 10 minutes after you close the tab. Details: {LOG_FILE}")
                serve_in_browser(url, port, proc)
        except KeyboardInterrupt:
            pass
        finally:
            stop_server(proc)
    return 0


if __name__ == "__main__":
    sys.exit(main())
