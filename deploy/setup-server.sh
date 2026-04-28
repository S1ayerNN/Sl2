#!/bin/bash
# ============================================================
# MyAstro - Server Setup Script (run as root on fresh VPS)
# Tested on: Ubuntu 22.04 / Debian 12
# ============================================================

set -e

echo "=== MyAstro Server Setup ==="
echo ""

# 1. Update system
echo "[1/6] Updating system packages..."
apt-get update -y && apt-get upgrade -y

# 2. Install Docker
echo "[2/6] Installing Docker..."
if ! command -v docker &> /dev/null; then
    curl -fsSL https://get.docker.com | sh
    systemctl enable docker
    systemctl start docker
    echo "Docker installed successfully"
else
    echo "Docker already installed: $(docker --version)"
fi

# 3. Install Docker Compose plugin
echo "[3/6] Checking Docker Compose..."
if ! docker compose version &> /dev/null; then
    apt-get install -y docker-compose-plugin
    echo "Docker Compose installed"
else
    echo "Docker Compose already installed: $(docker compose version)"
fi

# 4. Install git
echo "[4/6] Installing git..."
apt-get install -y git

# 5. Create app directory
echo "[5/6] Setting up app directory..."
mkdir -p /opt/myastro
cd /opt/myastro

# 6. Clone repository
echo "[6/6] Cloning repository..."
if [ -d "/opt/myastro/backend/.git" ]; then
    echo "Repository already exists, pulling latest..."
    cd /opt/myastro/backend
    git pull origin feature/myastro-backend-mvp
else
    git clone -b feature/myastro-backend-mvp https://github.com/S1ayerNN/Sl2.git backend
    cd /opt/myastro/backend
fi

echo ""
echo "=== Server setup complete! ==="
echo ""
echo "Next steps:"
echo "1. Run: cd /opt/myastro/backend"
echo "2. Run: cp .env.example .env"
echo "3. Edit .env with your API keys: nano .env"
echo "4. Run: bash deploy/generate-secrets.sh"
echo "5. Run: docker compose up -d"
echo "6. Run: docker compose exec api alembic upgrade head"
echo ""
