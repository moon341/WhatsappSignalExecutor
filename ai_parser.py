"""Minimal AI parser adapter for WhatsApp trade signals.

This module provides an `AISignalParser` class so the repository can import
`ai_parser.AISignalParser` and exercise the AI parsing code path.

The current implementation is a local wrapper around the existing `SignalParser`
fallback. Replace the `parse` method with a real API call when you want true AI
interpretation.
"""

import logging
from typing import Optional

from parser import SignalParser, TradeSignal

logger = logging.getLogger(__name__)


class AISignalParser:
    def __init__(
        self,
        api_key: str,
        model: str = "llama-3.3-70b-versatile",
        base_url: str = "https://api.groq.com/openai/v1",
        fallback_parser: Optional[SignalParser] = None,
    ):
        self.api_key = api_key
        self.model = model
        self.base_url = base_url.rstrip("/")
        self.fallback_parser = fallback_parser or SignalParser()
        self.logger = logging.getLogger(__name__)

    def parse(self, text: str, sender: str = "") -> Optional[TradeSignal]:
        """Parse a message using AI if available, otherwise use fallback parser."""
        if not text or not text.strip():
            return None

        self.logger.debug(
            "AISignalParser.parse called",
            extra={
                "model": self.model,
                "base_url": self.base_url,
                "sender": sender,
            },
        )

        # Placeholder implementation: use fallback parser.
        # To enable real AI parsing, replace this block with an actual API call.
        try:
            self.logger.debug("AISignalParser: using fallback parser implementation")
            return self.fallback_parser.parse(text, sender)
        except Exception as exc:
            self.logger.error("AISignalParser fallback parser failed.", exc_info=True)
            return None
