from __future__ import annotations


# Simple deterministic PRNG for MVP (LCG, Numerical Recipes constants).
# Kept isolated so it can be replaced later with a stronger generator.
_LCG_A = 1664525
_LCG_C = 1013904223
_LCG_M = 2**32


def next_u32(state: int) -> tuple[int, int]:
    next_state = (_LCG_A * state + _LCG_C) % _LCG_M
    return next_state, next_state


def roll_two_d6(state: int) -> tuple[tuple[int, int], int]:
    v1, s1 = next_u32(state)
    v2, s2 = next_u32(s1)
    die_1 = (v1 % 6) + 1
    die_2 = (v2 % 6) + 1
    return (die_1, die_2), s2
