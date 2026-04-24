from __future__ import annotations

from dataclasses import dataclass, field
import json
from pathlib import Path
from statistics import median


@dataclass
class V2DecisionProfile:
    decision_time_s: float = 0.0
    legal_prep_time_s: float = 0.0
    filter_forbidden_time_s: float = 0.0
    action_scoring_time_s: float = 0.0
    topn_selection_time_s: float = 0.0
    candidate_simulation_time_s: float = 0.0
    state_copy_time_s: float = 0.0
    apply_action_time_s: float = 0.0
    position_eval_time_s: float = 0.0
    explanation_time_s: float = 0.0
    candidates_considered: int = 0
    legal_action_count: int = 0
    trivial_or_forced: bool = False
    evaluator_component_time_s: dict[str, float] = field(default_factory=dict)


class V2ProfilingStats:
    def __init__(self) -> None:
        self._decisions: list[V2DecisionProfile] = []

    def reset(self) -> None:
        self._decisions.clear()

    def record(self, profile: V2DecisionProfile) -> None:
        self._decisions.append(profile)

    @property
    def decision_count(self) -> int:
        return len(self._decisions)

    def summary(self) -> dict[str, object]:
        decisions = len(self._decisions)
        if decisions == 0:
            return {
                "decisions": 0,
                "avg_decision_ms": 0.0,
                "median_decision_ms": 0.0,
                "max_decision_ms": 0.0,
                "total_time_by_category_ms": {},
                "avg_time_by_category_ms": {},
                "slowest_component": None,
            }

        decision_ms = [entry.decision_time_s * 1000.0 for entry in self._decisions]
        category_totals_s = {
            "legal_prep": sum(entry.legal_prep_time_s for entry in self._decisions),
            "filter_forbidden": sum(entry.filter_forbidden_time_s for entry in self._decisions),
            "action_scoring": sum(entry.action_scoring_time_s for entry in self._decisions),
            "topn_selection": sum(entry.topn_selection_time_s for entry in self._decisions),
            "candidate_simulation": sum(entry.candidate_simulation_time_s for entry in self._decisions),
            "state_copy": sum(entry.state_copy_time_s for entry in self._decisions),
            "apply_action": sum(entry.apply_action_time_s for entry in self._decisions),
            "position_eval": sum(entry.position_eval_time_s for entry in self._decisions),
            "explanation": sum(entry.explanation_time_s for entry in self._decisions),
        }
        evaluator_component_totals: dict[str, float] = {}
        for entry in self._decisions:
            for name, elapsed in entry.evaluator_component_time_s.items():
                evaluator_component_totals[name] = evaluator_component_totals.get(name, 0.0) + elapsed

        slowest_component = None
        if evaluator_component_totals:
            slowest_name = max(evaluator_component_totals, key=evaluator_component_totals.get)
            slowest_component = {
                "name": slowest_name,
                "total_ms": round(evaluator_component_totals[slowest_name] * 1000.0, 3),
            }

        return {
            "decisions": decisions,
            "avg_decision_ms": round(sum(decision_ms) / decisions, 3),
            "median_decision_ms": round(float(median(decision_ms)), 3),
            "max_decision_ms": round(max(decision_ms), 3),
            "trivial_or_forced_decisions": sum(1 for entry in self._decisions if entry.trivial_or_forced),
            "avg_candidates_considered": round(
                sum(entry.candidates_considered for entry in self._decisions) / decisions,
                3,
            ),
            "total_time_by_category_ms": {
                name: round(total * 1000.0, 3) for name, total in category_totals_s.items()
            },
            "avg_time_by_category_ms": {
                name: round((total / decisions) * 1000.0, 3) for name, total in category_totals_s.items()
            },
            "evaluator_component_total_ms": {
                name: round(total * 1000.0, 3) for name, total in evaluator_component_totals.items()
            },
            "slowest_component": slowest_component,
        }

    def formatted_summary(self) -> str:
        summary = self.summary()
        if summary["decisions"] == 0:
            return "V2 Profiling Summary\ndecisions: 0"
        lines = [
            "V2 Profiling Summary",
            f"decisions: {summary['decisions']}",
            f"avg_decision_ms: {summary['avg_decision_ms']}",
            f"median_decision_ms: {summary['median_decision_ms']}",
            f"max_decision_ms: {summary['max_decision_ms']}",
            "",
            "time breakdown (avg ms):",
        ]
        avg_breakdown = summary["avg_time_by_category_ms"]
        for name in (
            "legal_prep",
            "filter_forbidden",
            "action_scoring",
            "topn_selection",
            "candidate_simulation",
            "state_copy",
            "apply_action",
            "position_eval",
            "explanation",
        ):
            lines.append(f"- {name}: {avg_breakdown.get(name, 0.0)}")
        slowest = summary.get("slowest_component")
        if slowest is not None:
            lines.extend(["", "slowest evaluator component:", f"- {slowest['name']}: {slowest['total_ms']} ms total"])
        return "\n".join(lines)

    def write_json(self, path: Path) -> Path:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(self.summary(), indent=2), encoding="utf-8")
        return path


GLOBAL_V2_PROFILING_STATS = V2ProfilingStats()
