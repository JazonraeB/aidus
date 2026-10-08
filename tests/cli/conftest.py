import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "cli" / "src"))


@pytest.fixture(autouse=True)
def isolated_state(tmp_path, monkeypatch):
    """Keep writer ids and logs out of the real user state directory."""
    state = tmp_path / "_state"
    monkeypatch.setenv("AIDUS_STATE_DIR", str(state))
    return state
