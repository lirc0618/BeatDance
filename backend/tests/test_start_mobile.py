import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[2] / "scripts"))

from start_mobile import prepare_clash_direct, restore_clash_proxy


class FakeClashController:
    def __init__(self, *, mode: str = "global", selected: str = "demo-node"):
        self.mode = mode
        self.selected = selected
        self.selections: list[str] = []

    def config(self) -> dict:
        return {"mode": self.mode}

    def global_proxy(self) -> dict:
        return {"now": self.selected, "all": ["DIRECT", self.selected]}

    def select_global(self, name: str) -> None:
        self.selections.append(name)
        self.selected = name


def test_clash_proxy_is_restored_after_tunnel_registration():
    controller = FakeClashController()

    previous = prepare_clash_direct(controller)
    assert previous == "demo-node"
    assert controller.selections == ["DIRECT"]

    restore_clash_proxy(controller, previous)
    assert controller.selections == ["DIRECT", "demo-node"]


def test_non_global_clash_mode_is_left_unchanged():
    controller = FakeClashController(mode="rule")

    previous = prepare_clash_direct(controller)

    assert previous is None
    assert controller.selections == []
