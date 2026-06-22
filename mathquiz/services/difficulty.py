# services/difficulty.py
import random

def get_zone_from_elo(elo: float) -> int:
    if elo <= 200:
        return 0
    elif elo <= 400:
        return 1
    elif elo <= 600:
        return 2
    elif elo <= 800:
        return 3
    elif elo <= 1000:
        return 4


def sample_difficulty_from_zone(zone: int) -> int:
    zone_probs = {
        0: [1, 0, 0],
        1: [0.7, 0.30, 0.00],
        2: [0.7, 0.2, 0.1],
        3: [0, 0.3, 0.7],
        4: [0, 0, 1],
    }

    probs = zone_probs[zone]
    return random.choices([1, 2, 3], weights=probs, k=1)[0]


def get_difficulty_from_elo(elo: float) -> int:
    zone = get_zone_from_elo(elo)
    return sample_difficulty_from_zone(zone)


def calculate_elo(current_elo: int, correct: bool, time: float, time_limit: int) -> int:
    if not correct:
        S = 0
    else:
        S = -5 / (4 * time_limit * time_limit) * time * time + 2

    
    target = 0.75
    K = 20
    

    new_elo = current_elo + K * (S - target)
    return max(0, min(1000, new_elo))
