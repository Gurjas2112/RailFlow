"""SPEC §20.10 — speech-to-text with the model mocked: text only, never mutates state, limits enforced."""
import pytest

from railflow import stt
from conftest import do_login

TRANSCRIPT = "Train 11209, Shivneri Fort Express, running 30 minutes late. Platform 3 shut, 1400 to 1530, for track inspection."


class Seg:
    def __init__(self, text):
        self.text = text


class Info:
    def __init__(self, duration):
        self.duration = duration


class FakeModel:
    def __init__(self, duration=20.7, fail=False):
        self.duration, self.fail, self.calls = duration, fail, []

    def transcribe(self, audio, **kw):
        self.calls.append(kw)
        if self.fail:
            raise RuntimeError("model missing")
        return iter([Seg(TRANSCRIPT)]), Info(self.duration)


@pytest.fixture()
def fake(monkeypatch):
    m = FakeModel()
    stt.set_factory(lambda: m)
    yield m
    stt.set_factory(None)


def test_transcript_lands_as_text_only(client, fake):
    do_login(client, "controller")
    before = client.get("/api/scenario").json()
    r = client.post("/api/disruptions/transcribe", files={"file": ("radio.wav", b"RIFF" + b"\0" * 64)}, data={"lang": "en"})
    assert r.status_code == 200
    assert r.json()["transcript"] == TRANSCRIPT and r.json()["stt_path"] == "whisper-small"
    assert client.get("/api/scenario").json() == before                   # never mutates state
    kw = fake.calls[0]
    assert kw["language"] == "en" and kw["vad_filter"] and kw["beam_size"] == 5 and "11209" in kw["initial_prompt"]


def test_unavailable_when_the_model_fails(client):
    stt.set_factory(lambda: FakeModel(fail=True))
    try:
        do_login(client, "controller")
        r = client.post("/api/disruptions/transcribe", files={"file": ("radio.wav", b"x" * 100)})
        assert r.status_code == 200 and r.json()["stt_path"] == "unavailable" and r.json()["transcript"] == ""
    finally:
        stt.set_factory(None)


def test_size_and_duration_limits_return_413(client):
    stt.set_factory(lambda: FakeModel(duration=75))
    try:
        do_login(client, "controller")
        assert client.post("/api/disruptions/transcribe", files={"file": ("radio.wav", b"x" * 100)}).status_code == 413
        big = b"x" * (2 * 1024 * 1024 + 1)
        assert client.post("/api/disruptions/transcribe", files={"file": ("radio.wav", big)}).status_code == 413
    finally:
        stt.set_factory(None)


def test_only_audio_files_and_only_controllers(client, fake):
    do_login(client, "controller")
    assert client.post("/api/disruptions/transcribe", files={"file": ("notes.txt", b"hi")}).status_code == 400
    client.post("/api/auth/logout")
    do_login(client, "viewer")
    assert client.post("/api/disruptions/transcribe", files={"file": ("radio.wav", b"x")}).status_code == 403


def test_spoken_transcript_parses_after_normalisation(client, fake):
    do_login(client, "controller")
    client.post("/api/scenario/load", json={"scenario_id": "S2"})
    parsed = client.post("/api/disruptions/parse", json={"text": TRANSCRIPT, "now": "13:50"}).json()
    got = {(p["type"], p.get("train_id") or p.get("platform_id"), p.get("minutes") or p.get("start")) for p in parsed["proposals"]}
    assert got == {("delay", "11209", 30), ("closure", "P3", "14:00")}
