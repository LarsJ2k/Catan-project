from __future__ import annotations


# Deterministic XorShift32-based PRNG for repeatable simulations.
def next_u32(state: int) -> tuple[int, int]:
    x = state & 0xFFFFFFFF
    if x == 0:
        x = 0x6D2B79F5  # avoid zero-lock state
    x ^= (x << 13) & 0xFFFFFFFF
    x ^= (x >> 17) & 0xFFFFFFFF
    x ^= (x << 5) & 0xFFFFFFFF
    return x, x


def roll_two_d6(state: int) -> tuple[tuple[int, int], int]:
    v1, s1 = next_u32(state)
    v2, s2 = next_u32(s1)
    die_1 = (v1 % 6) + 1
    die_2 = (v2 % 6) + 1
    return (die_1, die_2), s2
