from __future__ import annotations

import pytest

from coding_kid.events import TurnCancelled
from coding_kid.turn_control import TurnController, TurnLimits


def test_turn_limits_require_positive_values() -> None:
    with pytest.raises(ValueError, match="max_steps"):
        TurnLimits(max_steps=0)


def test_controller_steers_with_bounded_fifo_input() -> None:
    controller = TurnController(TurnLimits(max_pending_inputs=2))
    token = controller.begin()

    assert controller.steer(" first ") is True
    assert controller.steer("second") is True
    assert controller.steer("third") is False
    assert token.cancelled
    assert token.reason == "steered"
    with pytest.raises(TurnCancelled) as raised:
        token.raise_if_cancelled()
    assert raised.value.reason == "steered"
    assert [item.text for item in controller.take_pending()] == ["first", "second"]


def test_controller_uses_fresh_token_after_steer() -> None:
    controller = TurnController()
    first = controller.begin()
    controller.steer("change direction")

    second = controller.next_step_token()

    assert first.cancelled
    assert not second.cancelled
    controller.interrupt()
    assert second.cancelled
    assert second.reason == "interrupted"
    controller.finish()
    assert controller.token is None
