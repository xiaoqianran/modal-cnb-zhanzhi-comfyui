#!/usr/bin/env bash
# Sparse-clone zhanzhi/ComfyUI the way CNB starts a workspace: latest commit,
# no LFS blobs, no venv312. Modal installs Python deps in the image instead.
set -euo pipefail

DEST="${1:-${ZHANZHI_ROOT:-/opt/zhanzhi}}"
REPO_URL="${CNB_REPO_URL:-https://cnb.cool/zhan_zhi/ComfyUI.git}"
REF="${CNB_REPO_REF:-main}"

export GIT_LFS_SKIP_SMUDGE=1
export GIT_TERMINAL_PROMPT=0

if [[ -n "${GITHUB_TOKEN:-}" ]]; then
  git config --global url."https://x-access-token:${GITHUB_TOKEN}@github.com/".insteadOf "https://github.com/"
fi

mkdir -p "$(dirname "$DEST")"

if [[ -d "$DEST/.git" ]]; then
  echo "[clone] updating $DEST from $REPO_URL ($REF)"
  git -C "$DEST" fetch --depth 1 origin "$REF"
  git -C "$DEST" checkout --force FETCH_HEAD
else
  echo "[clone] cloning $REPO_URL ($REF) -> $DEST"
  rm -rf "$DEST"
  git clone --depth 1 --filter=blob:none --sparse --branch "$REF" "$REPO_URL" "$DEST"
fi

git -C "$DEST" sparse-checkout set --no-cone \
  '/ComfyUI/**' \
  '!/ComfyUI/.git_backup/**' \
  '/custom_nodes/**' \
  '/工作流/**' \
  '/assets/**' \
  '!/assets/welcome.gif' \
  '!/assets/tools/cache/**' \
  '!/assets/start_ComfyUI*.sh' \
  '!/assets/welcome.sh*' \
  '/初始化下载' \
  '/README.md' \
  '/.cnb.yml'

# Belt-and-suspenders: these trees are huge and unused on Modal.
rm -rf \
  "$DEST/venv312" \
  "$DEST/ComfyUI/.git_backup" \
  "$DEST/assets/tools/cache" \
  "$DEST/models"

echo "[clone] done: $DEST"
git -C "$DEST" log -1 --oneline
