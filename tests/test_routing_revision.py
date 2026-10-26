import hashlib

from helpers import REPO
from intake.routing import ROUTING_REVISION

# sha256 of intake/routing.py at each rules revision. Editing routing.py makes this test fail
# until ROUTING_REVISION is bumped and the new hash is added, so stored routes are re-routed.
PINNED = {
    1: "ed5029fe21af511cb3b3faaeef65aa3d756cb8bf5c8db5ed25222f26644adb27",
}


def test_routing_py_changed_only_together_with_a_revision_bump():
    actual = hashlib.sha256((REPO / "intake" / "routing.py").read_bytes()).hexdigest()
    assert PINNED.get(ROUTING_REVISION) == actual, (
        f"intake/routing.py is now {actual}. Bump ROUTING_REVISION and add this hash to PINNED.")
