import json
from pathlib import Path

import pytest

from biosbom_agentkg.multiagent.models import Case


@pytest.fixture
def case():
    root = Path(__file__).resolve().parents[1]
    return Case.model_validate(json.loads((root / "examples/rnaseq-case.json").read_text()))
