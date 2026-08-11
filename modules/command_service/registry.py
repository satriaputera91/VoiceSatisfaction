from typing import Dict, List, Tuple

# Indonesian 5-point CSAT scale + score map
SATISFACTION_INTENTS: List[Tuple[str, int, List[str]]] = [
    (
        "sangat_tidak_puas",
        1,
        [
            "sangat tidak puas",
            "sangat kecewa",
            "tidak puas sekali",
            "buruk sekali",
            "sangat buruk",
            "parah sekali",
        ],
    ),
    (
        "tidak_puas",
        2,
        [
            "tidak puas",
            "kurang puas",
            "kecewa",
            "kurang memuaskan",
            "tidak memuaskan",
            "jelek",
            "buruk",
        ],
    ),
    (
        "cukup_puas",
        3,
        [
            "cukup puas",
            "lumayan",
            "cukup",
            "biasa saja",
            "cukup memuaskan",
            "standar",
            "biasa",
        ],
    ),
    (
        "puas",
        4,
        [
            "puas",
            "memuaskan",
            "bagus",
            "baik",
            "senang",
            "oke",
            "ok",
        ],
    ),
    (
        "sangat_puas",
        5,
        [
            "sangat puas",
            "sangat memuaskan",
            "luar biasa",
            "sempurna",
            "sangat bagus",
            "sangat baik",
            "mantap",
        ],
    ),
]

GENERAL_TELEPHONY_INTENTS: List[Tuple[str, int, List[str]]] = [
    (
        "repeat_question",
        0,
        [
            "ulangi",
            "mohon ulangi",
            "tidak jelas",
            "repeat",
            "say again",
            "apa tadi",
        ],
    ),
    (
        "speak_to_agent",
        0,
        [
            "bicara dengan agen",
            "operator",
            "manusia",
            "speak to agent",
            "customer service",
        ],
    ),
    (
        "end_call",
        0,
        [
            "selesai",
            "sudah",
            "terima kasih",
            "bye",
            "goodbye",
        ],
    ),
]

SATISFACTION_SCORE_MAP: Dict[str, int] = {
    intent: score for intent, score, _ in (SATISFACTION_INTENTS + GENERAL_TELEPHONY_INTENTS)
}
