#!/bin/bash
# ═══════════════════════════════════════════════════════════════
# QR Menu SaaS — Hostinger VPS Deploy Script
# Server: 76.13.61.252 (Ubuntu 24.04)
# Run as root or with sudo
# ═══════════════════════════════════════════════════════════════

set -e  # Exit on error

echo "🚀 Starting QR Menu SaaS deployment..."

# ─── 1. CHECK REQUIREMENTS ───────────────────────────────────
echo "📋 Checking requirements..."

if ! command -v docker &> /dev/null; then
    echo "❌ Docker not found. Installing..."
    curl -fsSL https://get.docker.com | sh
    systemctl enable docker
    systemctl start docker
    usermod -aG docker root
fi

if ! command -v docker-compose &> /dev/null; then
    echo "❌ Docker Compose not found. Installing..."
    curl -L "https://github.com/docker/compose/releases/latest/download/docker-compose-$(uname -s)-$(uname -m)" -o /usr/local/bin/docker-compose
    chmod +x /usr/local/bin/docker-compose
fi

# ─── 2. CREATE DIRECTORIES ──────────────────────────────────
echo "📁 Creating directories..."
mkdir -p /var/www/qrmenu
mkdir -p /var/www/qrmenu/static
mkdir -p /var/www/qrmenu/backups
mkdir -p /var/www/qrmenu/nginx

# ─── 3. COPY FILES ──────────────────────────────────────────
echo "📦 Copying application files..."
# NOTE: Run this script from your project root where docker-compose.prod.yml exists
cp docker-compose.prod.yml /var/www/qrmenu/
cp -r static/* /var/www/qrmenu/static/ 2>/dev/null || echo "⚠️ No static files to copy"
cp nginx/qrmenu.conf /var/www/qrmenu/nginx/

# ─── 4. SETUP ENVIRONMENT ───────────────────────────────────
echo "🔧 Setting up environment..."
if [ ! -f /var/www/qrmenu/.env ]; then
    echo "⚠️ .env file not found. Creating from example..."
    cp .env.example /var/www/qrmenu/.env
    echo "❌ PLEASE EDIT /var/www/qrmenu/.env with your actual values before continuing!"
    exit 1
fi

# Generate SECRET_KEY if not set
if grep -q "CHANGE_THIS_TO_64_CHAR_RANDOM_STRING" /var/www/qrmenu/.env; then
    NEW_SECRET=$(openssl rand -hex 32)
    sed -i "s/CHANGE_THIS_TO_64_CHAR_RANDOM_STRING/$NEW_SECRET/g" /var/www/qrmenu/.env
    echo "✅ Generated SECRET_KEY"
fi

# Generate DB_PASSWORD if not set
if grep -q "CHANGE_THIS_TO_STRONG_PASSWORD" /var/www/qrmenu/.env; then
    NEW_DB_PASS=$(openssl rand -base64 24)
    sed -i "s/CHANGE_THIS_TO_STRONG_PASSWORD/$NEW_DB_PASS/g" /var/www/qrmenu/.env
    echo "✅ Generated DB_PASSWORD"
fi

# ─── 5. BUILD & START ───────────────────────────────────────
echo "🏗️ Building and starting containers..."
cd /var/www/qrmenu

docker-compose -f docker-compose.prod.yml down 2>/dev/null || true
docker-compose -f docker-compose.prod.yml pull
docker-compose -f docker-compose.prod.yml up -d --build

# ─── 6. RUN MIGRATIONS ────────────────────────────────────
echo "🗄️ Running database migrations..."
sleep 5  # Wait for DB to be ready
docker-compose -f docker-compose.prod.yml exec -T qrmenu-api alembic upgrade head

# ─── 7. INSTALL NGINX ──────────────────────────────────────
echo "🌐 Setting up Nginx..."
if ! command -v nginx &> /dev/null; then
    apt-get update
    apt-get install -y nginx
fi

# Copy config
cp /var/www/qrmenu/nginx/qrmenu.conf /etc/nginx/sites-available/qrmenu

# Replace domain placeholder
DOMAIN=$(grep "^DOMAIN=" /var/www/qrmenu/.env | cut -d '=' -f2)
sed -i "s/YOUR_DOMAIN_HERE/$DOMAIN/g" /etc/nginx/sites-available/qrmenu

# Enable site
ln -sf /etc/nginx/sites-available/qrmenu /etc/nginx/sites-enabled/
rm -f /etc/nginx/sites-enabled/default 2>/dev/null || true

# Test and reload
nginx -t && systemctl reload nginx

# ─── 8. SSL CERTIFICATE ─────────────────────────────────────
echo "🔒 Setting up SSL..."
if ! command -v certbot &> /dev/null; then
    apt-get install -y certbot python3-certbot-nginx
fi

certbot --nginx -d $DOMAIN --non-interactive --agree-tos --email admin@$DOMAIN || true

# ─── 9. VERIFY DEPLOYMENT ─────────────────────────────────
echo "✅ Verifying deployment..."
sleep 3

echo ""
echo "📊 Container Status:"
docker-compose -f docker-compose.prod.yml ps

echo ""
echo "🔍 Health Check:"
curl -s http://127.0.0.1:9000/api/v1/health | head -c 200 || echo "❌ Health check failed"

echo ""
echo "🎉 DEPLOYMENT COMPLETE!"
echo ""
echo "📱 Frontend URLs:"
echo "   https://$DOMAIN          → Customer PWA"
echo "   https://$DOMAIN/portal   → Merchant Portal"
echo "   https://$DOMAIN/kds      → KDS Display"
echo "   https://$DOMAIN/driver   → Driver App"
echo ""
echo "🔌 API Base URL:"
echo "   https://$DOMAIN/api/v1/"
echo ""
echo "📋 Useful Commands:"
echo "   docker-compose -f /var/www/qrmenu/docker-compose.prod.yml logs -f"
echo "   docker-compose -f /var/www/qrmenu/docker-compose.prod.yml ps"
echo "   docker-compose -f /var/www/qrmenu/docker-compose.prod.yml restart qrmenu-api"
echo ""
