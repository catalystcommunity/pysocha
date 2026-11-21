#!/usr/bin/env bash
set -euo pipefail
cd "${REACTORCIDE_CODE_DIR:-/job/src}"
[[ "$REACTORCIDE_EVENT_TYPE" = pull_request_merged && "$REACTORCIDE_BRANCH" = main ]]
[[ "$(git rev-parse HEAD)" = "$REACTORCIDE_SHA" ]]
# Push the merge SHA. GitHub sends a push event for the new tag.
python3 /job/ci/.reactorcide/scripts/tag.py
