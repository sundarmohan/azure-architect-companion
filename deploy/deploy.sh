#!/bin/bash
set -euo pipefail
umask 077
cd "${DEPLOYMENT_DIR:-.}"
export COMPOSE_PROJECT_NAME=monitorai-v22
: "${RELEASE_ID:?}" "${DOCKER_IMAGE:?}" "${IMAGE_TAG:?}"
[[ "$RELEASE_ID" =~ ^[0-9]+-[0-9]+$ ]]
[[ "$IMAGE_TAG" =~ ^[0-9a-f]{40}$ ]]
test -s .env

release="releases/$RELEASE_ID"
state="$release/previous-image"
candidate="$DOCKER_IMAGE:$IMAGE_TAG"
export MONITORAI_IMAGE_REF="$candidate"
existing=(docker compose --env-file .env -f docker-compose.yml)
compose=(docker compose --project-directory "$PWD" --env-file .env -f "$release/docker-compose.yml")

rollback() {
    test -s "$state" || return 0
    local current previous
    previous=$(cat "$state")
    current=$("${compose[@]}" ps -aq app)
    if [[ -n "$current" ]]; then
        local image
        image=$(docker inspect --format '{{.Config.Image}}' "$current")
        if [[ "$image" != "$candidate" && "$image" != "$previous" ]]; then
            echo "Running app changed independently. Rollback stopped." >&2
            return 1
        fi
    fi
    MONITORAI_IMAGE_REF="$previous" "${compose[@]}" up -d --no-deps --pull never --wait --wait-timeout 180 app || return 1
    curl -fsS http://127.0.0.1:8003/health || return 1
    rm -f "$state"
    echo "Previous application image restored"
}

case "${1:-deploy}" in
    rollback) rollback; exit ;;
    finalize) rm -f "$state"; exit ;;
    deploy) ;;
    *) exit 2 ;;
esac

app=$("${existing[@]}" ps -q app)
db=$("${existing[@]}" ps -q postgres)
test -n "$app" && test -n "$db"
test "$(docker inspect --format '{{.State.Health.Status}}' "$db")" = healthy
test "$(docker inspect --format '{{range .Mounts}}{{if eq .Destination "/var/lib/postgresql/data"}}{{.Name}}{{end}}{{end}}' "$db")" = monitorai-v22_monitorai_pg_data
test -z "$("${existing[@]}" port postgres 5432 2>/dev/null || true)"
test "$("${existing[@]}" port app 8000)" = 127.0.0.1:8003

previous=$(docker inspect --format '{{.Config.Image}}' "$app")
docker image inspect "$previous" >/dev/null
"${compose[@]}" pull app

current=$("${existing[@]}" exec -T app alembic current | awk 'NF {print $1}')
head=$("${compose[@]}" run --rm --no-deps -T app alembic heads | awk 'NF {print $1}')
if [[ -z "$current" || "$current" != "$head" ]]; then
    echo "Schema-changing release requires a migration plan that preserves rollback compatibility." >&2
    exit 1
fi
"${compose[@]}" run --rm --no-deps -T app alembic upgrade head

printf '%s\n' "$previous" > "$state"
trap 'result=$?; if (( result != 0 )); then rollback || echo "Rollback requires operator recovery" >&2; fi; exit "$result"' EXIT
"${compose[@]}" up -d --no-deps --pull never --wait --wait-timeout 180 app
app=$("${compose[@]}" ps -q app)
test "$(docker inspect --format '{{.Config.Image}}' "$app")" = "$candidate"
test "$("${compose[@]}" ps -q postgres)" = "$db"
test "$("${compose[@]}" port app 8000)" = 127.0.0.1:8003
curl -fsS http://127.0.0.1:8003/health
test "$(curl -sS -o /dev/null -w '%{http_code}' http://127.0.0.1:8003/api/auth/me)" = 401
