"""Use real child processes to test failures in Pagefind communication."""

import os
import sys
import time

import pytest

pytest.importorskip("pagefind.service")

from pysocha.search import build_search_indexes


def run_build(path, timeout=2):
    return build_search_indexes(
        {"outputDir": str(path), "search": [{
            "name": "site", "provider": "pagefind",
            "options": {"indexTimeout": timeout},
        }]},
        [],
    )


@pytest.fixture
def fake_binary(tmp_path, monkeypatch):
    def write(body):
        executable = tmp_path / "pagefind-fake"
        executable.write_text(
            "#!{}\nimport os, signal, sys, time\n".format(sys.executable)
            + "import resource\nresource.setrlimit(resource.RLIMIT_CORE, (0, 0))\n"
            + "open({!r}, 'w').write(str(os.getpid()))\n".format(str(tmp_path / "pid"))
            + body
        )
        executable.chmod(0o700)
        monkeypatch.setenv("PAGEFIND_BINARY_PATH", str(executable))
    yield write
    pid_file = tmp_path / "pid"
    if pid_file.exists():
        with pytest.raises(ProcessLookupError):
            os.kill(int(pid_file.read_text()), 0)


@pytest.mark.skipif(os.name != "posix", reason="POSIX child process signals")
@pytest.mark.parametrize("body, message", [
    ("os.kill(os.getpid(), signal.SIGILL)\n", "SIGILL"),
    ("sys.exit(17)\n", "exit code 17"),
    ("print('invalid protocol,', flush=True)\ntime.sleep(20)\n", "response reader failed"),
    ("import base64\n"
     "frame = base64.b64encode(b'{\"message_id\":1000,\"payload\":{}}')\n"
     "print(frame.decode() + ',', flush=True)\ntime.sleep(20)\n", "response reader failed"),
    ("os.close(1)\nos.close(2)\ntime.sleep(20)\n", "response reader failed"),
])
def test_crash_or_reader_failure_stops_build(tmp_path, fake_binary, body, message):
    fake_binary(body)
    start = time.monotonic()
    with pytest.raises(RuntimeError, match=message):
        run_build(tmp_path)
    assert time.monotonic() - start < 1.5


@pytest.mark.skipif(os.name != "posix", reason="POSIX child process signals")
def test_crash_after_index_creation_is_reported(tmp_path, fake_binary):
    fake_binary("""
import base64, json
data = bytearray()
while not data.endswith(b','):
    data.extend(sys.stdin.buffer.read(1))
request = json.loads(base64.b64decode(data[:-1]))
reply = {'message_id': request['message_id'], 'payload': {'type': 'NewIndex', 'index_id': 0}}
sys.stdout.buffer.write(base64.b64encode(json.dumps(reply).encode()) + b',')
sys.stdout.buffer.flush()
sys.stdin.buffer.read(1)
os.kill(os.getpid(), signal.SIGILL)
""")
    with pytest.raises(RuntimeError, match="SIGILL"):
        run_build(tmp_path)


@pytest.mark.skipif(os.name != "posix", reason="POSIX child process signals")
def test_timeout_kills_a_child_that_ignores_termination(tmp_path, fake_binary):
    fake_binary("signal.signal(signal.SIGTERM, signal.SIG_IGN)\ntime.sleep(20)\n")
    start = time.monotonic()
    with pytest.raises(RuntimeError, match="indexing exceeded 0.5 seconds"):
        run_build(tmp_path, timeout=0.5)
    # Allow the indexing timeout and both bounded cleanup waits.
    assert time.monotonic() - start < 3.5


@pytest.mark.parametrize("value", [0, -1, True, "20", float("inf"), float("nan")])
def test_invalid_timeout_is_rejected(tmp_path, value):
    with pytest.raises(ValueError, match="indexTimeout"):
        run_build(tmp_path, timeout=value)


@pytest.mark.skipif(os.name != "posix", reason="POSIX child process")
def test_protocol_error_is_matched_to_the_original_request(tmp_path, fake_binary):
    fake_binary("""
import base64, json
frame = bytearray()
while not frame.endswith(b','):
    frame.extend(sys.stdin.buffer.read(1))
original = base64.b64decode(frame[:-1]).decode()
reply = {'payload': {'type': 'Error', 'message': 'invalid index configuration', 'original_message': original}}
sys.stdout.buffer.write(base64.b64encode(json.dumps(reply).encode()) + b',')
sys.stdout.buffer.flush()
time.sleep(20)
""")
    with pytest.raises(Exception, match="invalid index configuration"):
        run_build(tmp_path)
