"""Create one version tag per merged commit. Reuse the tag on a retry."""

import json
import os
import re
import subprocess
import urllib.error
import urllib.request
from pathlib import Path

REPO = "https://github.com/catalystcommunity/pysocha.git"
VERSION = re.compile(r"v(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)")


def next_tag(refs, sha, floor):
    versions = []
    for line in refs.splitlines():
        commit, ref = line.split()
        tag = ref.split("/")[-1]
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
    for attempt in range(5):
        refs = subprocess.check_output(["git", "ls-remote", "--tags", "--refs", REPO, "refs/tags/v*"], text=True)
        tag, create = next_tag(refs, sha, floor)
        if create:
            request = urllib.request.Request(
                "https://api.github.com/repos/catalystcommunity/pysocha/git/refs",
                data=json.dumps({"ref": "refs/tags/" + tag, "sha": sha}).encode(),
                headers={"Authorization": "Bearer " + os.environ["GH_TOKEN"], "Content-Type": "application/json"},
            )
            try:
                with urllib.request.urlopen(request, timeout=30):
                    pass
            except urllib.error.HTTPError as error:
                if error.code == 422 and attempt < 4:
                    continue
                raise
        print(tag, sha)
        return


if __name__ == "__main__":
    main()
