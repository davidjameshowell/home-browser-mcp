"""Opt-in live test on the Linux host; uses only harmless local test data.

Run: .venv/bin/python tests/smoke_shared_browser.py
Requires the home-browser services. Restarts only the Chromium service.
"""
import asyncio
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import os
from pathlib import Path
import subprocess
import sys
import threading
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from hbm import resolve_server_cmd, run_mcp_plan
from hbm_browser import browser_status, open_url
from patchright.sync_api import sync_playwright


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        body = b"<html><body><h1>Shared browser verification</h1></body></html>"
        self.send_response(200)
        self.send_header("Content-Type", "text/html")
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args):
        pass


def wait_ready(endpoint):
    for _ in range(60):
        try:
            if browser_status(endpoint)["ready"]:
                return
        except OSError:
            pass
        time.sleep(0.5)
    raise RuntimeError("Browser failed to start")


def main():
    endpoint = "http://127.0.0.1:9222"
    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    url = f"http://127.0.0.1:{server.server_port}/"
    name = "hbm_smoke_test"
    try:
        wait_ready(endpoint)
        open_url(endpoint, url)
        with sync_playwright() as p:
            browser = p.chromium.connect_over_cdp(endpoint)
            context = browser.contexts[0]
            page = next(page for page in context.pages if page.url == url)
            page.evaluate("localStorage.setItem('hbm_smoke_test', 'persisted')")
            context.add_cookies([{"name": name, "value": "persisted", "url": url, "expires": time.time() + 3600}])
        # Restart to verify disk persistence, not just in-memory state.
        subprocess.run(["systemctl", "--user", "restart", "home-browser-chromium.service"], check=True)
        wait_ready(endpoint)
        with sync_playwright() as p:
            browser = p.chromium.connect_over_cdp(endpoint)
            context = browser.contexts[0]
            page = context.new_page()
            page.goto(url)
            assert page.evaluate("localStorage.getItem('hbm_smoke_test')") == "persisted"
            assert any(cookie["name"] == name for cookie in context.cookies(url))
            page.evaluate("localStorage.removeItem('hbm_smoke_test')")
            context.clear_cookies(name=name)
            page.close()
        command = resolve_server_cmd(host="", engine="playwright", cdp_endpoint=endpoint)
        results = asyncio.run(run_mcp_plan([
            {"tool": "browser_navigate", "args": {"url": url}},
            {"tool": "browser_snapshot", "args": {}}
        ], command))
        assert all(result["ok"] for result in results), results
        assert "Shared browser verification" in results[-1]["output"], results
        assert browser_status(endpoint)["ready"], "MCP disconnect closed shared browser"
        print("PASS: login-tab attachment, cookie and localStorage persistence across restart, MCP navigation and snapshot, browser survives disconnect")
    finally:
        server.shutdown()


if __name__ == "__main__":
    main()
