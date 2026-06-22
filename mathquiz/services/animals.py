ANIMAL_MAP = {
    '0': '🦁',  
    '1': '🦒',
    '2': '🐘',
    '3': '🦓',
    '4': '🐵',
    '5': '🐍',
    '6': '🐊',
    '7': '🐅',
    '8': '🦩',
    '9': '🦏'
}

def pin_to_animals(pin: str):
    return "".join(ANIMAL_MAP.get(ch, '?') for ch in pin)
