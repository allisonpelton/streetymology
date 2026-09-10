"""A refusal must reach zero HTTP POSTs. That is the whole suite.

The county run is meant to happen once, so every path that declines to send is
worth an executable claim. Each test states one precondition and asserts the
same thing: `fake.posts == 0`. Only the deliberate sends assert 1.

These test our logic against a fake transport. They do not test Anthropic's
behaviour, and passing does not mean a real send works -- nothing here makes a
network call, which is the point.

Three tests guard defects that actually occurred on 2026-09-10, and are the
reason the rest exist:

- `never_retries_a_post`: submit inherited config.session, which retries POST on
  502. A batch could be created, its response lost, and the retry would create
  and bill a second one.
- `unpriced_model_is_not_free`: PRICES is keyed by alias, so a dated model id
  returned $0.00, which reads as free rather than as unknown.
- `verify_refuses_an_unlisted_model`: `claude-sonnet-4-5` was not an id the API
  lists. A wrong id fails every request in the batch.
"""
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from streetymology import build_batch, run_batch

FIXTURE = Path(__file__).parent / "fixture"


class FakeResponse:
    def __init__(self, status_code=200, payload=None, body=b""):
        self.status_code = status_code
        self._payload = payload or {}
        self.text = json.dumps(self._payload)
        self._body = body

    def json(self):
        return self._payload

    def iter_content(self, chunk_size=1):
        yield self._body


class FakeSession:
    """Records calls and makes none. `posts` is the number under test."""
    request_timeout = 5

    def __init__(self, batches=(), models=(), new_batches=1,
                 post_status=200, raise_on_post=None):
        self.batches = [{"id": b, "created_at": "t"} for b in batches]
        self.models = list(models)
        self.new_batches = new_batches
        self.post_status = post_status
        self.raise_on_post = raise_on_post
        self.posts = 0
        self.gets = []

    def get(self, url, **kw):
        self.gets.append(url)
        if url == run_batch.MODELS_API:
            return FakeResponse(payload={"data": [{"id": m} for m in self.models]})
        if url == run_batch.API:
            return FakeResponse(payload={"data": self.batches})
        if url.endswith("/results"):
            return FakeResponse(body=b'{"custom_id": "batch-0000"}\n')
        return FakeResponse(payload={"id": "msgbatch_new0",
                                     "processing_status": "ended",
                                     "request_counts": {"succeeded": 1}})

    def post(self, url, **kw):
        self.posts += 1
        if self.raise_on_post:
            raise self.raise_on_post
        for i in range(self.new_batches):
            self.batches.insert(0, {"id": f"msgbatch_new{i}", "created_at": "t"})
        return FakeResponse(status_code=self.post_status,
                            payload={"id": "msgbatch_new0",
                                     "request_counts": {"processing": 1}})


@pytest.fixture
def env(tmp_path, monkeypatch):
    """Point every path at tmp_path, and never look for a real API key."""
    runs, arts = tmp_path / "runs", tmp_path / "artifacts"
    runs.mkdir()
    arts.mkdir()
    monkeypatch.setattr(run_batch, "RUNS_DIR", runs)
    monkeypatch.setattr(run_batch, "PENDING", runs / "pending.json")
    monkeypatch.setattr(run_batch, "LATEST", runs / "latest.json")
    monkeypatch.setattr(run_batch, "ARTIFACTS_DIR", arts)
    monkeypatch.setattr(run_batch, "_headers", lambda: {"x-api-key": "test"})
    return tmp_path


def use(monkeypatch, fake):
    monkeypatch.setattr(run_batch, "_post_session", lambda: fake)
    monkeypatch.setattr(run_batch, "_session", lambda: fake)
    return fake


def request_file(tmp_path, n=1, model="claude-sonnet-5"):
    path = tmp_path / "batch.jsonl"
    path.write_text("".join(
        json.dumps({"custom_id": f"batch-{i:04d}",
                    "params": {"model": model, "max_tokens": 100,
                               "messages": [{"role": "user", "content": "hi"}]}}) + "\n"
        for i in range(n)))
    path.with_suffix(".index.csv").write_text(
        "custom_id,n,place,street\nbatch-0000,1,x#0,X Street\n")
    return path


def record(env, digest, batch_id="msgbatch_OLD"):
    (run_batch.RUNS_DIR / f"{batch_id}.json").write_text(json.dumps(
        {"batch_id": batch_id, "digest": digest, "model": "claude-sonnet-5",
         "requests": 1, "submitted": "2026-09-10T00:00:00+00:00",
         "index_file": "x.csv"}))


# --- the refusals -----------------------------------------------------------

def test_without_yes_nothing_is_sent(env, monkeypatch):
    fake = use(monkeypatch, FakeSession())
    assert run_batch.submit(request_file(env), yes=False) is None
    assert fake.posts == 0


def test_a_file_already_sent_is_refused(env, monkeypatch):
    fake = use(monkeypatch, FakeSession())
    path = request_file(env)
    record(env, run_batch._digest(path))
    with pytest.raises(SystemExit):
        run_batch.submit(path, yes=True)
    assert fake.posts == 0


