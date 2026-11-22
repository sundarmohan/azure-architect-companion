#!/bin/bash
set -euo pipefail
umask 077
: "${MONITORAI_PUBLIC_HOST:?Set the public DNS name or IPv4 address}"
[[ "$MONITORAI_PUBLIC_HOST" =~ ^[a-zA-Z0-9]([a-zA-Z0-9.-]*[a-zA-Z0-9])?$ ]]
[[ "$MONITORAI_PUBLIC_HOST" == *.* ]]
proxy=rca-ingress-caddy-1
test "$(docker inspect --format '{{.HostConfig.NetworkMode}}' "$proxy")" = host
source=$(docker inspect --format '{{range .Mounts}}{{if eq .Destination "/etc/caddy/Caddyfile"}}{{.Source}}{{end}}{{end}}' "$proxy")
case "$source" in /opt/rca-engine/releases/*/deploy/Caddyfile) ;; *) echo "Unexpected ingress configuration path" >&2; exit 1 ;; esac
work=$(mktemp -d)
staged="/tmp/monitorai-caddy-$$"
trap 'docker exec "$proxy" rm -f "$staged" >/dev/null 2>&1 || true; rm -rf "$work"' EXIT
sudo -n cat "$source" > "$work/original"
if grep -Fxq '# BEGIN MONITORAI V2.2' "$work/original"; then
    grep -Fxq "https://$MONITORAI_PUBLIC_HOST {" "$work/original"
    exit
fi
docker exec "$proxy" caddy adapt --config /etc/caddy/Caddyfile 2>/dev/null |
    python3 -c 'import fnmatch,json,sys
host=sys.argv[1]
servers=json.load(sys.stdin)["apps"]["http"]["servers"]
for server in servers.values():
    for route in server.get("routes", []):
        for match in route.get("match", []):
            if any(fnmatch.fnmatchcase(host, name) for name in match.get("host", [])):
                raise SystemExit("Host already belongs to an existing Caddy route")' "$MONITORAI_PUBLIC_HOST"

cp "$work/original" "$work/updated"
{
    printf '\n# BEGIN MONITORAI V2.2\nhttps://%s {\n' "$MONITORAI_PUBLIC_HOST"
    if [[ "$MONITORAI_PUBLIC_HOST" =~ ^[0-9.]+$ ]]; then
        printf '    tls {\n        issuer acme {\n            profile shortlived\n        }\n    }\n'
    fi
    printf '    reverse_proxy 127.0.0.1:8003\n}\n# END MONITORAI V2.2\n'
} >> "$work/updated"

docker exec -i "$proxy" sh -c 'umask 077; cat > "$1"' sh "$staged" < "$work/updated"
docker exec "$proxy" caddy validate --adapter caddyfile --config "$staged"
sudo -n cmp -s "$source" "$work/original"
sudo -n tee "$source" < "$work/updated" >/dev/null
if ! docker exec "$proxy" caddy reload --adapter caddyfile --config /etc/caddy/Caddyfile; then
    sudo -n tee "$source" < "$work/original" >/dev/null
    docker exec "$proxy" caddy reload --adapter caddyfile --config /etc/caddy/Caddyfile
    exit 1
fi
echo "MonitorAI virtual host added to existing Caddy"
