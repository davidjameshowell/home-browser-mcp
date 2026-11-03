"""Persistent browser lifecycle. CDP is deliberately restricted to loopback."""
import json
import os
from pathlib import Path
import signal
import shutil
import subprocess
import urllib.request
from urllib.parse import urlparse


def local_endpoint(endpoint):
    parsed = urlparse(endpoint)
    if parsed.scheme != "http" or parsed.hostname not in ("127.0.0.1", "localhost", "::1"):
        raise ValueError("Use an HTTP loopback CDP endpoint; tunnel remote access through SSH.")
    return endpoint.rstrip("/")


def browser_status(endpoint):
    endpoint = local_endpoint(endpoint)
    # Never send browser-control requests through an inherited outbound proxy.
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    with opener.open(endpoint + "/json/version", timeout=5) as response:
        data = json.load(response)
    return {"endpoint": endpoint, "browser": data.get("Browser"), "ready": bool(data.get("webSocketDebuggerUrl"))}


def open_url(endpoint, url):
    endpoint = local_endpoint(endpoint)
    if urlparse(url).scheme not in ("http", "https"):
        raise ValueError("Login URL must use HTTP or HTTPS")
    from patchright.sync_api import sync_playwright
    with sync_playwright() as p:
        browser = p.chromium.connect_over_cdp(endpoint)
        if not browser.contexts:
            raise RuntimeError("Shared browser has no persistent context")
        page = browser.contexts[0].new_page()
        page.goto(url)
        page.bring_to_front()
        # Stopping the client disconnects; browser.close() would close the user's browser.


def run_browser(profile_dir, port=9222):
    if not 1024 <= port <= 65535:
        raise ValueError("Browser port must be between 1024 and 65535")
    if os.name != "nt" and not os.environ.get("DISPLAY"):
        raise RuntimeError("DISPLAY is required. Start the graphical services or use an existing desktop.")
    endpoint = f"http://127.0.0.1:{port}"
    try:
        if browser_status(endpoint)["ready"]:
            raise RuntimeError(f"A browser is already listening at {endpoint}")
    except (OSError, ValueError):
        pass
    profile = Path(profile_dir).expanduser().resolve()
    profile.mkdir(parents=True, exist_ok=True, mode=0o700)
    if os.name != "nt":
        profile.chmod(0o700)
    executable = os.environ.get("HBM_BROWSER_EXECUTABLE") or shutil.which("google-chrome-stable") or shutil.which("google-chrome")
    if not executable:
        from patchright.sync_api import sync_playwright
        with sync_playwright() as p:
            executable = p.chromium.executable_path
    command = [executable, f"--user-data-dir={profile}",
               "--remote-debugging-address=127.0.0.1", f"--remote-debugging-port={port}",
               "--no-first-run", "--no-default-browser-check", "--disable-dev-shm-usage",
               "--password-store=basic", "about:blank"]
    process = subprocess.Popen(command)

    def stop(signum, frame):
        if process.poll() is None:
            try:
                from patchright.sync_api import sync_playwright
                with sync_playwright() as p:
                    browser = p.chromium.connect_over_cdp(endpoint, timeout=5000)
                    browser.new_browser_cdp_session().send("Browser.close")
                process.wait(timeout=10)
            except Exception:
                if process.poll() is None:
                    process.terminate()

    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)
    raise SystemExit(process.wait())
