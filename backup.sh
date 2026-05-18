#!/bin/bash
# Daily backup script - add to crontab: 0 3 * * * /root/qrmenu-saas/backup.sh

BACKUP_DIR="/backups/qrmenu"
DATE=$(date +%Y%m%d_%H%M%S)
RETENTION_DAYS=7

mkdir -p $BACKUP_DIR

# Backup PostgreSQL
docker exec qrmenu_db pg_dump -U saas_user saas_db | gzip > $BACKUP_DIR/saas_db_$DATE.sql.gz

# Backup Redis
docker exec qrmenu_redis redis-cli BGSAVE
sleep 5
docker cp qrmenu_redis:/data/dump.rdb $BACKUP_DIR/redis_$DATE.rdb

# Cleanup old backups
find $BACKUP_DIR -name "saas_db_*.sql.gz" -mtime +$RETENTION_DAYS -delete
find $BACKUP_DIR -name "redis_*.rdb" -mtime +$RETENTION_DAYS -delete

echo "Backup completed: $DATE"
