#!/usr/bin/env bash

set -e

usage() {
  cat <<EOF
Usage: ${0##*/} <command> [arguments]

Commands:
  setup                Install the locked Python dependencies, including search providers.
  editor [SITE.yaml]   Build and start the editor. Optionally open a site configuration.
  help, -h, --help     Show this help.
EOF
}

repo_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)

case "${1:-}" in
  setup)
    exec uv sync --project "$repo_dir" --locked --all-extras
    ;;
  editor)
    shift
    if (( $# > 1 )); then
      usage >&2
      exit 2
    fi
    exec uv run --project "$repo_dir" --locked --all-extras -- \
      cargo run --locked --manifest-path "$repo_dir/editor/Cargo.toml" -- "$@"
    ;;
  ''|help|-h|--help)
    usage
    ;;
  *)
    printf 'Unknown command: %s\n' "$1" >&2
    usage >&2
    exit 2
    ;;
esac
