#!/bin/bash
# Copy the code directories to the public checkout (default ../otlab-public) and refuse if anything
# site-specific would go with them. Docs in the public repo are maintained there, not copied.
set -euo pipefail
HERE=$(cd "$(dirname "$0")/.." && pwd); DST=${1:-$HERE/../otlab-public}
[ -d "$DST/.git" ] || { echo "no git checkout at $DST" >&2; exit 1; }
for d in bin base overlay scenarios tools; do
  rsync -a --delete --exclude __pycache__ --exclude authorized_keys "$HERE/$d/" "$DST/$d/"
done
cp "$HERE/.gitignore" "$DST/.gitignore"; grep -qx 'otlab.json' "$DST/.gitignore" || printf 'otlab.json\nbase/authorized_keys\n' >> "$DST/.gitignore"
PAT=${OTLAB_PRIVATE_PATTERN:?set OTLAB_PRIVATE_PATTERN to an extended regex of things that must never be published}
if git -C "$DST" grep -n -I -i -E "$PAT" -- . ':!otlab.json' | grep -v '^tools/publish.sh'; then
  echo "REFUSING: private details found above; fix them in the private repo and re-run" >&2; exit 2
fi
git -C "$DST" add -A; git -C "$DST" status --short
echo "Staged in $DST. Review, commit and push there."
