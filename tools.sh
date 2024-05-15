#!/usr/bin/env bash

set -e

THISSCRIPT=$(basename $0)

GITHUB_OUTPUT=${GITHUB_OUTPUT:-$(mktemp)}

# Modify for the help message
usage() {
  echo "${THISSCRIPT} command"
  echo "Executes the step command in the script."
  exit 0
}

setup() {
  echo "Not really a thing yet."
}

# This should be last in the script, all other functions are named beforehand.
case "$1" in
  "setup")
    shift
    setup "$@"
    ;;
  *)
    usage
    ;;
esac

exit 0
