from datetime import date

# Zodiac sign date ranges (month, day) tuples
ZODIAC_SIGNS = [
    ("Козерог", (1, 1), (1, 19)),
    ("Водолей", (1, 20), (2, 18)),
    ("Рыбы", (2, 19), (3, 20)),
    ("Овен", (3, 21), (4, 19)),
    ("Телец", (4, 20), (5, 20)),
    ("Близнецы", (5, 21), (6, 20)),
    ("Рак", (6, 21), (7, 22)),
    ("Лев", (7, 23), (8, 22)),
    ("Дева", (8, 23), (9, 22)),
    ("Весы", (9, 23), (10, 22)),
    ("Скорпион", (10, 23), (11, 21)),
    ("Стрелец", (11, 22), (12, 21)),
    ("Козерог", (12, 22), (12, 31)),
]

ZODIAC_ELEMENTS = {
    "Овен": "Огонь",
    "Телец": "Земля",
    "Близнецы": "Воздух",
    "Рак": "Вода",
    "Лев": "Огонь",
    "Дева": "Земля",
    "Весы": "Воздух",
    "Скорпион": "Вода",
    "Стрелец": "Огонь",
    "Козерог": "Земля",
    "Водолей": "Воздух",
    "Рыбы": "Вода",
}

ZODIAC_QUALITIES = {
    "Овен": "Кардинальный",
    "Телец": "Фиксированный",
    "Близнецы": "Мутабельный",
    "Рак": "Кардинальный",
    "Лев": "Фиксированный",
    "Дева": "Мутабельный",
    "Весы": "Кардинальный",
    "Скорпион": "Фиксированный",
    "Стрелец": "Мутабельный",
    "Козерог": "Кардинальный",
    "Водолей": "Фиксированный",
    "Рыбы": "Мутабельный",
}


def get_zodiac_sign(birth_date: date) -> str:
    """Determine zodiac sign from birth date."""
    month = birth_date.month
    day = birth_date.day

    for sign, (start_m, start_d), (end_m, end_d) in ZODIAC_SIGNS:
        if (month == start_m and day >= start_d) or (month == end_m and day <= end_d):
            return sign

    return "Козерог"  # Fallback


def get_zodiac_info(sign: str) -> dict:
    """Get full zodiac info for a sign."""
    return {
        "sign": sign,
        "element": ZODIAC_ELEMENTS.get(sign, ""),
        "quality": ZODIAC_QUALITIES.get(sign, ""),
    }
