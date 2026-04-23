from __future__ import annotations

import pytest

from catan.controllers.human_controller import HumanController, NoActionAvailableYet
from catan.core.models.action import DiscardResources, EndTurn, ProposePlayerTrade
from catan.core.models.enums import ResourceType


def test_propose_player_trade_intent_is_accepted_even_if_not_in_legal_action_list() -> None:
    controller = HumanController()
    action = ProposePlayerTrade(
        player_id=1,
        offered_resources=((ResourceType.GRAIN, 1),),
        requested_resources=((ResourceType.ORE, 1),),
    )
    controller.submit_action_intent(action)

    chosen = controller.choose_action(observation=None, legal_actions=[EndTurn(player_id=1)])  # type: ignore[arg-type]

    assert chosen == action


def test_empty_discard_intent_is_rejected() -> None:
    controller = HumanController()
    controller.submit_action_intent(DiscardResources(player_id=1, resources=tuple()))

    legal = [DiscardResources(player_id=1, resources=((ResourceType.BRICK, 2),))]

    with pytest.raises(NoActionAvailableYet):
        controller.choose_action(observation=None, legal_actions=legal)  # type: ignore[arg-type]