def test_an_unconfirmed_submit_blocks_the_next(env, monkeypatch):
    fake = use(monkeypatch, FakeSession())
    run_batch.PENDING.write_text('{"digest": "abc"}')
    with pytest.raises(SystemExit):
        run_batch.submit(request_file(env), yes=True)
    assert fake.posts == 0


def test_more_requests_than_the_ceiling_is_refused(env, monkeypatch):
    fake = use(monkeypatch, FakeSession())
    with pytest.raises(SystemExit):
        run_batch.submit(request_file(env, n=5), yes=True, max_requests=4)
    assert fake.posts == 0


# --- the deliberate sends ---------------------------------------------------

def test_again_overrides_the_duplicate_refusal(env, monkeypatch):
    fake = use(monkeypatch, FakeSession())
    path = request_file(env)
    record(env, run_batch._digest(path))
    run_batch.submit(path, yes=True, again=True)
    assert fake.posts == 1


def test_a_clean_submit_posts_once_and_keeps_the_id(env, monkeypatch):
    fake = use(monkeypatch, FakeSession())
    rec = run_batch.submit(request_file(env), yes=True)
    assert fake.posts == 1
    assert rec["batch_id"] == "msgbatch_new0"
    assert (run_batch.RUNS_DIR / "msgbatch_new0.json").exists()
    assert not run_batch.PENDING.exists()


# --- the crash window -------------------------------------------------------

def test_pending_survives_a_post_that_raises(env, monkeypatch):
    """A lost response may still have created a batch, so the marker stays."""
    use(monkeypatch, FakeSession(raise_on_post=RuntimeError("connection reset")))
    with pytest.raises(RuntimeError):
        run_batch.submit(request_file(env), yes=True)
    assert run_batch.PENDING.exists()


def test_pending_is_cleared_when_the_api_rejects(env, monkeypatch):
    """A 4xx means no batch was created, so the marker must not block the fix."""
    use(monkeypatch, FakeSession(post_status=400))
    with pytest.raises(SystemExit):
        run_batch.submit(request_file(env), yes=True)
    assert not run_batch.PENDING.exists()


def test_two_new_batches_is_reported_as_a_duplicate(env, monkeypatch):
    fake = use(monkeypatch, FakeSession(new_batches=2))
    with pytest.raises(SystemExit):
        run_batch.submit(request_file(env), yes=True)
    assert fake.posts == 1


# --- the three defects of 2026-09-10 ---------------------------------------

def test_the_submit_session_never_retries_a_post():
    url = "https://api.anthropic.com"
    assert run_batch._post_session().get_adapter(url).max_retries.total == 0
    assert run_batch._session().get_adapter(url).max_retries.total > 0


def test_an_unpriced_model_is_not_reported_as_free():
    reqs = [{"params": {"messages": [{"content": "x" * 4000}]}}]
    assert build_batch.estimate(reqs, 40, "claude-fictional-9")["priced"] is False
    assert build_batch.estimate(reqs, 40, build_batch.MODEL_DEFAULT)["priced"] is True
    # PRICES is keyed by alias, so a dated id has to be stripped back to one.
    # The regression is in the lookup, not the flag: assert the money.
    assert build_batch.estimate(reqs, 40, "claude-sonnet-4-5-20250929")["usd"] > 0


def test_verify_refuses_a_model_the_api_does_not_list(env, monkeypatch):
    use(monkeypatch, FakeSession(models=["claude-sonnet-5"]))
    with pytest.raises(SystemExit):
        run_batch.verify("claude-sonnet-4-5")
    assert run_batch.verify("claude-sonnet-5") is True


# --- not paying twice, not downloading twice --------------------------------

def test_fetch_does_not_redownload(env, monkeypatch):
    fake = use(monkeypatch, FakeSession())
    record(env, "d", batch_id="msgbatch_X")
    (run_batch.ARTIFACTS_DIR / "msgbatch_X.results.jsonl").write_text("kept\n")
    out = run_batch.fetch("msgbatch_X")
    assert out.read_text() == "kept\n"
    assert fake.gets == []


def test_exclude_drops_places_already_answered(tmp_path):
    """The trial's places must not appear in the county file that follows it."""
    for sub in ("raw", "derived"):
        shutil.copytree(FIXTURE / sub, tmp_path / sub)
    env = {**os.environ, "STREETYMOLOGY_DATA_DIR": str(tmp_path)}
    for stage in ("measure_streets", "build_context"):
        r = subprocess.run([sys.executable, "-m", f"streetymology.{stage}"],
                           env=env, capture_output=True, text=True)
        assert r.returncode == 0, r.stderr

    def build(*extra):
        out = tmp_path / "b.jsonl"
        r = subprocess.run([sys.executable, "-m", "streetymology.build_batch",
                            "--out", str(out), *extra],
                           env=env, capture_output=True, text=True)
        assert r.returncode == 0, r.stderr
        rows = (tmp_path / "b.index.csv").read_text().splitlines()[1:]
        return [x.split(",")[2] for x in rows]

    everything = build()
    answered = tmp_path / "answered.csv"
    answered.write_text("place,choice\n" + f"{everything[0]},NONE\n")
    rest = build("--exclude", str(answered))

    assert everything[0] not in rest
    assert len(rest) == len(everything) - 1
