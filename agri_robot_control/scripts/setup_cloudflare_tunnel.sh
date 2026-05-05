#!/usr/bin/env bash
# setup_cloudflare_tunnel.sh — Install and configure Cloudflare Tunnel on Raspberry Pi
#
# Solves 5G CGNAT problem: Pi on a 5G SIM gets a private IP that Flutter app
# cannot reach directly.  Cloudflare Tunnel creates an outbound-only connection
# from the Pi to Cloudflare's edge, then exposes a public subdomain that the
# app connects to.
#
# Architecture:
#   Flutter app ──MQTT──► <robot>.cfargotunnel.com:1883
#                                   │  (Cloudflare edge)
#                                   ▼
#                           cloudflared (on Pi)
#                                   │
#                                   ▼
#                        Mosquitto  localhost:1883
#
# Prerequisites:
#   1. Free Cloudflare account at https://dash.cloudflare.com
#   2. A domain added to Cloudflare (even a free one works)
#   3. Run this script on the Raspberry Pi (Ubuntu 22.04)
#
# Usage:
#   chmod +x setup_cloudflare_tunnel.sh
#   ./setup_cloudflare_tunnel.sh
#
# After setup:
#   - In Flutter app Settings: host = <your-tunnel-hostname>, port = 1883
#   - Tunnel starts automatically on boot via systemd

set -e

TUNNEL_NAME="agri-robot"
MQTT_PORT=1883

echo "=== Cloudflare Tunnel Setup for Agri Robot ==="
echo ""

# ── Step 1: Install cloudflared ───────────────────────────────────────────────
echo "[1/5] Installing cloudflared..."

# ARM64 (Raspberry Pi 3 with Ubuntu 22.04 64-bit)
ARCH=$(dpkg --print-architecture)
if [ "$ARCH" = "arm64" ]; then
    wget -q https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-arm64.deb
    sudo dpkg -i cloudflared-linux-arm64.deb
    rm cloudflared-linux-arm64.deb
elif [ "$ARCH" = "armhf" ]; then
    wget -q https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-armhf.deb
    sudo dpkg -i cloudflared-linux-armhf.deb
    rm cloudflared-linux-armhf.deb
else
    echo "Unsupported architecture: $ARCH"
    exit 1
fi

echo "cloudflared installed: $(cloudflared --version)"

# ── Step 2: Authenticate with Cloudflare ─────────────────────────────────────
echo ""
echo "[2/5] Authenticate with Cloudflare..."
echo "A browser window will open. Log in and select your domain."
echo "(If running headless, copy the URL printed and open it on another device)"
echo ""
cloudflared tunnel login

# ── Step 3: Create tunnel ─────────────────────────────────────────────────────
echo ""
echo "[3/5] Creating tunnel '$TUNNEL_NAME'..."
cloudflared tunnel create "$TUNNEL_NAME"

TUNNEL_ID=$(cloudflared tunnel list --name "$TUNNEL_NAME" --output json 2>/dev/null \
    | python3 -c "import json,sys; d=json.load(sys.stdin); print(d[0]['id'])" 2>/dev/null || true)

if [ -z "$TUNNEL_ID" ]; then
    echo "Could not detect tunnel ID automatically."
    echo "Run: cloudflared tunnel list"
    echo "Then set TUNNEL_ID manually below."
    TUNNEL_ID="<your-tunnel-id>"
fi

echo "Tunnel ID: $TUNNEL_ID"

# ── Step 4: Configure Mosquitto for TCP tunnel ────────────────────────────────
echo ""
echo "[4/5] Configuring Mosquitto..."

# Mosquitto must accept connections from cloudflared (localhost only is fine
# because cloudflared runs on the same Pi and forwards external traffic).
sudo tee /etc/mosquitto/conf.d/agri_robot.conf > /dev/null <<EOF
# Allow anonymous connections (tunnel handles auth via Cloudflare Access if needed)
allow_anonymous true
listener $MQTT_PORT 127.0.0.1

# Also listen on all interfaces for local WiFi access
listener $MQTT_PORT
EOF

sudo systemctl restart mosquitto
echo "Mosquitto restarted."

# ── Step 5: Create cloudflared config + systemd service ──────────────────────
echo ""
echo "[5/5] Writing cloudflared config and installing systemd service..."

# Config directory
CLOUDFLARED_DIR="$HOME/.cloudflared"
mkdir -p "$CLOUDFLARED_DIR"

# Tunnel config: route TCP port 1883
# Replace <your-subdomain> with the hostname you want, e.g. robot.yourdomain.com
cat > "$CLOUDFLARED_DIR/config.yml" <<EOF
tunnel: $TUNNEL_ID
credentials-file: $CLOUDFLARED_DIR/$TUNNEL_ID.json

ingress:
  # MQTT broker — Flutter app connects to <hostname>:1883
  - hostname: robot.<your-domain.com>
    service: tcp://localhost:$MQTT_PORT
  # Catch-all required by cloudflared
  - service: http_status:404
EOF

echo ""
echo "=== MANUAL STEP REQUIRED ==="
echo "Edit ~/.cloudflared/config.yml and replace:"
echo "  robot.<your-domain.com>  →  your actual subdomain"
echo ""
echo "Then create a DNS record:"
echo "  cloudflared tunnel route dns $TUNNEL_NAME robot.<your-domain.com>"
echo ""

# Install as systemd service
sudo cloudflared service install
sudo systemctl enable cloudflared
sudo systemctl start cloudflared

echo ""
echo "=== Setup complete ==="
echo ""
echo "Tunnel status:  sudo systemctl status cloudflared"
echo "Tunnel logs:    journalctl -u cloudflared -f"
echo ""
echo "Flutter app Settings:"
echo "  Host: robot.<your-domain.com>"
echo "  Port: 1883"
echo ""
echo "Test from another machine:"
echo "  mosquitto_pub -h robot.<your-domain.com> -p 1883 -t test -m hello"
