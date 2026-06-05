@echo off
echo Stopping and removing containers...
docker compose down

echo Building and starting containers...
docker compose -f docker-compose.yml -f docker-compose.dev.yml up -d --build

echo Done.
pause