from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from catan.controllers.base import Controller
from catan.controllers.random_bot_controller import RandomBotController
from catan.controllers.heuristic_bot_controller import HeuristicBotController
from catan.runners.game_setup import ControllerType


@dataclass(frozen=True)
class ControllerSpec:
    controller_type: ControllerType
    label: str
    is_bot: bool
    factory: Callable[[bool], Controller]


def _random_factory(enable_bot_delay: bool) -> Controller:
    return RandomBotController(enable_delay=enable_bot_delay)


def _heuristic_factory(enable_bot_delay: bool) -> Controller:
    return HeuristicBotController(enable_delay=enable_bot_delay)


_CONTROLLER_SPECS: tuple[ControllerSpec, ...] = (
    ControllerSpec(
        controller_type=ControllerType.RANDOM_BOT,
        label="Random Bot",
        is_bot=True,
        factory=_random_factory,
    ),
    ControllerSpec(
        controller_type=ControllerType.HEURISTIC_BOT,
        label="Heuristic Bot",
        is_bot=True,
        factory=_heuristic_factory,
    ),
)


_CONTROLLER_BY_TYPE = {spec.controller_type: spec for spec in _CONTROLLER_SPECS}


def list_bot_specs() -> tuple[ControllerSpec, ...]:
    return _CONTROLLER_SPECS


def get_bot_spec(controller_type: ControllerType) -> ControllerSpec | None:
    return _CONTROLLER_BY_TYPE.get(controller_type)


def build_bot_controller(controller_type: ControllerType, *, enable_bot_delay: bool) -> Controller:
    spec = get_bot_spec(controller_type)
    if spec is None:
        raise ValueError(f"Unknown bot controller type: {controller_type}")
    return spec.factory(enable_bot_delay)
