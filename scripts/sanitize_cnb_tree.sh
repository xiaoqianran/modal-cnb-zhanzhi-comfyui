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
while IFS= read -r -d '' file; do
  log "drop oversized $(du -h "$file" | cut -f1) $file"
  rm -f "$file"
done < <(find "$DEST" -type f -size +90M -print0 2>/dev/null)

log "done: $DEST"
