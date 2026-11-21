#!/usr/bin/env bash
set -euo pipefail
cd "${REACTORCIDE_CODE_DIR:-/job/src}"
[[ "$REACTORCIDE_EVENT_TYPE" = tag_created ]]
tag=$REACTORCIDE_BRANCH
[[ "$tag" =~ ^v(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)$ ]]
[[ "$(git rev-parse HEAD)" = "$REACTORCIDE_SHA" ]]
repo=https://github.com/catalystcommunity/pysocha.git
[[ "$(git ls-remote --refs "$repo" "refs/tags/$tag" | cut -f1)" = "$REACTORCIDE_SHA" ]]
# A release must contain code that has reached main.
args=()
if [[ "$(git rev-parse --is-shallow-repository)" = true ]]; then args+=(--unshallow); fi
git fetch "${args[@]}" "$repo" refs/heads/main
git merge-base --is-ancestor HEAD FETCH_HEAD

# Stamp a private build tree. A shared checkout can have concurrent readers.
work=$(mktemp -d)
mkdir "$work/src"
git archive HEAD | tar -x -C "$work/src"
cd "$work/src"
sed -i -E "/^\[project\]$/,/^\[/{s/^version = .*/version = \"${tag#v}\"/;}" pyproject.toml
export SOURCE_DATE_EPOCH=$(git -C "${REACTORCIDE_CODE_DIR:-/job/src}" show -s --format=%ct HEAD)
env -u UV_PUBLISH_TOKEN uv build --out-dir "$work/dist"
# uv checks the PyPI index before upload. A retry can complete a partial upload.
uv publish --publish-url https://upload.pypi.org/legacy/ --check-url https://pypi.org/simple/ "$work"/dist/*
