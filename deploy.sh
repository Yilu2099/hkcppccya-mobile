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
# Refuse to overwrite production-only code changes. Hashing against the saved
# deployed commit catches drift even when local Git and origin are both clean.
deployed_commit=$(ssh -o BatchMode=yes -o StrictHostKeyChecking=yes "$host" "cat '$remote/.deployed-commit'")
[[ "$deployed_commit" =~ ^[0-9a-f]{40}$ ]] || { echo 'Missing valid deployed commit; review production code first.' >&2; exit 5; }
git cat-file -e "$deployed_commit^{commit}" || { echo 'Deployed commit is unavailable locally; review before deploying.' >&2; exit 5; }
while IFS= read -r file; do
  remote_hash=$(ssh -o BatchMode=yes -o StrictHostKeyChecking=yes "$host" "test ! -f '$remote/$file' || sha256sum '$remote/$file'" | awk '{print $1}')
  if git cat-file -e "$deployed_commit:$file" 2>/dev/null; then
    base_hash=$(git show "$deployed_commit:$file" | shasum -a 256 | awk '{print $1}')
    [[ "$remote_hash" == "$base_hash" ]] || { echo "Production code drift: review and merge $file before deploying." >&2; exit 5; }
  else
    [[ -z "$remote_hash" ]] || { echo "Production-only code: review and merge $file before deploying." >&2; exit 5; }
  fi
done < "$list"
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
commit=$(git rev-parse HEAD)
ssh -o BatchMode=yes -o StrictHostKeyChecking=yes "$host" "printf '%s\\n' '$commit' > '$remote/.deployed-commit'"
