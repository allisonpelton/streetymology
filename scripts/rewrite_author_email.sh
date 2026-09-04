#!/usr/bin/env bash
# Replace the author/committer email across ALL commits.
#
# GitHub blocks pushes that would expose a private address when
# "Block command line pushes that expose my email" is enabled. Your noreply
# address is at https://github.com/settings/emails and looks like:
#     12345678+username@users.noreply.github.com
#
# Safe to run here only because nothing has been pushed yet. Rewriting history
# after a push forces everyone else to re-clone.
#
# Usage: scripts/rewrite_author_email.sh 12345678+allisonpelton@users.noreply.github.com
set -euo pipefail

NEW="${1:?usage: $0 <new-email>}"
OLD="allisonwpelton@gmail.com"
NAME="allisonpelton"

cd "$(dirname "$0")/.."
BACKUP_DIR="${STREETYMOLOGY_DATA_DIR:-/workspace/streetymology-data}"
BACKUP="$BACKUP_DIR/streetymology-backup-$(date +%Y%m%d-%H%M%S).bundle"
git bundle create "$BACKUP" --all
echo "backup written: $BACKUP"

.venv/bin/git-filter-repo --force --email-callback "
return b'$NEW' if email == b'$OLD' else email
"

git config user.email "$NEW"
git config user.name "$NAME"

echo
echo "remaining commits with the old address: $(git log --format='%ae %ce' --all | grep -c "$OLD" || true)"
git log --format='%h %an <%ae>' | head -3
echo
echo "NOTE: filter-repo removes the 'origin' remote by design. Re-add it after:"
echo "  gh repo create streetymology --private --source=. --remote=origin"
