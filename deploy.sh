#!/bin/bash
set -e

echo "========================================="
echo "  QRMenu SaaS - Production Deploy"
echo "  Server: 76.13.61.252"
echo "========================================="

# 1. Update system
echo "[1/8] Updating system packages..."
sudo apt-get update -y
sudo apt-get upgrade -y

# 2. Install Docker if not present
echo "[2/8] Installing Docker..."
if ! command -v docker &> /dev/null; then
    curl -fsSL https://get.docker.com | sh
    sudo usermod -aG docker $USER
    echo "Docker installed. Please log out and back in, then re-run this script."
    exit 0
fi

# 3. Install Docker Compose
echo "[3/8] Installing Docker Compose..."
if ! command -v docker-compose &> /dev/null; then
    sudo curl -L "https://github.com/docker/compose/releases/download/v2.24.0/docker-compose-$(uname -s)-$(uname -m)" -o /usr/local/bin/docker-compose
    sudo chmod +x /usr/local/bin/docker-compose
fi

# 4. Create app directory
echo "[4/8] Setting up application directory..."
mkdir -p ~/qrmenu-saas
cd ~/qrmenu-saas

# 5. Clone repo (if not exists)
echo "[5/8] Cloning repository..."
if [ ! -d ".git" ]; then
    git clone https://github.com/noelsilveira/qrmenu-saas.git .
else
    git pull origin main
fi

# 6. Create .env file
echo "[6/8] Creating environment file..."
if [ ! -f ".env" ]; then
    cat > .env << 'ENVFILE'
# APP
APP_NAME=QRMenu SaaS
APP_VERSION=2.0.0
SECRET_KEY=CHANGE_THIS_TO_64_CHAR_RANDOM_STRING

# DATABASE
DB_PASSWORD=CHANGE_THIS_DB_PASSWORD

# REDIS (internal Docker network)
REDIS_URI=redis://redis:6379/0
REDIS_CELERY_URI=redis://redis:6379/1

# WHATSAPP (fill when ready)
META_WA_ACCESS_TOKEN=
META_WA_PHONE_NUMBER_ID=
META_WA_BUSINESS_ACCOUNT_ID=
META_WA_WEBHOOK_VERIFY_TOKEN=

# PAYMENTS (fill when ready)
STRIPE_SECRET_KEY=
STRIPE_WEBHOOK_SECRET=

# STORAGE (fill when ready)
S3_ENDPOINT=https://s3.amazonaws.com
S3_BUCKET=qrmenu-assets
S3_ACCESS_KEY=
S3_SECRET_KEY=

# CORS
CORS_ORIGINS=["*"]
ENVFILE
    echo "WARNING: .env file created. PLEASE EDIT IT and set SECRET_KEY and DB_PASSWORD!"
    echo "   nano ~/qrmenu-saas/.env"
    exit 1
fi

# 7. Build and start services
echo "[7/8] Building and starting services..."
docker-compose -f docker-compose.prod.yml down 2>/dev/null || true
docker-compose -f docker-compose.prod.yml up -d --build

# 8. Run migrations
echo "[8/8] Running database migrations..."
sleep 10
docker-compose -f docker-compose.prod.yml exec -T api alembic upgrade head

echo ""
echo "========================================="
echo "  DEPLOYMENT COMPLETE!"
echo "========================================="
echo ""
echo "API Health Check:"
echo "  curl http://76.13.61.252/health"
echo ""
echo "API Docs:"
echo "  http://76.13.61.252/api/v1/docs"
echo ""
echo "To view logs:"
echo "  docker-compose -f docker-compose.prod.yml logs -f api"
echo ""
