"""
Signal Parser for XAUUSD (Gold) WhatsApp Trade Signals.

Handles real-world signal formats including:
  - Pips-based TP/SL: "TP.1 90 PIPS", "SL:40 pips out from end of zone"
  - Absolute price TP/SL: "TP1 4354", "SL 4392"
  - OPEN TP: "TP.3 OPEN" (no fixed TP, let it run)
  - Entry zones: "BUY LIMIT:4328-4325.50", "Sell Gold 4384-88"
  - Break-even: "AFTER TP.1 SL MOVE TO BE"
  - Abbreviated zones: "4384-88" → 4384-4388
  - Numbered TPs with dots: "TP.1", "TP.2", "TP.3"
  - Timeframe context: "H1 setup.", "M30 setup."

Usage:
    from parser import SignalParser
    parser = SignalParser()
    signal = parser.parse(message_text)
"""

import re
import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional, List

logger = logging.getLogger(__name__)


@dataclass
class TradeSignal:
    """Represents a parsed trade signal."""
    signal_id: str = ""
    timestamp: str = ""
    symbol: str = "XAUUSD"
    side: str = ""              # "BUY" or "SELL"
    entry_type: str = "MARKET"  # "MARKET", "LIMIT", "STOP"
    entry_min: float = 0.0      # lower bound of entry zone
    entry_max: float = 0.0      # upper bound of entry zone (same as entry_min for market)
    stop_loss: float = 0.0      # SL value (price or pips depending on sl_type)
    sl_type: str = "PRICE"      # "PRICE" or "PIPS"
    take_profits: List[float] = field(default_factory=list)  # TP values
    tp_type: str = "PRICE"      # "PRICE" or "PIPS"
    move_to_be: bool = False    # Move SL to break-even after TP1
    confidence: float = 0.0
    source_sender: str = ""
    timeframe: str = ""         # "H1", "M30", etc.
    raw_text: str = ""

    def to_dict(self):
        return {
            "signal_id": self.signal_id,
            "timestamp": self.timestamp,
            "symbol": self.symbol,
            "side": self.side,
            "entry_type": self.entry_type,
            "entry_min": self.entry_min,
            "entry_max": self.entry_max,
            "stop_loss": self.stop_loss,
            "sl_type": self.sl_type,
            "take_profits": self.take_profits,
            "tp_type": self.tp_type,
            "move_to_be": self.move_to_be,
            "confidence": self.confidence,
            "source_sender": self.source_sender,
            "timeframe": self.timeframe,
            "raw_text": self.raw_text,
        }

    def to_pipe_string(self):
        """Serialize to pipe-delimited format for MT5 EA consumption.

        Format:
            id|timestamp|symbol|side|entry_type|entry_min|entry_max|sl|sl_type|tps|tp_type|move_to_be|confidence|raw_text
        """
        tp_str = "/".join(str(tp) for tp in self.take_profits)
        parts = [
            self.signal_id,
            self.timestamp,
            self.symbol,
            self.side,
            self.entry_type,
            f"{self.entry_min:.5f}",
            f"{self.entry_max:.5f}",
            f"{self.stop_loss:.5f}",
            self.sl_type,
            tp_str if tp_str else "0",
            self.tp_type,
            "1" if self.move_to_be else "0",
            f"{self.confidence:.2f}",
            self.raw_text.replace("|", "/").replace("\n", " ")[:300],
        ]
        return "|".join(parts)

    @staticmethod
    def from_pipe_string(line):
        """Deserialize from pipe-delimited format."""
        parts = line.strip().split("|")
        if len(parts) < 13:
            return None
        try:
            sig = TradeSignal()
            sig.signal_id = parts[0]
            sig.timestamp = parts[1]
            sig.symbol = parts[2]
            sig.side = parts[3]
            sig.entry_type = parts[4] if len(parts) > 4 else "MARKET"
            sig.entry_min = float(parts[5])
            sig.entry_max = float(parts[6])
            sig.stop_loss = float(parts[7])
            sig.sl_type = parts[8] if parts[8] else "PRICE"
            tp_str = parts[9]
            if tp_str and tp_str != "0":
                sig.take_profits = [float(x) for x in tp_str.split("/") if x.strip()]
            sig.tp_type = parts[10] if parts[10] else "PRICE"
            sig.move_to_be = parts[11] == "1" if len(parts) > 11 else False
            sig.confidence = float(parts[12]) if len(parts) > 12 else 0.0
            if len(parts) > 13:
                sig.raw_text = parts[13]
            return sig
        except (ValueError, IndexError) as e:
            logger.error(f"Failed to parse pipe string: {e}")
            return None


