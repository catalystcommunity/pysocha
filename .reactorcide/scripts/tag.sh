#!/usr/bin/env bash
set -euo pipefail
cd "${REACTORCIDE_CODE_DIR:-/job/src}"
[[ "$REACTORCIDE_EVENT_TYPE" = pull_request_merged && "$REACTORCIDE_BRANCH" = main ]]
[[ "$(git rev-parse HEAD)" = "$REACTORCIDE_SHA" ]]
# The runner does not have gh. Use the GitHub refs API to tag the merge SHA.
python3 /job/ci/.reactorcide/scripts/tag.py
