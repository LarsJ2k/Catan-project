from __future__ import annotations

from dataclasses import dataclass, field
import json
from pathlib import Path
import re
from typing import Callable, Mapping

from catan.controllers.base import Controller
from catan.controllers.heuristic_params import HeuristicScoringParams, default_family_parameters, merge_with_family_defaults
from catan.controllers.random_bot_controller import RandomBotController
from catan.controllers.heuristic_bot_controller import HeuristicBotController
from catan.controllers.heuristic_v1_baseline_bot_controller import HeuristicV1BaselineBotController
from catan.runners.game_setup import ControllerType


@dataclass(frozen=True)
class ControllerSpec:
    controller_type: ControllerType
    label: str
    is_bot: bool
    factory: Callable[[bool], Controller]


@dataclass(frozen=True)
class BotDefinition:
    bot_id: str
    display_name: str
    base_controller_type: ControllerType
    description: str = ""
    parameters: Mapping[str, float | int | str | bool] = field(default_factory=dict)
    is_builtin: bool = False


def _random_factory(enable_bot_delay: bool) -> Controller:
    return RandomBotController(enable_delay=enable_bot_delay)


def _heuristic_factory(enable_bot_delay: bool) -> Controller:
    return HeuristicBotController(enable_delay=enable_bot_delay)


def _heuristic_v1_baseline_factory(enable_bot_delay: bool) -> Controller:
    return HeuristicV1BaselineBotController(enable_delay=enable_bot_delay)


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
    ControllerSpec(
        controller_type=ControllerType.HEURISTIC_V1_BASELINE,
        label="Heuristic v1 Baseline",
        is_bot=True,
        factory=_heuristic_v1_baseline_factory,
    ),
)


_CONTROLLER_BY_TYPE = {spec.controller_type: spec for spec in _CONTROLLER_SPECS}
_BOT_CATALOG_FILE = Path.home() / ".catan" / "custom_bots.json"

_BUILTIN_BOTS: tuple[BotDefinition, ...] = (
    BotDefinition(
        bot_id="random_bot",
        display_name="Random Bot",
        base_controller_type=ControllerType.RANDOM_BOT,
        description="Chooses uniformly from legal actions.",
        parameters=default_family_parameters(ControllerType.RANDOM_BOT),
        is_builtin=True,
    ),
    BotDefinition(
        bot_id="heuristic_bot",
        display_name="Heuristic Bot",
        base_controller_type=ControllerType.HEURISTIC_BOT,
        description="Greedy bot that scores legal actions.",
        parameters=default_family_parameters(ControllerType.HEURISTIC_BOT),
        is_builtin=True,
    ),
    BotDefinition(
        bot_id="heuristic_v1_baseline",
        display_name="Heuristic v1 Baseline",
        base_controller_type=ControllerType.HEURISTIC_V1_BASELINE,
        description="Stronger first-generation heuristic with road/robber/trade/dev scoring.",
        parameters=default_family_parameters(ControllerType.HEURISTIC_V1_BASELINE),
        is_builtin=True,
    ),
)
_BUILTIN_BY_ID = {definition.bot_id: definition for definition in _BUILTIN_BOTS}


def list_bot_specs() -> tuple[ControllerSpec, ...]:
    return _CONTROLLER_SPECS


def get_bot_spec(controller_type: ControllerType) -> ControllerSpec | None:
    return _CONTROLLER_BY_TYPE.get(controller_type)


def build_bot_controller(controller_type: ControllerType, *, enable_bot_delay: bool) -> Controller:
    spec = get_bot_spec(controller_type)
    if spec is None:
        raise ValueError(f"Unknown bot controller type: {controller_type}")
    return spec.factory(enable_bot_delay)


def _custom_store_path() -> Path:
    return _BOT_CATALOG_FILE


def _slugify(text: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "_", text.lower()).strip("_")
    return slug or "bot"


def list_builtin_bot_definitions() -> tuple[BotDefinition, ...]:
    return _BUILTIN_BOTS


def _load_custom_bot_definitions(*, storage_path: Path | None = None) -> tuple[BotDefinition, ...]:
    path = storage_path or _custom_store_path()
    if not path.exists():
        return ()
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, list):
        return ()
    loaded: list[BotDefinition] = []
    for entry in payload:
        if not isinstance(entry, dict):
            continue
        try:
            loaded.append(
                BotDefinition(
                    bot_id=str(entry["bot_id"]),
                    display_name=str(entry["display_name"]),
                    base_controller_type=ControllerType(str(entry["base_controller_type"])),
                    description=str(entry.get("description", "")),
                    parameters=merge_with_family_defaults(
                        ControllerType(str(entry["base_controller_type"])),
                        dict(entry.get("parameters", {})),
                    ),
                    is_builtin=False,
                )
            )
        except (KeyError, ValueError, TypeError):
            continue
    return tuple(loaded)


