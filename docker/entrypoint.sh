#!/bin/sh
# Entrypoint for the api, api-dev and tools containers.
#
#   serve       migrate, then run uvicorn (the production api service)
#   serve-dev   migrate, then run uvicorn --reload (api-dev)
#   anything    run it as given, after the steps below (tools, one-off commands)
set -eu

# TA_SECRET_KEY: an explicit value wins. Otherwise the app reads TA_SECRET_KEY_FILE
# (api/config.py), which is generated here on first boot. The key encrypts stored
# credentials: back up the file (the api_data volume) with the database.
if [ -z "${TA_SECRET_KEY:-}" ] && [ -n "${TA_SECRET_KEY_FILE:-}" ] && [ ! -s "$TA_SECRET_KEY_FILE" ]; then
	(umask 077 && python -c 'import secrets; print(secrets.token_urlsafe(48))' > "$TA_SECRET_KEY_FILE")
	echo "ta: generated a new TA_SECRET_KEY in $TA_SECRET_KEY_FILE" >&2
fi

# Dev image only: keep web/node_modules (a Linux-only named volume) in step with the lockfile.
if [ "${TA_NPM_ENSURE:-}" = "1" ] && [ -f /app/web/package-lock.json ]; then
	want=$(sha256sum /app/web/package-lock.json | cut -d' ' -f1)
	have=$(cat /app/web/node_modules/.ta-lock-sha 2>/dev/null || true)
	if [ "$want" != "$have" ]; then
		echo "ta: installing web dependencies (npm ci)" >&2
		(cd /app/web && npm ci --no-audit --no-fund && echo "$want" > node_modules/.ta-lock-sha)
	fi
fi

case "${1:-serve}" in
serve)
	alembic upgrade head
	# --proxy-headers --forwarded-allow-ips='*': the login limiter keys on the real client
	# address from Caddy's X-Forwarded-For. Safe only because compose does not publish
	# this port; Caddy is the only client. Also safe only because Caddy sets X-Forwarded-For
	# itself (no trusted_proxies); adding a trusted upstream proxy later (e.g. Cloudflare)
	# would make the leftmost entry spoofable.
	exec uvicorn api.main:app --host 0.0.0.0 --port 8000 --proxy-headers \
		--forwarded-allow-ips='*' --timeout-graceful-shutdown 5
	;;
serve-dev)
	alembic upgrade head
	exec uvicorn api.main:app --reload --host 0.0.0.0 --port 8000 --timeout-graceful-shutdown 5
	;;
*)
	exec "$@"
	;;
esac
