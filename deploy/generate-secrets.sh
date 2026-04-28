#!/bin/bash
# ============================================================
# Generate random secrets for .env file
# Run this ONCE during initial setup
# ============================================================

ENV_FILE=".env"

if [ ! -f "$ENV_FILE" ]; then
    echo "Error: .env file not found. Run 'cp .env.example .env' first."
    exit 1
fi

echo "Generating random secrets..."

# Generate JWT secret
JWT_SECRET=$(openssl rand -hex 32)
sed -i "s|JWT_SECRET_KEY=CHANGE_ME_MUST_BE_RANDOM|JWT_SECRET_KEY=${JWT_SECRET}|g" "$ENV_FILE"
echo "  JWT_SECRET_KEY generated"

# Generate encryption key
ENCRYPTION_KEY=$(openssl rand -hex 32)
sed -i "s|ENCRYPTION_KEY=CHANGE_ME_MUST_BE_RANDOM_ENCRYPTION_KEY|ENCRYPTION_KEY=${ENCRYPTION_KEY}|g" "$ENV_FILE"
echo "  ENCRYPTION_KEY generated"

# Generate PostgreSQL password
PG_PASSWORD=$(openssl rand -hex 16)
sed -i "s|POSTGRES_PASSWORD=CHANGE_ME_strong_password_here|POSTGRES_PASSWORD=${PG_PASSWORD}|g" "$ENV_FILE"
sed -i "s|CHANGE_ME_strong_password_here|${PG_PASSWORD}|g" "$ENV_FILE"
echo "  POSTGRES_PASSWORD generated"

# Generate Redis password
REDIS_PASSWORD=$(openssl rand -hex 16)
sed -i "s|REDIS_PASSWORD=CHANGE_ME_redis_password_here|REDIS_PASSWORD=${REDIS_PASSWORD}|g" "$ENV_FILE"
sed -i "s|CHANGE_ME_redis_password_here|${REDIS_PASSWORD}|g" "$ENV_FILE"
echo "  REDIS_PASSWORD generated"

echo ""
echo "All secrets generated! Now edit .env to add your API keys:"
echo "  - OPENAI_API_KEY=sk-..."
echo "  - TELEGRAM_BOT_TOKEN=..."
echo "  - GOOGLE_CLIENT_ID=... (optional for now)"
echo ""
echo "Then run: docker compose up -d"
