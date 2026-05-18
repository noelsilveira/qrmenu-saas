# QRMenu SaaS - Hostinger Deployment Guide
## Server: srv1417349.hstgr.cloud | IP: 76.13.61.252

## Quick Start (One Command)

```bash
# 1. SSH into your server
ssh root@76.13.61.252

# 2. Download and run deploy script
curl -fsSL https://raw.githubusercontent.com/noelsilveira/qrmenu-saas/main/deploy.sh | bash

# 3. Edit .env file
nano ~/qrmenu-saas/.env
# Set SECRET_KEY and DB_PASSWORD

# 4. Re-run deploy
bash ~/qrmenu-saas/deploy.sh
```

## Manual Steps

### Step 1: SSH into server
```bash
ssh root@76.13.61.252
```

### Step 2: Install Docker & Docker Compose
```bash
curl -fsSL https://get.docker.com | sh
sudo usermod -aG docker $USER
# Log out and back in
```

### Step 3: Clone repo
```bash
cd ~
git clone https://github.com/noelsilveira/qrmenu-saas.git
cd qrmenu-saas
```

### Step 4: Create .env
```bash
cp .env.example .env
nano .env
```
Fill in:
- `SECRET_KEY` — generate with: `openssl rand -hex 32`
- `DB_PASSWORD` — strong password

### Step 5: Deploy
```bash
docker-compose -f docker-compose.prod.yml up -d --build
sleep 10
docker-compose -f docker-compose.prod.yml exec api alembic upgrade head
```

### Step 6: Verify
```bash
curl http://76.13.61.252/health
# Should return: {"status":"healthy","version":"2.0.0"}
```

## Useful Commands

```bash
# View logs
docker-compose -f docker-compose.prod.yml logs -f api

# Restart API
docker-compose -f docker-compose.prod.yml restart api

# Database shell
docker-compose -f docker-compose.prod.yml exec db psql -U saas_user -d saas_db

# Redis CLI
docker-compose -f docker-compose.prod.yml exec redis redis-cli

# Update deployment
cd ~/qrmenu-saas && git pull origin main
docker-compose -f docker-compose.prod.yml up -d --build
```

## Adding a Custom Domain

1. Point your domain A record to `76.13.61.252`
2. Update `nginx/sites-available/qrmenu.conf`:
   ```
   server_name yourdomain.com www.yourdomain.com;
   ```
3. Get SSL:
   ```bash
   docker run -it --rm      -v certbot_data:/etc/letsencrypt      -v certbot_www:/var/www/certbot      certbot/certbot certonly --standalone -d yourdomain.com
   ```

## Backup

```bash
# Add to crontab for daily backups at 3 AM
crontab -e
# Add line:
0 3 * * * /root/qrmenu-saas/backup.sh
```
