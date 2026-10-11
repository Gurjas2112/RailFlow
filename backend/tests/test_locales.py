"""SPEC §20.9 — every code the backend can emit has a template in all three locale files."""
import json

import pytest

from railflow.explainer import EXPLAIN_CODES
from railflow.models import RULE_OF, VALIDATOR_RULES
from railflow.proposals import PROPOSAL_CODES
from railflow.reasons import CLASSES, REASON_CODES

from conftest import ROOT

LOCALES = ROOT / "web" / "public" / "locales"


@pytest.mark.parametrize("lang", ["en", "hi", "mr"])
def test_every_backend_code_is_translated(lang):
    d = json.loads((LOCALES / f"{lang}.json").read_text(encoding="utf-8"))
    need = ([f"reason.{c}" for c in REASON_CODES] + [f"proposal.{c}" for c in PROPOSAL_CODES]
            + [f"explain.{c}" for c in EXPLAIN_CODES] + [f"class.{c}" for c in CLASSES]
            + [f"conflictDesc.{c}" for c in RULE_OF] + [f"rule.{r}" for r in VALIDATOR_RULES])
    assert [k for k in need if k not in d] == []


def test_ids_times_and_minutes_are_never_translated():
    for lang in ("hi", "mr"):
        d = json.loads((LOCALES / f"{lang}.json").read_text(encoding="utf-8"))
        assert not any(ch in v for v in d.values() for ch in "०१२३४५६७८९")
