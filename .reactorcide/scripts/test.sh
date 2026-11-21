#!/usr/bin/env bash
set -euo pipefail
cd "${REACTORCIDE_CODE_DIR:-/job/src}"
out=$(mktemp -d)
uv sync --locked --all-extras
uv run --no-sync pytest --junitxml="${REACTORCIDE_ARTIFACTS_DIR:-$out}/junit.xml"
uv build --out-dir "$out"
uv venv "$out/smoke"
uv pip install --python "$out/smoke/bin/python" "$out"/*.whl
(cd "$out" && smoke/bin/pysocha --help >/dev/null)
