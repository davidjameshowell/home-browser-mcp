#!/usr/bin/env bash
# Ubuntu/Debian graphical browser services, owned by the invoking non-root user.
set -euo pipefail
if [[ $(id -u) == 0 ]]; then
  echo 'Run as the browser user, with sudo access, not as root.' >&2
  exit 1
fi
ROOT=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd)
if [[ "$ROOT" == *'%'* || "$ROOT" == *$'\n'* || "$ROOT" == *'"'* || "$ROOT" == *'\\'* ]]; then
  echo 'Checkout path contains characters unsupported in service definitions.' >&2
  exit 1
fi
sudo apt-get update
sudo apt-get install -y python3-venv xvfb x11vnc novnc websockify openbox xauth openssl
python3 -m venv "$ROOT/.venv"
"$ROOT/.venv/bin/python" -m pip install -r "$ROOT/requirements.txt"
"$ROOT/.venv/bin/scrapling" install
"$ROOT/.venv/bin/python" -m patchright install --with-deps chromium
# Ubuntu restricts user namespaces for downloaded Chromium builds. The official
# Chrome path has a distribution-provided AppArmor policy and keeps its sandbox.
if [[ -r /proc/sys/kernel/apparmor_restrict_unprivileged_userns ]] &&
   [[ $(cat /proc/sys/kernel/apparmor_restrict_unprivileged_userns) == 1 ]] &&
   ! command -v google-chrome-stable >/dev/null; then
  if [[ $(dpkg --print-architecture) != amd64 ]]; then
    echo 'Provide an approved sandbox-capable browser on this architecture.' >&2
    exit 1
  fi
  PACKAGE_DIR=$(mktemp -d)
  trap 'rm -f -- "$PACKAGE_DIR/google-chrome.deb"; rmdir -- "$PACKAGE_DIR"' EXIT
  chmod 755 "$PACKAGE_DIR"
  python3 -c 'import sys, urllib.request; urllib.request.urlretrieve("https://dl.google.com/linux/direct/google-chrome-stable_current_amd64.deb", sys.argv[1])' "$PACKAGE_DIR/google-chrome.deb"
  sudo apt-get install -y "$PACKAGE_DIR/google-chrome.deb"
fi
if ! command -v npx >/dev/null; then
  echo 'Install Node.js 18+ before connecting Playwright MCP.' >&2
  exit 1
fi
CONFIG="$HOME/.config/home-browser-mcp"
UNITS="$HOME/.config/systemd/user"
install -d -m 700 "$CONFIG" "$UNITS" "$HOME/.local/share/home-browser-mcp"
if [[ ! -f "$CONFIG/vnc.pass" ]]; then
  if [[ "${1:-}" == '--generate-vnc-password' ]]; then
    (umask 077; openssl rand -hex 4 > "$CONFIG/vnc-password.txt")
    x11vnc -storepasswd "$(cat "$CONFIG/vnc-password.txt")" "$CONFIG/vnc.pass"
    echo "Generated VNC password saved privately to $CONFIG/vnc-password.txt"
  else
    echo 'Choose a dedicated VNC password (classic VNC uses the first eight characters).'
    x11vnc -storepasswd "$CONFIG/vnc.pass"
  fi
fi
chmod 600 "$CONFIG/vnc.pass"
if [[ ! -f "$CONFIG/xauthority" ]]; then
  touch "$CONFIG/xauthority"
  chmod 600 "$CONFIG/xauthority"
  xauth -f "$CONFIG/xauthority" add :99 . "$(openssl rand -hex 16)"
fi
write_unit() {
  local name=$1 description=$2 command=$3 dependencies=$4
  cat > "$UNITS/$name.service" <<EOF
[Unit]
Description=$description
After=$dependencies
Requires=$dependencies
PartOf=home-browser.target

[Service]
Environment=DISPLAY=:99
Environment="XAUTHORITY=$CONFIG/xauthority"
UMask=0077
ExecStart=$command
Restart=on-failure
RestartSec=3
TimeoutStopSec=20
KillMode=mixed
EOF
}
write_unit home-browser-display 'Home browser virtual display' "/usr/bin/Xvfb :99 -screen 0 1440x900x24 -nolisten tcp -auth \"$CONFIG/xauthority\"" ''
write_unit home-browser-desktop 'Home browser window manager' '/usr/bin/openbox' 'home-browser-display.service'
write_unit home-browser-vnc 'Private home browser VNC' "/usr/bin/x11vnc -display :99 -auth \"$CONFIG/xauthority\" -rfbauth \"$CONFIG/vnc.pass\" -localhost -rfbport 5900 -forever -shared" 'home-browser-display.service'
write_unit home-browser-web 'Private home browser noVNC' '/usr/bin/websockify --web=/usr/share/novnc 127.0.0.1:6080 127.0.0.1:5900' 'home-browser-vnc.service'
write_unit home-browser-chromium 'Persistent home browser' "\"$ROOT/.venv/bin/python\" \"$ROOT/hbm.py\" browser run --profile-dir \"$HOME/.local/share/home-browser-mcp/profile\"" 'home-browser-display.service'
cat > "$UNITS/home-browser.target" <<'EOF'
[Unit]
Description=Persistent home browser with private graphical access
Wants=home-browser-desktop.service home-browser-web.service home-browser-chromium.service
After=home-browser-display.service

[Install]
WantedBy=default.target
EOF
systemctl --user daemon-reload
systemctl --user enable --now home-browser.target
echo 'Services started. For startup at boot without a login, run: sudo loginctl enable-linger "$USER"'
echo 'Tunnel: ssh -N -L 6080:127.0.0.1:6080 user@browser-host'
echo 'Open http://127.0.0.1:6080/vnc.html and enter the VNC password.'
