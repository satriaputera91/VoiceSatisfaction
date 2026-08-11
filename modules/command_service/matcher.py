import re
from typing import NamedTuple, Optional
from rapidfuzz import fuzz, process
from modules.command_service.registry import (
    SATISFACTION_INTENTS,
    GENERAL_TELEPHONY_INTENTS,
    SATISFACTION_SCORE_MAP,
)


class MatchResult(NamedTuple):
    intent: str
    score: int
    confidence: float
    matched_phrase: str
    status: str


class FuzzyMatcher:
    def __init__(self, threshold: float = 75.0):
        self.threshold = threshold
        self.phrase_to_intent: dict[str, tuple[str, int]] = {}
        self.all_phrases: list[str] = []

        all_definitions = SATISFACTION_INTENTS + GENERAL_TELEPHONY_INTENTS
        for intent, score, phrases in all_definitions:
            for phrase in phrases:
                norm_phrase = self._normalize(phrase)
                self.phrase_to_intent[norm_phrase] = (intent, score)
                self.all_phrases.append(norm_phrase)

    def _normalize(self, text: str) -> str:
        text = text.lower().strip()
        text = re.sub(r"[^\w\s]", "", text)
        return text

    def match(self, text: str) -> MatchResult:
        normalized = self._normalize(text)
        if not normalized:
            return MatchResult(
                intent="unknown",
                score=0,
                confidence=0.0,
                matched_phrase="",
                status="unknown",
            )

        match = process.extractOne(
            normalized,
            self.all_phrases,
            scorer=fuzz.WRatio,
        )

        if match:
            best_phrase, score, _ = match
            intent, intent_score = self.phrase_to_intent[best_phrase]

            if score >= self.threshold:
                # Format intent name cleanly without underscores if needed, or keep canonical snake_case
                # Return canonical intent label (e.g. "sangat_puas" or display label "sangat puas")
                display_intent = intent.replace("_", " ")
                return MatchResult(
                    intent=display_intent,
                    score=intent_score,
                    confidence=round(score, 1),
                    matched_phrase=best_phrase,
                    status="success",
                )
            else:
                return MatchResult(
                    intent="unknown",
                    score=0,
                    confidence=round(score, 1),
                    matched_phrase=best_phrase,
                    status="low_confidence",
                )

        return MatchResult(
            intent="unknown",
            score=0,
            confidence=0.0,
            matched_phrase="",
            status="unknown",
        )
