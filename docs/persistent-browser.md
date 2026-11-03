# Shared browser, persistent logins, and graphical access

This extension retains the upstream Scrapling CLI, MCP server, Python client,
Playwright engine, and Windows/macOS setup paths. The optional graphical service
installer targets Ubuntu/Debian with a systemd user session and Node.js 18+.

## Install on a Linux browser host

From this checkout, as a regular user with sudo access:

```bash
bash deploy/linux/install.sh
sudo loginctl enable-linger "$USER"
```

The installer asks for a dedicated VNC password and starts Xvfb, Openbox,
Chromium, x11vnc, and noVNC. Classic VNC uses only the first eight password
characters. Its traffic is protected by the SSH tunnel below. Re-running the
installer preserves the password, X authorization cookie, and browser profile.
For unattended installation, add `--generate-vnc-password`; it saves a random
password to the owner-only `~/.config/home-browser-mcp/vnc-password.txt` file.
The display number is :99; ports 5900, 6080, and 9222 must be free.

On Ubuntu systems that restrict user namespaces, the installer also installs
Google Chrome from Google's official package. It uses Ubuntu's existing
AppArmor allowance for Chrome so the browser sandbox stays enabled. Elsewhere,
the service prefers an installed Google Chrome or falls back to Patchright's
Chromium. `HBM_BROWSER_EXECUTABLE` can select another approved executable.

Browser data is stored outside the checkout at
`~/.local/share/home-browser-mcp/profile`, with owner-only directory permissions.
The Linux service uses Chromium's basic password store so it can run without
an interactive keyring. Treat the profile as sensitive, use disk encryption
where appropriate, and avoid saving passwords in the browser. Cookies still
grant account access to whoever controls this browser.

## Reach the desktop privately

On your laptop, using an SSH target reachable over Tailscale:

```bash
ssh -N -L 6080:127.0.0.1:6080 user@browser-host
```

Open `http://127.0.0.1:6080/vnc.html` and connect using your VNC password.
For a native VNC client, forward port 5900 instead. VNC, noVNC, and Chromium
debugging listen only on loopback; the installer opens no router ports and
does not enable Tailscale Funnel or public access.

Tailscale SSH check mode can require a human identity check. Plan unattended
access with narrowly scoped tailnet SSH policy; this installer does not change
that policy or copy administrator SSH keys to an agent.

## Login and continue automation

On the browser host:

```bash
./hbm login https://example.com/login --cdp-endpoint http://127.0.0.1:9222
./hbm browser status
```

Complete login and MFA through noVNC. Leave the browser running. This command
opens a tab in the service's existing persistent context; it does not create a
second browser against the profile. Stop agent actions before manual takeover,
then explicitly ask the agent to resume. There is no automatic input arbitration.

For a browser on an existing desktop without the service stack:

```bash
./hbm browser run --profile-dir ~/.home-browser-profile
```

The original standalone `./hbm login URL --profile-dir PATH` remains available.
It uses Patchright's installed Chromium. Close that browser before launching a
new process with the same profile. Never run two Chromium processes against the
same profile directory.

## MCP clients

Keep separate tool names so agents can choose the engine. Substitute your own
SSH target and absolute checkout path; do not assume a consumer cloud chatbot
can reach your tailnet.

```json
{
  "mcpServers": {
    "home-scrapling": {
      "command": "ssh",
      "args": ["-T", "user@browser-host", "/absolute/path/home-browser-mcp/.venv/bin/scrapling-mcp"]
    },
    "home-browser": {
      "command": "ssh",
      "args": ["-T", "user@browser-host", "/absolute/path/home-browser-mcp/hbm serve --engine playwright --cdp-endpoint http://127.0.0.1:9222"]
    }
  }
}
```

For clients without native MCP, use the existing JSON-plan driver:

```bash
export HBM_SSH_HOST=user@browser-host
export HBM_CDP_ENDPOINT=http://127.0.0.1:9222
printf '%s' '[{"tool":"browser_snapshot","args":{}}]' | ./hbm drive --engine playwright
```

The CDP endpoint above is resolved on the browser host. `--profile-dir` or
`HBM_PROFILE_DIR` selects a profile when Playwright launches its own browser;
`--headed` makes that launch visible. Attaching with `--cdp-endpoint` takes
precedence and uses the running browser's profile. Playwright MCP is pinned to
0.0.84 for reproducible tool behavior.

## Scrapling and saved accounts

`./hbm fetch`, `./hbm serve --engine scrapling`, and all upstream Scrapling tools
remain available. They retain their original independent session behavior.
Scrapling's CDP option creates a new browser context; it does **not** automatically
inherit the shared browser's cookies. Use the Playwright connection above for
logged-in account workflows. Explicit Scrapling session/cookie configuration is
still supported through its native MCP tools. No credentials are copied or
exported by this extension. Anti-bot success is website dependent.

## Services and troubleshooting

```bash
systemctl --user status home-browser.target home-browser-chromium.service
journalctl --user -u home-browser-chromium.service -n 50
systemctl --user restart home-browser-chromium.service
systemctl --user stop home-browser.target
systemctl --user start home-browser.target
```

Disabling: `systemctl --user disable --now home-browser.target`. This preserves
the profile and credentials. To apply changed service definitions after an
installer update, run `systemctl --user restart home-browser.target`.

## Meta Muse handoff

Muse must first establish an authorized connection to the host. Its built-in
cloud browser is separate from this browser. Ask Muse to use the `home-browser`
tools explicitly, pause for manual login, and resume only after you confirm.
Do not paste your runner's administrator SSH private key into a chat. If Muse
cannot reach Tailscale/SSH, a separately authenticated HTTPS connector must be
designed and tested; this installation intentionally publishes no public endpoint.

## Verification

```bash
python3 -m unittest discover -s tests -v
bash -n deploy/linux/install.sh
```

Before relying on saved accounts, test that an MCP navigation is visible in
noVNC and that a harmless test cookie/localStorage value survives a Chromium
service restart. Real account login must be completed by the user.
