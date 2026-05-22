# 🚀 Hostinger VPS Deploy Guide
# Server: 76.13.61.252 (srv1417349.hstgr.cloud)
# OS: Ubuntu 24.04 LTS | 2 CPU | 8GB RAM | 100GB SSD

## What This Package Contains

| File | Purpose |
|------|---------|
| `docker-compose.prod.yml` | Production Docker stack (isolated ports) |
| `nginx/qrmenu.conf` | Nginx reverse proxy + SSL + WebSocket |
| `.env.example` | Environment variables template |
| `deploy.sh` | One-command deploy script |

## Port Mapping (No Conflicts)

| Service | Internal | External | Notes |
|---------|----------|----------|-------|
| Nginx | 80/443 | 80/443 | Standard HTTP/HTTPS |
| FastAPI | 8000 | 9000 (localhost only) | Proxied via Nginx |
| PostgreSQL | 5432 | 5433 (localhost only) | Isolated from other DBs |
| Redis | 6379 | 6380 (localhost only) | Isolated from other Redis |

All backend services bind to `127.0.0.1` only — no external exposure.

## Pre-Deploy Checklist

### 1. Domain Setup (Hostinger)
1. Log into Hostinger hPanel
2. Go to **Domains** → Manage your domain
3. Add **A Record**:
   - Name: `@` (root) or `www`
   - Points to: `76.13.61.252`
   - TTL: 3600
4. Wait 5-10 minutes for DNS propagation

### 2. Prepare Your Code
Ensure all 12 phases are committed to your git repo:
```bash
git add .
git commit -m "Phase 12 complete — production ready"
git push origin main
```

## Deploy Steps

### Step 1: SSH to Server
```bash
ssh root@76.13.61.252
```

### Step 2: Clone/Pull Code
```bash
cd /opt
git clone YOUR_GIT_REPO_URL qrmenu
cd qrmenu
```

### Step 3: Copy Deploy Files
```bash
# From the deploy_hostinger package
cp /path/to/deploy_hostinger/docker-compose.prod.yml .
cp /path/to/deploy_hostinger/nginx/qrmenu.conf ./nginx/
cp /path/to/deploy_hostinger/.env.example ./.env
```

### Step 4: Configure Environment
```bash
nano .env
```

Edit these values:
```
DOMAIN=yourdomain.com                    # Your Hostinger domain
SECRET_KEY=$(openssl rand -hex 32)     # Auto-generated
DB_PASSWORD=$(openssl rand -base64 24) # Auto-generated
STRIPE_SECRET_KEY=sk_live_...          # Your Stripe key
WHATSAPP_API_KEY=...                   # Your WhatsApp API key
TALABAT_API_KEY=...                    # Your Talabat key
ZOMATO_API_KEY=...                     # Your Zomato key
JAHEZ_API_KEY=...                      # Your Jahez key
```

### Step 5: Run Deploy Script
```bash
chmod +x deploy.sh
./deploy.sh
```

This will:
1. Install Docker & Docker Compose (if missing)
2. Build production image
3. Start PostgreSQL, Redis, API, Celery Worker, Celery Beat
4. Run database migrations
5. Install and configure Nginx
6. Obtain SSL certificate via Let's Encrypt
7. Verify everything is running

### Step 6: Verify
```bash
# Check containers
docker-compose -f docker-compose.prod.yml ps

# Check logs
docker-compose -f docker-compose.prod.yml logs -f qrmenu-api

# Health check
curl https://yourdomain.com/api/v1/health

# Test frontend
curl https://yourdomain.com
```

## Post-Deploy Management

### View Logs
```bash
docker-compose -f /var/www/qrmenu/docker-compose.prod.yml logs -f qrmenu-api
docker-compose -f /var/www/qrmenu/docker-compose.prod.yml logs -f qrmenu-worker
docker-compose -f /var/www/qrmenu/docker-compose.prod.yml logs -f qrmenu-beat
```

### Restart Services
```bash
docker-compose -f /var/www/qrmenu/docker-compose.prod.yml restart qrmenu-api
```

### Update Code
```bash
cd /var/www/qrmenu
git pull origin main
docker-compose -f docker-compose.prod.yml up -d --build
```

### Database Backup
```bash
docker-compose -f /var/www/qrmenu/docker-compose.prod.yml exec qrmenu-db pg_dump -U qrmenu qrmenu_prod > backup_$(date +%Y%m%d).sql
```

### SSL Renewal
Certbot auto-renews, but to manually renew:
```bash
certbot renew --nginx
```

## Troubleshooting

### Port Already in Use
If you get "port already in use" errors, check what's running:
```bash
netstat -tlnp | grep -E ':80|:443|:9000'
```

Our config uses port 9000 (not 8000) and binds to localhost only, so it shouldn't conflict.

### Nginx Config Test Fails
```bash
nginx -t
# If errors, check the domain was properly substituted in the config
cat /etc/nginx/sites-available/qrmenu | grep server_name
```

### SSL Certificate Issues
```bash
# Check certbot logs
cat /var/log/letsencrypt/letsencrypt.log

# Re-run certbot manually
certbot --nginx -d yourdomain.com
```

### Database Connection Failed
```bash
# Check if DB container is healthy
docker-compose -f /var/www/qrmenu/docker-compose.prod.yml ps

# Check DB logs
docker-compose -f /var/www/qrmenu/docker-compose.prod.yml logs qrmenu-db
```

## Security Notes

1. **Firewall**: Ensure only ports 80, 443, and 22 (SSH) are open:
   ```bash
   ufw allow 80/tcp
   ufw allow 443/tcp
   ufw allow 22/tcp
   ufw enable
   ```

2. **Fail2Ban**: Recommended for SSH protection:
   ```bash
   apt install fail2ban -y
   ```

3. **Automatic Updates**:
   ```bash
   apt install unattended-upgrades -y
   ```

## Monitoring

### Server Resources
```bash
# CPU/Memory
docker stats

# Disk usage
df -h

# Container resource usage
docker system df
```

### Application Monitoring
- Flower (Celery): Not exposed externally in production. Access via SSH tunnel:
  ```bash
  ssh -L 5555:localhost:5555 root@76.13.61.252
  # Then open http://localhost:5555 in browser
  ```

## Complete URLs After Deploy

| URL | What It Is |
|-----|-----------|
| `https://yourdomain.com` | Customer PWA (QR Menu) |
| `https://yourdomain.com/portal` | Merchant Portal |
| `https://yourdomain.com/kds` | Kitchen Display System |
| `https://yourdomain.com/driver` | Driver Mobile App |
| `https://yourdomain.com/api/v1/health` | Health Check |
| `https://yourdomain.com/api/v1/docs` | API Documentation (if you have it) |

## Support

If deployment fails, check:
1. `.env` file has all required values
2. Domain DNS points to `76.13.61.252`
3. Docker is running: `systemctl status docker`
4. Nginx is running: `systemctl status nginx`
5. Containers are up: `docker-compose -f docker-compose.prod.yml ps`
