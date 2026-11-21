# Source this file from a tag release job in the source checkout.
[[ "$REACTORCIDE_EVENT_TYPE" = tag_created ]]
tag=$REACTORCIDE_BRANCH
[[ "$tag" =~ ^v(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)$ ]]
[[ "$(git rev-parse HEAD)" = "$REACTORCIDE_SHA" ]]
repo=https://github.com/catalystcommunity/pysocha.git
[[ "$(git ls-remote --refs "$repo" "refs/tags/$tag" | cut -f1)" = "$REACTORCIDE_SHA" ]]
# Keep fetch state out of the shared checkout.
refs=$(mktemp -d)
git init --bare -q "$refs"
git -C "$refs" fetch -q --filter=blob:none "$repo" refs/heads/main
git -C "$refs" merge-base --is-ancestor "$REACTORCIDE_SHA" FETCH_HEAD
