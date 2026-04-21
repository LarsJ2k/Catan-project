from __future__ import annotations

from catan.core.models.action import BuildRoad, BuildSettlement, EndTurn, PlaceSetupRoad, RollDice
from catan.ui.pygame_ui.renderer import extract_legal_targets


def test_extract_legal_targets_splits_nodes_edges_and_buttons() -> None:
    legal = [
        BuildSettlement(player_id=1, node_id=4),
        BuildRoad(player_id=1, edge_id=7),
        PlaceSetupRoad(player_id=1, edge_id=2),
        RollDice(player_id=1),
        EndTurn(player_id=1),
    ]
    nodes, edges, can_roll, can_end = extract_legal_targets(legal)

    assert nodes == {4}
    assert edges == {2, 7}
    assert can_roll is True
    assert can_end is True
