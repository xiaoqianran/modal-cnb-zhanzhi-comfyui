#!/usr/bin/env bash
# Shallow-clone zhanzhi/ComfyUI for Modal image builds.
#
# Why this is not `git clone --depth 1 --filter=blob:none --sparse`:
#   Modal builders are overseas; cnb.cool drops HTTP/2 mid-pack
#   (`curl 92 INTERNAL_ERROR` / `promisor remote` EOF). A single
#   sparse-checkout of custom_nodes is a 2GB+ pack that cannot resume.
#
# What we do instead:
#   1. HTTP/1.1 + retries
#   2. `--depth 1 --filter=blob:none` so the first fetch is trees only
#   3. cone sparse-checkout: root files, then ComfyUI / 工作流 / assets
#   4. each custom node as its own sparse-add (retryable ~10–265MB packs)
#   5. never materialize venv312 / models / 输入 (LFS skipped anyway)
set -euo pipefail

DEST="${1:-${ZHANZHI_ROOT:-/opt/zhanzhi}}"
# Modal / local default: this repo's daily snapshot. The GitHub Action
# overrides these to clone from cnb.cool when refreshing cnb-mirror.
REPO_URL="${CNB_REPO_URL:-https://github.com/xiaoqianran/modal-cnb-zhanzhi-comfyui.git}"
REF="${CNB_REPO_REF:-cnb-mirror}"
RETRIES="${CNB_CLONE_RETRIES:-5}"
RETRY_WAIT="${CNB_CLONE_RETRY_WAIT:-4}"
HTTP_VERSION="${CNB_HTTP_VERSION:-HTTP/1.1}"

export GIT_LFS_SKIP_SMUDGE=1
export GIT_TERMINAL_PROMPT=0
export GIT_HTTP_LOW_SPEED_LIMIT="${GIT_HTTP_LOW_SPEED_LIMIT:-1000}"
export GIT_HTTP_LOW_SPEED_TIME="${GIT_HTTP_LOW_SPEED_TIME:-60}"

HERE="$(cd "$(dirname "$0")" && pwd)"

log() { echo "[clone] $*"; }

retry() {
  local attempt=1
  local delay="$RETRY_WAIT"
  local status=0
  while true; do
    if "$@"; then
      return 0
    fi
    status=$?
    if (( attempt >= RETRIES )); then
      log "giving up after ${attempt} attempts (exit ${status}): $*"
      return "$status"
    fi
    log "attempt ${attempt}/${RETRIES} failed (exit ${status}), retry in ${delay}s"
    sleep "$delay"
    delay=$(( delay * 2 ))
    if (( delay > 60 )); then
      delay=60
    fi
    attempt=$(( attempt + 1 ))
  done
}

git_net() {
  git \
    -c "http.version=${HTTP_VERSION}" \
    -c http.postBuffer=524288000 \
    -c http.lowSpeedLimit=1000 \
    -c http.lowSpeedTime=60 \
    -c core.quotepath=false \
    "$@"
}

git_tree() {
  git -C "$DEST" -c core.quotepath=false ls-tree --name-only "$@"
}

configure_repo() {
  local dir="$1"
  git -C "$dir" config http.version "$HTTP_VERSION"
  git -C "$dir" config http.postBuffer 524288000
  git -C "$dir" config lfs.fetchexclude "*"
  git -C "$dir" config remote.origin.promisor true
  git -C "$dir" config remote.origin.partialclonefilter blob:none
}

configure_github_https() {
  if [[ -z "${GITHUB_TOKEN:-}" && -z "${GH_TOKEN:-}" ]]; then
    return 0
  fi
  local token="${GITHUB_TOKEN:-${GH_TOKEN}}"
  git config --global url."https://x-access-token:${token}@github.com/".insteadOf "https://github.com/"
}

init_empty_repo() {
  log "init $DEST from $REPO_URL ($REF) via ${HTTP_VERSION}, depth=1, blob:none"
  rm -rf "$DEST"
  mkdir -p "$DEST"
  git -C "$DEST" init --quiet
  git -C "$DEST" remote add origin "$REPO_URL"
  configure_repo "$DEST"
  git -C "$DEST" sparse-checkout init --cone
}

fetch_tip() {
  log "fetch origin $REF (trees only)"
  retry git_net -C "$DEST" fetch --depth 1 --filter=blob:none --no-tags origin "$REF"
  git -C "$DEST" checkout --force --quiet FETCH_HEAD
}

sparse_add() {
  local path="$1"
  if [[ -e "$DEST/$path" ]]; then
    log "already present: $path"
    return 0
  fi
  log "sparse-add $path"
  retry git_net -C "$DEST" sparse-checkout add "$path"
  if [[ ! -e "$DEST/$path" ]]; then
    log "sparse-add reported ok but $path is missing"
    return 1
  fi
}

list_custom_nodes() {
  git_tree FETCH_HEAD:custom_nodes 2>/dev/null || true
}

CONE_TOP_DIRS=(ComfyUI 工作流 assets)

materialize() {
  local dir
  for dir in "${CONE_TOP_DIRS[@]}"; do
    if git_tree FETCH_HEAD | grep -Fxq "$dir"; then
      sparse_add "$dir"
    else
      log "skip missing tree: $dir"
    fi
  done

  local node
  local count=0
  while IFS= read -r node; do
    [[ -z "$node" ]] && continue
    count=$((count + 1))
    sparse_add "custom_nodes/${node}"
  done < <(list_custom_nodes)
  log "custom_nodes materialized: ${count}"
}

configure_github_https
mkdir -p "$(dirname "$DEST")"

if [[ -d "$DEST/.git" ]]; then
  log "updating existing checkout $DEST"
  configure_repo "$DEST"
  git -C "$DEST" remote set-url origin "$REPO_URL"
  git -C "$DEST" sparse-checkout init --cone
  fetch_tip
else
  init_empty_repo
  fetch_tip
fi

materialize
bash "$HERE/sanitize_cnb_tree.sh" "$DEST"

if [[ ! -f "$DEST/ComfyUI/main.py" ]]; then
  log "ComfyUI/main.py missing after clone"
  exit 1
fi

log "done: $DEST"
git -C "$DEST" log -1 --oneline
du -sh "$DEST" "$DEST/ComfyUI" "$DEST/custom_nodes" 2>/dev/null || true
