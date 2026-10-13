"""Web-version launcher (`munger-lens --web`): runs the Streamlit app on a private
local port, opens it in your default browser, and shuts the server down once
every tab has been closed for a while. The native app is `python -m stockpicker.gui`.
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
            print(f"Munger Lens web version: {url}  (stops 10 minutes after the last tab closes; Ctrl+C to stop now)")
            serve_in_browser(url, port, proc)
        except KeyboardInterrupt:
            pass
        finally:
            stop_server(proc)
    return 0


if __name__ == "__main__":
    sys.exit(main())
