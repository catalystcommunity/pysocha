"""Create one version tag per merged commit. Reuse the tag on a retry."""

import base64
import os
import re
import subprocess
from pathlib import Path

REPO = "https://github.com/catalystcommunity/pysocha.git"
VERSION = re.compile(r"v(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)")


def next_tag(refs, sha, floor):
    versions = []
    for line in refs.splitlines():
        commit, ref = line.split()
        tag = ref[len("refs/tags/"):]
        match = VERSION.fullmatch(tag)
        if match:
            if commit == sha:
                return tag, False
            versions.append(tuple(map(int, match.groups())))
    if versions:
        major, minor, patch = max(versions)
        floor = max(floor, (major, minor, patch + 1))
    return "v%d.%d.%d" % floor, True


def main():
    sha = os.environ["REACTORCIDE_SHA"]
    section = Path("pyproject.toml").read_text().split("[project]\n", 1)[1].split("\n[", 1)[0]
    floor = tuple(map(int, re.search(r'^version = "(\d+)\.(\d+)\.(\d+)"$', section, re.M).groups()))
    env = os.environ.copy()
    credentials = ("x-access-token:" + env.pop("GH_TOKEN")).encode()
    env.update(
        GIT_TERMINAL_PROMPT="0",
        GIT_CONFIG_COUNT="1",
        GIT_CONFIG_KEY_0="http.https://github.com/.extraHeader",
        GIT_CONFIG_VALUE_0="Authorization: Basic " + base64.b64encode(credentials).decode(),
    )
    push_tag(REPO, sha, floor, env)


def push_tag(repo, sha, floor, env):
    for attempt in range(5):
        refs = subprocess.check_output(["git", "ls-remote", "--tags", "--refs", repo, "refs/tags/v*"], text=True)
        tag, create = next_tag(refs, sha, floor)
        if create:
            # A Git push produces the push webhook that Reactorcide maps to tag_created.
            push = subprocess.run(["git", "push", repo, sha + ":refs/tags/" + tag], env=env)
            if push.returncode:
                # Retry a concurrent allocation. Surface transport and permissions errors.
                if attempt < 4 and subprocess.check_output(["git", "ls-remote", repo, "refs/tags/" + tag]):
                    continue
                push.check_returncode()
        print(tag, sha)
        return tag


if __name__ == "__main__":
    main()
