from __future__ import annotations

from catan.controllers.human_controller import HumanController, NoActionAvailableYet
from catan.core.engine import apply_action, get_legal_actions, get_observation
from catan.core.models.state import GameState


class LocalPygameRunner:
    """Orchestrates UI + controllers + engine. Pygame wiring is added in UI layer."""

    def tick(self, state: GameState, controller: HumanController, player_id: int) -> GameState:
        legal_actions = get_legal_actions(state, player_id)
        observation = get_observation(state, player_id)
        try:
            action = controller.choose_action(observation, legal_actions)
        except NoActionAvailableYet:
            return state
        return apply_action(state, action)
