import importlib.util
import os
import subprocess
from pathlib import Path


def test_first_merge_retry_and_next_patch(tmp_path, monkeypatch):
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", os.devnull)
    path = Path(__file__).resolve().parents[1] / ".reactorcide/scripts/tag.py"
    spec = importlib.util.spec_from_file_location("pysocha_release_tag", path)
    tagger = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(tagger)
    upstream = str(tmp_path / "upstream.git")
    work = tmp_path / "work"
    subprocess.run(["git", "init", "--bare", upstream], check=True, capture_output=True)
    subprocess.run(["git", "init", "-b", "main", work], check=True, capture_output=True)
    monkeypatch.chdir(work)
    for key, value in {"name": "Test", "email": "test@example.org"}.items():
        subprocess.run(["git", "config", "user." + key, value], check=True)

    def commit():
        subprocess.run(["git", "commit", "--allow-empty", "-m", "test merge"], check=True)
        return subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip()

    first = commit()
    assert tagger.push_tag(upstream, first, (0, 4, 1), os.environ) == "v0.4.1"
    second = commit()
    assert tagger.push_tag(upstream, second, (0, 4, 1), os.environ) == "v0.4.2"
    assert tagger.push_tag(upstream, first, (0, 4, 1), os.environ) == "v0.4.1"
