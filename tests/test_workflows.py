import re
from pathlib import Path

WORKFLOWS = Path(__file__).resolve().parents[1] / ".github" / "workflows"


def test_third_party_actions_are_pinned_to_a_commit():
    """The holdout workflow can push to main, so an action outside GitHub's own must be
    pinned to a full commit SHA: a moved tag cannot then run new code with that token."""
    uses = [(path.name, ref) for path in WORKFLOWS.glob("*.yml")
            for ref in re.findall(r"uses:\s*([^\s#]+)", path.read_text())]
    assert uses
    loose = [(name, ref) for name, ref in uses
             if not ref.startswith("actions/") and not re.search(r"@[0-9a-f]{40}$", ref)]
    assert loose == []
