#!/usr/bin/env bash
set -euo pipefail
ci=$(dirname "$0")
cd "${REACTORCIDE_CODE_DIR:-/job/src}"
source "$ci/verify-tag.sh"
work=$(mktemp -d)
trap 'rm -rf "$work"' EXIT
for target in linux-x86_64 linux-arm64 windows-x86_64 macos-arm64; do
    env -u GH_TOKEN bash "$ci/build-editor.sh" "$target" "$work/assets" "${tag#v}"
done
case "$(uname -m)" in
    x86_64) arch=amd64; hash=afada88676dfccea384e6cc28ae990b3e31bbc55f9d75c4697f902c757fa462b ;;
    aarch64) arch=arm64; hash=80b467daabeabf4379b5b7138f4b8b47f56670cc615ab288361a602ce413d8bf ;;
    *) exit 2 ;;
esac
curl -fsSL --retry 3 "https://github.com/cli/cli/releases/download/v2.82.1/gh_2.82.1_linux_$arch.tar.gz" -o "$work/gh.tgz"
echo "$hash  $work/gh.tgz" | sha256sum -c -
tar -xzf "$work/gh.tgz" -C "$work" --strip-components=2 "gh_2.82.1_linux_$arch/bin/gh"
export GH_REPO=catalystcommunity/pysocha
gh="$work/gh"
if ! "$gh" release view "$tag" --json isDraft >/dev/null 2>&1; then
    "$gh" release create "$tag" --verify-tag --draft --title "Pysocha $tag" --generate-notes
fi
if [[ "$("$gh" release view "$tag" --json isDraft --jq .isDraft)" = true ]]; then
    "$gh" release upload "$tag" "$work"/assets/* --clobber
    "$gh" release edit "$tag" --draft=false
fi
for archive in "$work"/assets/*; do
    "$gh" release view "$tag" --json assets --jq '.assets[].name' | grep -Fx "$(basename "$archive")"
done
