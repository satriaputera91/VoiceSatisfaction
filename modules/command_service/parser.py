import logging
from modules.command_service.matcher import FuzzyMatcher, MatchResult

logger = logging.getLogger("VoiceSatisfaction.Parser")


class CommandParser:
    def __init__(self, match_threshold: float = 75.0):
        self.matcher = FuzzyMatcher(threshold=match_threshold)

    def parse(self, text: str) -> MatchResult:
        logger.info(f"Parsing input text: {text!r}")
        result = self.matcher.match(text)
        logger.info(
            f"Parse result -> intent: {result.intent!r}, score: {result.score}, "
            f"confidence: {result.confidence}, status: {result.status}"
        )
        return result