class SignalParser:
    """
    Flexible parser for XAUUSD/Gold trade signals from WhatsApp messages.
    """

    SYMBOL_ALIASES = ["XAUUSD", "GOLD", "XAU/USD", "XAU", "GOLD SPOT"]
    DEFAULT_PIP_VALUE = 1.0  # 1 pip = $1.00 for XAUUSD

    def __init__(self, symbol_aliases=None, default_symbol="XAUUSD",
                 min_confidence=0.4, pip_value=None):
        self.default_symbol = default_symbol
        self.min_confidence = min_confidence
        if symbol_aliases:
            self.SYMBOL_ALIASES = symbol_aliases
        if pip_value is not None:
            self.DEFAULT_PIP_VALUE = pip_value
        self._compile_patterns()

    def _compile_patterns(self):
        """Precompile regex patterns."""
        # Symbol pattern
        sym = "|".join(re.escape(a) for a in self.SYMBOL_ALIASES)
        self.re_symbol = re.compile(sym, re.IGNORECASE)

        # Side pattern - includes LIMIT/STOP order types
        self.re_side = re.compile(
            r'\b(BUY\s*(?:LIMIT|STOP)?|SELL\s*(?:LIMIT|STOP)?|LONG|SHORT)\b',
            re.IGNORECASE
        )

        # Timeframe pattern: "H1 setup.", "M30 setup.", "H4 setup"
        self.re_timeframe = re.compile(
            r'\b(MN|W1|D1|H4|H1|M\d{1,2})\s*(?:setup|chart|timeframe|tf)\b',
            re.IGNORECASE
        )

        # Entry zone patterns
        # "BUY LIMIT:4328-4325.50" or "BUY LIMIT: 4328-4325.50"
        self.re_entry_with_prefix = re.compile(
            r'(?:BUY|SELL)\s*(?:LIMIT|STOP)?\s*[:\s]*'
            r'(\d{3,5}(?:\.\d{1,5})?)\s*[-\u2013\u2014]\s*(\d{2,5}(?:\.\d{1,5})?)',
            re.IGNORECASE
        )
        # "Sell Gold 4384-88" - symbol then zone
        self.re_entry_after_symbol = re.compile(
            r'(?:GOLD|XAUUSD|XAU)\s+(\d{3,5}(?:\.\d{1,5})?)\s*[-\u2013\u2014]\s*(\d{2,5}(?:\.\d{1,5})?)',
            re.IGNORECASE
        )
        # Entry with @ prefix: "@ 2350" or "@ 2350-2352"
        self.re_entry_at_zone = re.compile(
            r'@\s*(\d{3,5}(?:\.\d{1,5})?)\s*[-\u2013\u2014]\s*(\d{3,5}(?:\.\d{1,5})?)',
            re.IGNORECASE
        )
        self.re_entry_at_single = re.compile(
            r'@\s*(\d{3,5}(?:\.\d{1,5})?)',
            re.IGNORECASE
        )
        # Entry with "Entry:" or "ENTER:" prefix
        self.re_entry_keyword = re.compile(
            r'(?:ENTRY|ENTER|ENTERY|PRICE)\s*[:\s]*(\d{3,5}(?:\.\d{1,5})?)'
            r'(?:\s*[-\u2013\u2014]\s*(\d{3,5}(?:\.\d{1,5})?))?',
            re.IGNORECASE
        )
        # Bare entry zone after side: "BUY 2350" or "BUY 2350-2352"
        self.re_entry_bare = re.compile(
            r'(?:BUY|SELL|LONG|SHORT)\s+'
            r'(\d{4,5}(?:\.\d{1,5})?)'
            r'(?:\s*[-\u2013\u2014]\s*(\d{2,5}(?:\.\d{1,5})?))?',
            re.IGNORECASE
        )
        # Bare zone (fallback): "2350-2352" anywhere in text
        self.re_entry_zone_bare = re.compile(
            r'\b(\d{4,5}(?:\.\d{1,5})?)\s*[-\u2013\u2014]\s*(\d{4,5}(?:\.\d{1,5})?)\b'
        )

        # Stop loss patterns
        # "SL:40 pips out from end of zone" or "SL: 40 pips" or "SL 40 pips"
        self.re_sl_pips = re.compile(
            r'(?:STOP\s*LOSS|STOP\s*L|SL|S/L|STOP)\s*[:\s\-]*\s*(\d+(?:\.\d+)?)\s*PIPS?\b',
            re.IGNORECASE
        )
        # "SL 4392" or "SL: 4392" or "Stop Loss: 4392" (absolute price)
        self.re_sl_price = re.compile(
            r'(?:STOP\s*LOSS|STOP\s*L|SL|S/L|STOP)\s*[:\s\-]*\s*(\d{3,5}(?:\.\d{1,5})?)\b',
            re.IGNORECASE
        )

        # Take profit patterns
        # Numbered TPs with dots: "TP.1 90 PIPS" or "TP.1: 90 PIPS"
        # Also handles "TP1 90 PIPS" and "TP 1 90 PIPS"
        self.re_tp_numbered_pips = re.compile(
            r'(?:TP|TAKE\s*PROFIT|T/P)\s*\.?\s*(\d+)\s*[:\s\-]+\s*'
            r'(\d+(?:\.\d+)?)\s*PIPS?',
            re.IGNORECASE
        )
        # Numbered TPs with absolute prices: "TP1 4354" or "TP.1: 4354"
        self.re_tp_numbered_price = re.compile(
            r'(?:TP|TAKE\s*PROFIT|T/P)\s*\.?\s*(\d+)\s*[:\s\-]+\s*'
            r'(\d{3,5}(?:\.\d{1,5})?)',
            re.IGNORECASE
        )
        # Numbered TP that is OPEN: "TP.3 OPEN" or "TP3 OPEN"
        self.re_tp_numbered_open = re.compile(
            r'(?:TP|TAKE\s*PROFIT|T/P)\s*\.?\s*(\d+)\s*[:\s\-]*\s*OPEN',
            re.IGNORECASE
        )
        # List TPs (slash or comma): "TP: 2345/2355/2365" or "TP: 2360, 2370, 2380"
        self.re_tp_list = re.compile(
            r'(?:TP|TAKE\s*PROFIT|T/P)\s*[:\s\-]*\s*([\d.,/\s]+)',
            re.IGNORECASE
        )

        # Break-even pattern: "AFTER TP.1 SL MOVE TO BE" or "MOVE SL TO BE AFTER TP1"
        self.re_move_to_be = re.compile(
            r'(?:AFTER|MOVE|MOVE\s*SL|MOVE\s*STOP)\s*(?:TP\.?\s*\d+|TAKE\s*PROFIT\s*\d+)?\s*'
            r'(?:SL|STOP\s*LOSS)?\s*(?:MOVE\s*TO|TO)\s*BE\b',
            re.IGNORECASE
        )
        # Also match "SL TO BE" or "SL TO BREAKEVEN"
        self.re_move_to_be_alt = re.compile(
            r'(?:SL|STOP\s*LOSS)\s*TO\s*(?:BE|BREAKEVEN|BREAK\s*EVEN)\b',
            re.IGNORECASE
        )

    def _normalize_zone(self, price1: float, price2: float) -> tuple:
        """Normalize a zone so entry_min < entry_max."""
        return (min(price1, price2), max(price1, price2))

    def _expand_abbreviated_price(self, first_str: str, second_str: str) -> float:
        """
        Expand abbreviated second price in a zone.
        "4384-88" → 4388.0, "4328-4325.50" → 4325.50
        """
        second_str = second_str.strip()
        # If second number has fewer integer digits than first, prepend from first
        first_int_part = first_str.split(".")[0]
        if "." in second_str:
            second_int_part = second_str.split(".")[0]
            second_dec = second_str.split(".", 1)[1]
        else:
            second_int_part = second_str
            second_dec = ""

        if len(second_int_part) < len(first_int_part):
            # Prepend missing leading digits
            prefix = first_int_part[:len(first_int_part) - len(second_int_part)]
            expanded = prefix + second_int_part
            if second_dec:
                expanded += "." + second_dec
            return float(expanded)
        return float(second_str)

    def parse(self, text: str, sender: str = "") -> Optional[TradeSignal]:
        """Parse a WhatsApp message into a TradeSignal."""
        if not text or not text.strip():
            return None

        raw = text.strip()
        confidence = 0.0

        # Extract timeframe context
        timeframe = ""
        tf_match = self.re_timeframe.search(raw)
        if tf_match:
            timeframe = tf_match.group(1).upper()
            confidence += 0.05

        # Must have a side (buy/sell/long/short, optionally with LIMIT/STOP)
        side_match = self.re_side.search(raw)
        if not side_match:
            return None

        side_raw = side_match.group(1).upper().strip()
        # Determine side and order type
        if "BUY" in side_raw or "LONG" in side_raw:
            side = "BUY"
        else:
            side = "SELL"

        # Check for LIMIT or STOP order type
        entry_type = "MARKET"
        if "LIMIT" in side_raw:
            entry_type = "LIMIT"
            confidence += 0.1
        elif "STOP" in side_raw:
            entry_type = "STOP"
            confidence += 0.1

        confidence += 0.2  # Found a side

        # Check for symbol
        symbol = self.default_symbol
        sym_match = self.re_symbol.search(raw)
        if sym_match:
            symbol = self.default_symbol  # Normalize
            confidence += 0.1

        # Extract entry prices
        entry_min = 0.0
        entry_max = 0.0

        # Try entry with BUY/SELL LIMIT: prefix
        entry_match = self.re_entry_with_prefix.search(raw)
        if entry_match:
            p1 = float(entry_match.group(1))
            p2 = self._expand_abbreviated_price(entry_match.group(1), entry_match.group(2))
            entry_min, entry_max = self._normalize_zone(p1, p2)
            confidence += 0.3
        else:
            # Try "Sell Gold 4384-88" pattern
            entry_match = self.re_entry_after_symbol.search(raw)
            if entry_match:
                p1 = float(entry_match.group(1))
                p2 = self._expand_abbreviated_price(entry_match.group(1), entry_match.group(2))
                entry_min, entry_max = self._normalize_zone(p1, p2)
                confidence += 0.3
            else:
                # Try @ prefix zone
                entry_match = self.re_entry_at_zone.search(raw)
                if entry_match:
                    p1 = float(entry_match.group(1))
                    p2 = float(entry_match.group(2))
                    entry_min, entry_max = self._normalize_zone(p1, p2)
                    confidence += 0.3
                else:
                    # Try @ prefix single
                    entry_match = self.re_entry_at_single.search(raw)
                    if entry_match:
                        entry_min = float(entry_match.group(1))
                        entry_max = entry_min
                        confidence += 0.3
                    else:
                        # Try Entry: prefix
                        entry_match = self.re_entry_keyword.search(raw)
                        if entry_match:
                            entry_min = float(entry_match.group(1))
                            if entry_match.group(2):
                                p2 = self._expand_abbreviated_price(
                                    entry_match.group(1), entry_match.group(2)
                                )
                                entry_max = p2
                                entry_min, entry_max = self._normalize_zone(entry_min, entry_max)
                            else:
                                entry_max = entry_min
                            confidence += 0.3
                        else:
                            # Try bare entry after side: "BUY 2350"
                            entry_match = self.re_entry_bare.search(raw)
                            if entry_match:
                                entry_min = float(entry_match.group(1))
                                if entry_match.group(2):
                                    p2 = self._expand_abbreviated_price(
                                        entry_match.group(1), entry_match.group(2)
                                    )
                                    entry_max = p2
                                    entry_min, entry_max = self._normalize_zone(entry_min, entry_max)
                                else:
                                    entry_max = entry_min
                                confidence += 0.2
                            else:
                                # Fallback: bare zone anywhere
                                zone_match = self.re_entry_zone_bare.search(raw)
                                if zone_match:
                                    p1 = float(zone_match.group(1))
                                    p2 = float(zone_match.group(2))
                                    entry_min, entry_max = self._normalize_zone(p1, p2)
                                    confidence += 0.1

        # If entry_type is still MARKET but we found entry prices and the signal says LIMIT
        if entry_min > 0 and entry_max > 0 and entry_type == "MARKET":
            # If there's a zone (min != max), it's likely a limit order
            if entry_min != entry_max:
                entry_type = "LIMIT"

        # Extract stop loss
        stop_loss = 0.0
        sl_type = "PRICE"

        # Check for pips-based SL first
        sl_pips_match = self.re_sl_pips.search(raw)
        if sl_pips_match:
            stop_loss = float(sl_pips_match.group(1))
            sl_type = "PIPS"
            confidence += 0.3
        else:
            # Try absolute price SL
            sl_match = self.re_sl_price.search(raw)
            if sl_match:
                stop_loss = float(sl_match.group(1))
                sl_type = "PRICE"
                confidence += 0.3

        # Extract take profits
        take_profits = []
        tp_type = "PRICE"

        # Check for pips-based numbered TPs first
        tp_pips_matches = self.re_tp_numbered_pips.findall(raw)
        if tp_pips_matches:
            tp_pips_matches.sort(key=lambda x: int(x[0]))
            take_profits = [float(m[1]) for m in tp_pips_matches]
            tp_type = "PIPS"
            confidence += 0.3

            # Check for OPEN TPs and add them as 0.0
            tp_open_matches = self.re_tp_numbered_open.findall(raw)
            for tp_num in tp_open_matches:
                # Find position to insert OPEN TP (by number)
                tp_n = int(tp_num)
                # Insert 0.0 at the right position (0.0 means OPEN/no TP)
                while len(take_profits) < tp_n:
                    take_profits.append(0.0)
                if len(take_profits) >= tp_n:
                    take_profits[tp_n - 1] = 0.0  # 0.0 = OPEN
        else:
            # Check for absolute price numbered TPs
            tp_price_matches = self.re_tp_numbered_price.findall(raw)
            if tp_price_matches:
                tp_price_matches.sort(key=lambda x: int(x[0]))
                take_profits = [float(m[1]) for m in tp_price_matches]
                tp_type = "PRICE"
                confidence += 0.3

                # Check for OPEN TPs
                tp_open_matches = self.re_tp_numbered_open.findall(raw)
                for tp_num in tp_open_matches:
                    tp_n = int(tp_num)
                    while len(take_profits) < tp_n:
                        take_profits.append(0.0)
                    if len(take_profits) >= tp_n:
                        take_profits[tp_n - 1] = 0.0
            else:
                # Try list pattern (slash/comma separated)
                tp_list_match = self.re_tp_list.search(raw)
                if tp_list_match:
                    tp_str = tp_list_match.group(1).strip()
                    tp_parts = re.split(r'[/,]', tp_str)
                    for p in tp_parts:
                        p = p.strip()
                        if not p:
                            continue
                        if p.upper() == "OPEN":
                            take_profits.append(0.0)  # 0 = OPEN
                        elif re.match(r'\d{3,5}(?:\.\d{1,5})?', p):
                            take_profits.append(float(p))
                    if take_profits:
                        confidence += 0.3

        # Check for break-even
        move_to_be = bool(
            self.re_move_to_be.search(raw) or
            self.re_move_to_be_alt.search(raw)
        )
        if move_to_be:
            confidence += 0.05

        # Must have at least side and either SL or TP to be valid
        if stop_loss == 0.0 and not take_profits:
            logger.debug(f"Rejected (no SL/TP): {raw[:80]}")
            return None

        # Generate deterministic signal ID from sender and raw text so repeated
        # parsing of the same message does not create duplicate signals.
        import hashlib
        msg_hash = hashlib.md5(f"{sender}:{raw}".encode("utf-8")).hexdigest()[:16]
        signal_id = msg_hash

        # Timestamp for the parsed signal (used in output and serialization)
        timestamp = datetime.now().strftime("%Y%m%d%H%M%S")

        signal = TradeSignal(
            signal_id=signal_id,
            timestamp=timestamp,
            symbol=symbol,
            side=side,
            entry_type=entry_type,
            entry_min=entry_min,
            entry_max=entry_max,
            stop_loss=stop_loss,
            sl_type=sl_type,
            take_profits=take_profits,
            tp_type=tp_type,
            move_to_be=move_to_be,
            confidence=confidence,
            source_sender=sender,
            timeframe=timeframe,
            raw_text=raw,
        )

        if confidence >= self.min_confidence:
            logger.info(f"Parsed signal: {signal.to_dict()}")
            return signal
        else:
            logger.debug(f"Rejected (low confidence {confidence:.2f}): {raw[:80]}")
            return None

    def parse_batch(self, messages: list) -> list:
        """Parse multiple messages, returning valid signals."""
        signals = []
        for msg in messages:
            if isinstance(msg, dict):
                text = msg.get("text", "")
                sender = msg.get("sender", "")
            else:
                text = str(msg)
                sender = ""
            signal = self.parse(text, sender)
            if signal:
                signals.append(signal)
        return signals