def list_bot_definitions(*, storage_path: Path | None = None) -> tuple[BotDefinition, ...]:
    return _BUILTIN_BOTS + _load_custom_bot_definitions(storage_path=storage_path)


def get_bot_definition(bot_id: str, *, storage_path: Path | None = None) -> BotDefinition | None:
    return next((definition for definition in list_bot_definitions(storage_path=storage_path) if definition.bot_id == bot_id), None)


def _write_custom_bot_definitions(definitions: tuple[BotDefinition, ...], *, storage_path: Path | None = None) -> None:
    path = storage_path or _custom_store_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = [
        {
            "bot_id": definition.bot_id,
            "display_name": definition.display_name,
            "base_controller_type": definition.base_controller_type.value,
            "description": definition.description,
            "parameters": dict(definition.parameters),
        }
        for definition in definitions
    ]
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def create_custom_bot_definition(
    *,
    name: str,
    base_bot_id: str,
    description: str,
    parameters: Mapping[str, float | int | str | bool],
    storage_path: Path | None = None,
) -> BotDefinition:
    trimmed = name.strip()
    if not trimmed:
        raise ValueError("Bot name is required.")
    definitions = list_bot_definitions(storage_path=storage_path)
    if any(definition.display_name == trimmed for definition in definitions):
        raise ValueError(f"A bot named '{trimmed}' already exists.")
    base_definition = get_bot_definition(base_bot_id, storage_path=storage_path)
    if base_definition is None:
        raise ValueError(f"Unknown base bot id: {base_bot_id}")

    base_slug = _slugify(trimmed)
    all_ids = {definition.bot_id for definition in definitions}
    candidate = base_slug
    suffix = 2
    while candidate in all_ids:
        candidate = f"{base_slug}_{suffix}"
        suffix += 1

    created = BotDefinition(
        bot_id=candidate,
        display_name=trimmed,
        base_controller_type=base_definition.base_controller_type,
        description=description.strip(),
        parameters=merge_with_family_defaults(base_definition.base_controller_type, parameters),
        is_builtin=False,
    )
    existing_custom = _load_custom_bot_definitions(storage_path=storage_path)
    _write_custom_bot_definitions(existing_custom + (created,), storage_path=storage_path)
    return created


def delete_custom_bot_definition(bot_id: str, *, storage_path: Path | None = None) -> bool:
    existing_custom = _load_custom_bot_definitions(storage_path=storage_path)
    remaining_custom = tuple(definition for definition in existing_custom if definition.bot_id != bot_id)
    if len(remaining_custom) == len(existing_custom):
        return False
    _write_custom_bot_definitions(remaining_custom, storage_path=storage_path)
    return True


def build_bot_controller_from_definition(
    bot_id: str,
    *,
    enable_bot_delay: bool,
    seed: int | None = None,
    delay_seconds: float = 1.2,
    storage_path: Path | None = None,
) -> Controller:
    definition = get_bot_definition(bot_id, storage_path=storage_path)
    if definition is None:
        raise ValueError(f"Unknown bot definition id: {bot_id}")
    parameters = merge_with_family_defaults(definition.base_controller_type, dict(definition.parameters))
    if definition.base_controller_type == ControllerType.RANDOM_BOT:
        return RandomBotController(seed=seed, delay_seconds=delay_seconds, enable_delay=enable_bot_delay)
    if definition.base_controller_type == ControllerType.HEURISTIC_BOT:
        return HeuristicBotController(
            seed=seed,
            delay_seconds=delay_seconds,
            enable_delay=enable_bot_delay,
            heuristic_params=HeuristicScoringParams.from_mapping(parameters),
        )
    if definition.base_controller_type == ControllerType.HEURISTIC_V1_BASELINE:
        return HeuristicV1BaselineBotController(
            seed=seed,
            delay_seconds=delay_seconds,
            enable_delay=enable_bot_delay,
            heuristic_params=HeuristicScoringParams.from_mapping(parameters),
        )
    raise ValueError(f"Unsupported bot base type: {definition.base_controller_type}")
