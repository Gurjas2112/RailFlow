"""SPEC §10.2, §20.5 — every number the AI writes is checked against the metrics."""
from railflow.explainer import explain, grounded

S8 = [{"label": "A", "valid": True, "conflicts": 0, "recovery": "FULLY_ASSIGNED", "total_hold_min": 38,
       "weighted_delay": 76, "platform_changes": 2, "unassigned": 0, "trains_affected": 4},
      {"label": "B", "valid": True, "conflicts": 0, "recovery": "FULLY_ASSIGNED", "total_hold_min": 58,
       "weighted_delay": 136, "platform_changes": 1, "unassigned": 0, "trains_affected": 4}]
DIS = ["51218 departure +25 min", "P3 closed 14:30–15:10"]


def test_ungrounded_number_falls_back_to_template():
    res = explain(S8, DIS, "en", chat=lambda s, u: "Revision A saves 99 minutes over B.")
    assert res["explainer_path"] == "template" and res["grounding"] == "failed→template"
    assert "76" in res["text"] and "136" in res["text"] and "99" not in res["text"]


def test_grounded_llm_text_is_kept():
    text = "Revision A moves 2 trains with weighted delay 76; Revision B moves 1 train but costs 136."
    res = explain(S8, DIS, "en", chat=lambda s, u: text)
    assert (res["explainer_path"], res["grounding"], res["text"]) == ("llm", "passed", text)


def test_llm_down_gives_template():
    res = explain(S8, DIS, "en", chat=lambda s, u: None)
    assert res["explainer_path"] == "template" and res["grounding"] == "passed"


def test_hindi_and_marathi_always_use_the_template():
    for lang in ("hi", "mr"):
        called = []
        res = explain(S8, DIS, lang, chat=lambda s, u: called.append(1) or "anything")
        assert res["explainer_path"] == "template" and not called
        assert [p.code for p in res["parts"]][:2] == ["EXPLAIN_REVISION", "EXPLAIN_REVISION"]


def test_agreeing_revisions_are_said_to_agree():
    same = [dict(S8[0], label=x) for x in ("A", "B", "G")]
    res = explain(same, DIS, "en", chat=lambda s, u: None)
    assert res["parts"][0].code == "EXPLAIN_AGREE" and res["parts"][0].params["n"] == 3


def test_grounding_checks_times_and_numbers():
    assert grounded("closed 14:30 for 2 trains", '{"a": "14:30", "b": 2}')
    assert not grounded("closed 14:35", '{"a": "14:30"}')
