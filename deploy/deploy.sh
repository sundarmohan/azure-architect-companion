#!/bin/bash
set -euo pipefail
umask 077
cd "${DEPLOYMENT_DIR:-.}"
export COMPOSE_PROJECT_NAME=monitorai-v22

if [ ! -e .env ]; then
    if docker volume inspect monitorai-v22_monitorai_pg_data >/dev/null 2>&1; then
        echo "Existing V2.2 database requires its original .env" >&2
        exit 1
    fi
    {
        printf 'POSTGRES_PASSWORD=%s\n' "$(openssl rand -hex 32)"
        printf 'MONITORAI_BOOTSTRAP_USERNAME=monitorai-admin\n'
        printf 'MONITORAI_BOOTSTRAP_PASSWORD=%s\n' "$(openssl rand -hex 24)"
        printf 'MONITORAI_AZURE_ENCRYPTION_KEY=%s\n' "$(openssl rand -base64 32 | tr '+/' '-_')"
    } > .env.new
    mv .env.new .env
fi
chmod 600 .env

docker compose pull
docker compose up -d --wait --wait-timeout 180
test "$(docker compose port app 8000)" = 127.0.0.1:8003
app=$(docker compose ps -q app)
postgres=$(docker compose ps -q postgres)
test "$(docker inspect --format '{{.Config.Image}}' "$app")" = "$DOCKER_IMAGE:$IMAGE_TAG"
test "$(docker inspect --format '{{range .Mounts}}{{if eq .Destination "/var/lib/postgresql/data"}}{{.Name}}{{end}}{{end}}' "$postgres")" = monitorai-v22_monitorai_pg_data
docker compose exec -T postgres sh -c 'psql -v ON_ERROR_STOP=1 -U "$POSTGRES_USER" -d "$POSTGRES_DB" -Atc "SELECT 1"' | grep -Fx 1
revision=$(docker compose exec -T app alembic heads | awk '{print $1}')
test -n "$revision"
docker compose exec -T app alembic current | grep -Fx "$revision (head)"
docker compose ps
curl -fsS http://127.0.0.1:8003/health
for path in auth/me architectures azure/resource-catalog assessments; do
    test "$(curl -sS -o /dev/null -w '%{http_code}' "http://127.0.0.1:8003/api/$path")" = 401
done
