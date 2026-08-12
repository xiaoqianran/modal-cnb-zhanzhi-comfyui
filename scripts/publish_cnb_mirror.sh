#!/usr/bin/env bash
# Publish a sanitized zhanzhi worktree to a git checkout of branch cnb-mirror.
#
# Usage:
#   publish_cnb_mirror.sh SRC MIRROR
#
# SRC is the clone_cnb.sh destination (still has .git pointing at CNB).
# MIRROR is a git checkout of this repo's cnb-mirror branch (or an empty repo).
# Set MIRROR_PUSH=1 to push HEAD to origin (branch MIRROR_BRANCH, default cnb-mirror).
set -euo pipefail

SRC="${1:?usage: publish_cnb_mirror.sh SRC MIRROR}"
MIRROR="${2:?usage: publish_cnb_mirror.sh SRC MIRROR}"
BRANCH="${MIRROR_BRANCH:-cnb-mirror}"
HERE="$(cd "$(dirname "$0")" && pwd)"

log() { echo "[mirror] $*"; }

if [[ ! -f "$SRC/ComfyUI/main.py" ]]; then
  log "SRC is not a zhanzhi tree: $SRC"
  exit 1
fi

bash "$HERE/sanitize_cnb_tree.sh" "$SRC"

mkdir -p "$MIRROR"
if [[ ! -d "$MIRROR/.git" ]]; then
  git -C "$MIRROR" init --quiet
  git -C "$MIRROR" checkout -B "$BRANCH"
fi

git -C "$MIRROR" config user.name "${GIT_AUTHOR_NAME:-github-actions[bot]}"
git -C "$MIRROR" config user.email "${GIT_AUTHOR_EMAIL:-41898282+github-actions[bot]@users.noreply.github.com}"
git -C "$MIRROR" lfs uninstall --local >/dev/null 2>&1 || true
git -C "$MIRROR" config lfs.fetchexclude "*"
git -C "$MIRROR" config lfs.allowincompletepush true

upstream_sha="unknown"
if git -C "$SRC" rev-parse --is-inside-work-tree >/dev/null 2>&1; then
  upstream_sha="$(git -C "$SRC" log -1 --format=%H 2>/dev/null || echo unknown)"
fi
upstream_url="${CNB_REPO_URL:-https://cnb.cool/zhan_zhi/ComfyUI.git}"
upstream_ref="${CNB_REPO_REF:-main}"
stamp="$(date -u +%Y-%m-%dT%H:%M:%SZ)"

# Replace MIRROR worktree with SRC, keeping MIRROR's .git.
while IFS= read -r -d '' entry; do
  name="$(basename "$entry")"
  case "$name" in
    .git|.github|.cnb-mirror-meta) continue ;;
  esac
  rm -rf "$entry"
done < <(find "$MIRROR" -mindepth 1 -maxdepth 1 -print0)

tar -C "$SRC" \
  --exclude='.git' \
  --exclude='.github' \
  --exclude='.cnb-mirror-meta' \
  -cf - . | tar -C "$MIRROR" -xf -

# Keep CNB LFS *pointers* as regular files. Do not upload missing LFS blobs.
if [[ -f "$MIRROR/.gitattributes" ]]; then
  grep -v 'filter=lfs' "$MIRROR/.gitattributes" > "$MIRROR/.gitattributes.nolfs" || true
  mv "$MIRROR/.gitattributes.nolfs" "$MIRROR/.gitattributes"
fi

git -C "$MIRROR" add -A -- . ':!.cnb-mirror-meta'
if git -C "$MIRROR" diff --cached --quiet; then
  log "no changes vs ${BRANCH} (${upstream_sha})"
  git -C "$MIRROR" reset --quiet
  exit 0
fi

cat > "$MIRROR/.cnb-mirror-meta" <<EOF
source=${upstream_url}
ref=${upstream_ref}
commit=${upstream_sha}
mirrored_at=${stamp}
EOF

git -C "$MIRROR" add -A
git -C "$MIRROR" commit --quiet -m "mirror ${upstream_ref} ${upstream_sha:0:12} at ${stamp}"
log "committed $(git -C "$MIRROR" log -1 --oneline)"

if [[ "${MIRROR_PUSH:-0}" == "1" ]]; then
  log "push origin HEAD:${BRANCH}"
  git -C "$MIRROR" push origin "HEAD:${BRANCH}"
fi
