# Database Restore Procedure

## Stop containers

ssh -p 145 Padm@192.168.1.140

cd /volume1/docker/compose/investing-platform

sudo docker compose down

## Remove existing postgres container

sudo docker rm investing-postgres

## Remove existing postgres volume

sudo docker volume rm investing-platform_investing_postgres_data

## Start only postgres

sudo docker compose up -d postgres

## Wait ~15 seconds

sudo docker ps

## Restore backup

gunzip -c /volume1/docker/configs/investing-platform/data/backups/BACKUP_FILE.sql.gz \
| sudo docker exec -i investing-postgres psql -U investing -d investing

## Start full stack

sudo docker compose up -d

## Verify

Open dashboard:

http://NAS_IP:8501
