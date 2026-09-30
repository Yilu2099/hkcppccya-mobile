#!/bin/bash
# Deploy code only. Never overwrite CMS content, identities, environment or media.
set -euo pipefail
cd "$(dirname "$0")"
mode="${1:---check}"
if [[ "$mode" != "--check" && "$mode" != "--apply" ]]; then
  echo "Usage: ./deploy.sh [--check|--apply]" >&2; exit 2
fi
host=t2099-collector
remote=/www/zq-cms
export RSYNC_RSH='ssh -o BatchMode=yes -o StrictHostKeyChecking=yes'
list=$(mktemp)
trap 'rm -f "$list"' EXIT
cat > "$list" <<'FILES'
build.py
src/index.template.html
admin/auth.py
admin/schema.py
admin/media.py
admin/maintenance.py
admin/server.py
admin/publish.py
admin/index.html
admin/static/admin.css
admin/static/admin.js
admin/static/language.js
FILES
# Changed dependencies or image configuration need a separately reviewed rebuild.
for file in admin/requirements.txt admin/Dockerfile; do
  local_hash=$(shasum -a 256 "$file" | awk '{print $1}')
  remote_hash=$(ssh -o BatchMode=yes -o StrictHostKeyChecking=yes "$host" "sha256sum '$remote/$file'" | awk '{print $1}')
  [[ "$local_hash" == "$remote_hash" ]] || { echo "Dependency/image change: review required ($file)" >&2; exit 3; }
done
changes=$(rsync -rcni --files-from="$list" ./ "$host:$remote/")
if [[ -z "$changes" ]]; then echo "Code already matches; no restart needed."; exit 0; fi
printf '%s\n' "$changes"
[[ "$mode" == "--apply" ]] || exit 0
stamp=$(date -u +%Y%m%dT%H%M%SZ)
backup="/www/backups/zq/code-$stamp.tar.gz"
ssh -o BatchMode=yes -o StrictHostKeyChecking=yes "$host" "mkdir -p /www/backups/zq; cd '$remote'; while IFS= read -r file; do test ! -f \"\$file\" || printf '%s\\n' \"\$file\"; done | tar -czf '$backup' -T -" < "$list"
rsync -rc --files-from="$list" ./ "$host:$remote/"
if ! ssh -o BatchMode=yes -o StrictHostKeyChecking=yes "$host" 'docker restart zq-cms >/dev/null && docker exec zq-cms python3 admin/maintenance.py'; then
  ssh -o BatchMode=yes -o StrictHostKeyChecking=yes "$host" "tar -xzf '$backup' -C '$remote' && docker restart zq-cms >/dev/null"
  echo 'Deployment failed; previous code restored. Review public backup before retry.' >&2
  exit 4
fi
echo "Code backup: $backup"
echo "Rollback: ssh $host 'tar -xzf $backup -C $remote && docker restart zq-cms'"
echo "Website published using server-side content; protected data hashes checked."
