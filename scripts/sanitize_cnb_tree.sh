#!/usr/bin/env bash
# Strip CNB trees that must not go to GitHub or into the Modal image:
# nested git packs, venv, models, and blobs over GitHub's 100MB limit.
set -euo pipefail

DEST="${1:?usage: sanitize_cnb_tree.sh DEST}"

log() { echo "[sanitize] $*"; }

rm -rf \
  "$DEST/venv312" \
  "$DEST/ComfyUI/.git_backup" \
  "$DEST/assets/tools/cache" \
  "$DEST/models" \
  "$DEST/输入"

# CNB vendors full git clones inside custom_nodes (often 100MB+ packs).
while IFS= read -r -d '' dir; do
  log "drop $dir"
  rm -rf "$dir"
done < <(find "$DEST" -mindepth 2 \( -type d -name git_backup -o -type d -name .git \) -print0 2>/dev/null)

# GitHub rejects files > 100MB; keep a margin. LFS pointers are tiny.
# Never touch DEST/.git — those packs are the clone itself.
while IFS= read -r -d '' file; do
  log "drop oversized $(du -h "$file" | cut -f1) $file"
  rm -f "$file"
done < <(find "$DEST" -path "$DEST/.git" -prune -o -type f -size +90M -print0 2>/dev/null)

# GitHub pre-receive (GH008) rejects LFS pointer blobs unless the
# objects are uploaded. This mirror is code-only; drop the pointers.
while IFS= read -r -d '' file; do
  first="$(head -n 1 "$file" 2>/dev/null || true)"
  if [[ "$first" == "version https://git-lfs.github.com/spec/v1" ]]; then
    log "drop LFS pointer $file"
    rm -f "$file"
  fi
done < <(find "$DEST" -path "$DEST/.git" -prune -o -type f -size -2k -print0 2>/dev/null)

log "done: $DEST"
