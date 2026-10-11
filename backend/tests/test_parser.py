"""SPEC §10.1, §20.9, §20.10, §37, §41, §43 — regex fallback, normalisation, proposal validation."""
from railflow.parser_regex import parse_regex
from railflow.proposals import normalise, resolve_platform, validate_proposals
from railflow.timeutil import to_min


def _ev(text):
    return parse_regex(text)["events"]


def _props(station, tt, text, now="13:00"):
    n = normalise(text, [t.id for t in tt.trains])
    r = parse_regex(n.text)
    return validate_proposals(r["events"], r["unparsed"], text, station, tt, to_min(now))


def test_s2_sentence():
    ev = _ev("11209 running 30 min late, platform 3 shut 14:00 to 15:30 for track inspection")
    assert {"type": "delay", "train_id": "11209", "minutes": 30, "kind": "arrival"}.items() <= ev[0].items()
    assert [(e["platform"], e["start"], e["end"]) for e in ev if e["type"] == "closure"] == [("P3", "14:00", "15:30")]


def test_s8_sentence_departure_kind():
    ev = _ev("51218 held at platform 2, departure 25 min late. Platform 3 closed 14:30 to 15:10 for a points check")
    assert [(d["train_id"], d["minutes"], d["kind"]) for d in ev if d["type"] == "delay"] == [("51218", 25, "departure")]
    assert [(c["platform"], c["start"], c["end"]) for c in ev if c["type"] == "closure"] == [("P3", "14:30", "15:10")]


def test_hinglish():
    assert [(e["platform"], e["start"], e["end"]) for e in _ev("PF 3 band hai 14:00 se 15:30 tak")] == [("P3", "14:00", "15:30")]
    (e,) = _ev("PF 3 band hai 2 baje se 3:30 tak")
    assert (e["start"], e["end"], e.get("ambiguous")) == ("14:00", "15:30", True)


def test_devanagari_digits_resolve_platform(station):
    assert resolve_platform("प्लॅटफॉर्म ३", station) == "P3"
    assert resolve_platform("PF 3", station) == "P3"
    assert resolve_platform("फलाट 3", station) == "P3"
    assert resolve_platform("platform 7", station) is None


def test_spoken_train_numbers_normalise(tt_normal):
    ids = [t.id for t in tt_normal.trains]
    for spoken in ("train 1 1 2 0 9 running 30 min late", "11 209 running 30 min late",
                   "गाड़ी संख्या 11209 running 30 min late", "गाडी ११२०९ running 30 min late"):
        assert "11209" in normalise(spoken, ids).text, spoken


def test_spoken_times_normalise(tt_normal):
    assert "14:00 to 15:30" in normalise("platform 3 shut 1400 to 1530", [t.id for t in tt_normal.trains]).text
    assert normalise("PF 3 closed 14.00 to 15.30", []).text.endswith("14:00 to 15:30")


def test_spans_map_back_to_the_original_text(station, tt_normal):
    text = "train 1 1 2 0 9 running 30 min late, platform 3 shut 1400 to 1530"
    ok, rej, _ = _props(station, tt_normal, text)
    assert not rej and {p.type for p in ok} == {"delay", "closure"}
    for p in ok:
        s, e = p.span
        assert 0 <= s < e <= len(text)
    closure = next(p for p in ok if p.type == "closure")
    assert text[closure.span[0]:closure.span[1]].startswith("platform 3")
    assert (closure.start, closure.end) == ("14:00", "15:30")


def test_unknown_train_rejected_not_guessed(station, tt_normal):
    ok, rej, _ = _props(station, tt_normal, "11299 delayed 20 min")
    assert not ok and rej[0].reason.code == "UNKNOWN_TRAIN" and rej[0].train_id is None


def test_nonexistent_platform_rejected(station, tt_normal):
    ok, rej, _ = _props(station, tt_normal, "Platform 7 closed 14:00 to 15:00")
    assert not ok and rej[0].reason.code == "UNKNOWN_PLATFORM"


def test_hallucinated_source_rejected(station, tt_normal):
    ev = [{"type": "delay", "train_id": "11209", "minutes": 30, "source": "11209 is 30 min late"}]
    _, rej, _ = validate_proposals(ev, [], "platform 3 shut 14:00 to 15:30", station, tt_normal, 0)
    assert rej[0].reason.code == "SOURCE_NOT_FOUND"


def test_s2_late_arrival_delay_rejected(station, tt_normal):
    ok, rej, _ = _props(station, tt_normal, "11209 running 30 min late, platform 3 shut 14:00 to 15:30", now="14:05")
    assert [p.type for p in ok] == ["closure"]
    assert rej[0].reason.code == "AT_PLATFORM" and rej[0].reason.params["platform"] == "P3"


def test_departure_delay_at_platform_accepted(station, tt_normal):
    ok, rej, _ = _props(station, tt_normal, "51218 held at platform 2, departure 25 min late", now="14:10")
    assert not rej and (ok[0].kind, ok[0].minutes) == ("departure", 25)


def test_ambiguous_needs_clarification(station, tt_normal):
    ok, _, _ = _props(station, tt_normal, "PF 3 band hai 2 baje se 3:30 tak")
    assert ok[0].status == "needs_clarification"


def test_minutes_out_of_range(station, tt_normal):
    ev = [{"type": "delay", "train_id": "11209", "minutes": 900, "source": "11209 900 min"}]
    _, rej, _ = validate_proposals(ev, [], "11209 900 min", station, tt_normal, 0)
    assert rej[0].reason.code == "MINUTES_OUT_OF_RANGE"


def test_noise_goes_to_unparsed():
    r = parse_regex("Inspection team to report at control at 16:00")
    assert r["events"] == [] and r["unparsed"]
