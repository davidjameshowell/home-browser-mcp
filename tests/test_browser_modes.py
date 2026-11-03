import json
import os
from pathlib import Path
import shlex
import tempfile
import unittest
from unittest.mock import patch

import hbm
import hbm_browser


class BrowserModes(unittest.TestCase):
    def setUp(self):
        self.env = patch.dict(os.environ, {}, clear=True)
        self.env.start()
        self.addCleanup(self.env.stop)

    def test_scrapling_keeps_original_engine(self):
        self.assertEqual(hbm.resolve_server_cmd(host="user@host"),
                         ["ssh", "-T", "user@host", "scrapling-mcp"])

    def test_remote_profile_is_chosen_on_remote_host(self):
        cmd = hbm.resolve_server_cmd(host="user@host", engine="playwright")
        self.assertIn('"$HOME"/.home-browser-profile', cmd[-1])
        self.assertIn("--headless", cmd[-1])

    def test_remote_profile_is_shell_quoted(self):
        profile = "/srv/profile name;touch /tmp/unwanted"
        cmd = hbm.resolve_server_cmd(host="user@host", engine="playwright", profile_dir=profile)
        self.assertEqual(shlex.split(cmd[-1])[-1], profile)

    def test_cdp_does_not_launch_another_profile(self):
        cmd = hbm.resolve_server_cmd(engine="playwright", cdp_endpoint="http://127.0.0.1:9222")
        self.assertIn("--cdp-endpoint", cmd)
        self.assertNotIn("--headless", cmd)
        self.assertNotIn("--user-data-dir", cmd)

    def test_headed_profile_need_not_exist_yet(self):
        with tempfile.TemporaryDirectory() as folder:
            profile = str(Path(folder) / "new-profile")
            cmd = hbm.resolve_server_cmd(engine="playwright", headed=True, profile_dir=profile)
            self.assertNotIn("--headless", cmd)
            self.assertEqual(cmd[-1], profile)

    def test_explicit_local_serve_ignores_remote_environment(self):
        os.environ["HBM_SSH_HOST"] = "user@elsewhere"
        self.assertNotEqual(hbm.resolve_server_cmd(host="", engine="playwright")[0], "ssh")

    def test_browser_control_rejects_nonlocal_endpoints(self):
        for endpoint in ("http://0.0.0.0:9222", "https://example.com", "file:///etc/passwd"):
            with self.assertRaises(ValueError):
                hbm_browser.local_endpoint(endpoint)

    def test_browser_status_uses_no_proxy(self):
        with patch("urllib.request.build_opener") as build:
            build.return_value.open.return_value.__enter__.return_value.read.return_value = json.dumps(
                {"Browser": "Chromium/test", "webSocketDebuggerUrl": "ws://127.0.0.1/test"}).encode()
            self.assertTrue(hbm_browser.browser_status("http://127.0.0.1:9222")["ready"])
            self.assertEqual(build.call_args.args[0].proxies, {})


if __name__ == "__main__":
    unittest.main()
