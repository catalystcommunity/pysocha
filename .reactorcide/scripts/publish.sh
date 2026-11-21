#!/usr/bin/env bash
set -euo pipefail
cd "${REACTORCIDE_CODE_DIR:-/job/src}"
source "$(dirname "$0")/verify-tag.sh"

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
