#!/usr/bin/env bash
set -euo pipefail
cd "${REACTORCIDE_CODE_DIR:-/job/src}"
target=${1:?desktop target required}
output=${2:?archive directory required}
version=${3:-0.0.0}
work=$(mktemp -d)
trap 'rm -rf "$work"' EXIT
case "$target" in
    linux-x86_64) os=linux; triple=x86_64-unknown-linux-gnu ;;
    linux-arm64) os=linux; triple=aarch64-unknown-linux-gnu ;;
    windows-x86_64) os=windows; triple=x86_64-pc-windows-msvc ;;
    macos-arm64) os=macos; triple=aarch64-apple-darwin ;;
    *) exit 2 ;;
esac
case "$(uname -m)" in
    x86_64) arch=amd64; hash=bc5a158c97c1f7ace1af81c375e8c28bd27e6afeb283fc5b3bfb10777f48fc83 ;;
    aarch64) arch=arm64; hash=02a6f8c1ea519b11d312ea2fb2f45cf3a7a34814a0e61d55d2532adb211ce400 ;;
    *) exit 2 ;;
esac
curl --retry 3 -fsSL "https://github.com/moby/buildkit/releases/download/v0.28.0/buildkit-v0.28.0.linux-$arch.tar.gz" -o "$work/buildkit.tgz"
echo "$hash  $work/buildkit.tgz" | sha256sum -c -
tar -xzf "$work/buildkit.tgz" -C "$work" bin/buildctl
for _ in {1..30}; do
    if "$work/bin/buildctl" debug info >/dev/null 2>&1; then break; fi
    sleep 1
done
"$work/bin/buildctl" build --frontend dockerfile.v0 --local context=editor \
    --local dockerfile=editor/ci --opt "filename=$os.Dockerfile" \
    --opt "build-arg:TARGET=$triple" --output "type=local,dest=$work/bin-out"
binary=pysocha-editor
if [[ "$os" = windows ]]; then binary+=.exe; fi
python3 editor/ci/package.py "$target" "$work/bin-out/$binary" "$output" "$version"
