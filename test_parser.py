"""
Tests for the signal parser using real WhatsApp group signal formats.
Run: python test_parser.py
"""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from parser import SignalParser, TradeSignal


def test_real_sample_1():
    """Test real signal sample 1: BUY LIMIT with pips TP/SL."""
    parser = SignalParser(min_confidence=0.3)
    msg = """H1 setup.
GOLD
BUY LIMIT:4328-4325.50
SL:40 pips out from end of zone
TP.1 90 PIPS, TP.2 130 PIPS, TP.3 OPEN
AFTER TP.1 SL MOVE TO BE."""
    sig = parser.parse(msg)
    assert sig is not None, "Should parse real sample 1"
    assert sig.side == "BUY", f"Expected BUY, got {sig.side}"
    assert sig.entry_type == "LIMIT", f"Expected LIMIT, got {sig.entry_type}"
    assert sig.entry_min == 4325.50, f"Expected entry_min 4325.50, got {sig.entry_min}"
    assert sig.entry_max == 4328.0, f"Expected entry_max 4328.0, got {sig.entry_max}"
    assert sig.stop_loss == 40.0, f"Expected SL 40, got {sig.stop_loss}"
    assert sig.sl_type == "PIPS", f"Expected SL type PIPS, got {sig.sl_type}"
    assert sig.tp_type == "PIPS", f"Expected TP type PIPS, got {sig.tp_type}"
    assert len(sig.take_profits) == 3, f"Expected 3 TPs, got {len(sig.take_profits)}"
    assert sig.take_profits[0] == 90.0, f"Expected TP1 90, got {sig.take_profits[0]}"
    assert sig.take_profits[1] == 130.0, f"Expected TP2 130, got {sig.take_profits[1]}"
    assert sig.take_profits[2] == 0.0, f"Expected TP3 OPEN (0), got {sig.take_profits[2]}"
    assert sig.move_to_be == True, f"Expected move_to_be True, got {sig.move_to_be}"
    assert sig.timeframe == "H1", f"Expected H1, got {sig.timeframe}"
    print("PASS: test_real_sample_1")


def test_real_sample_2():
    """Test real signal sample 2: SELL with absolute price TP/SL."""
    parser = SignalParser(min_confidence=0.3)
    msg = """M30 setup.
Sell Gold 4384-88
SL 4392
TP1 4354
TP2 4318
TP3 4299
TP4 4251"""
    sig = parser.parse(msg)
    assert sig is not None, "Should parse real sample 2"
    assert sig.side == "SELL", f"Expected SELL, got {sig.side}"
    assert sig.entry_min == 4384.0, f"Expected entry_min 4384, got {sig.entry_min}"
    assert sig.entry_max == 4388.0, f"Expected entry_max 4388, got {sig.entry_max}"
    assert sig.stop_loss == 4392.0, f"Expected SL 4392, got {sig.stop_loss}"
    assert sig.sl_type == "PRICE", f"Expected SL type PRICE, got {sig.sl_type}"
    assert sig.tp_type == "PRICE", f"Expected TP type PRICE, got {sig.tp_type}"
    assert len(sig.take_profits) == 4, f"Expected 4 TPs, got {len(sig.take_profits)}"
    assert sig.take_profits[0] == 4354.0, f"Expected TP1 4354, got {sig.take_profits[0]}"
    assert sig.take_profits[1] == 4318.0, f"Expected TP2 4318, got {sig.take_profits[1]}"
    assert sig.take_profits[2] == 4299.0, f"Expected TP3 4299, got {sig.take_profits[2]}"
    assert sig.take_profits[3] == 4251.0, f"Expected TP4 4251, got {sig.take_profits[3]}"
    assert sig.timeframe == "M30", f"Expected M30, got {sig.timeframe}"
    print("PASS: test_real_sample_2")


def test_basic_buy():
    """Test basic BUY signal."""
    parser = SignalParser(min_confidence=0.3)
    msg = "BUY XAUUSD @ 2350 SL 2345 TP 2360"
    sig = parser.parse(msg)
    assert sig is not None
    assert sig.side == "BUY"
    assert sig.entry_min == 2350.0
    assert sig.stop_loss == 2345.0
    assert sig.sl_type == "PRICE"
    assert 2360.0 in sig.take_profits
    print("PASS: test_basic_buy")


def test_basic_sell():
    """Test basic SELL signal."""
    parser = SignalParser(min_confidence=0.3)
    msg = "SELL XAUUSD @ 2400 SL 2410 TP 2390"
    sig = parser.parse(msg)
    assert sig is not None
    assert sig.side == "SELL"
    assert sig.entry_min == 2400.0
    assert sig.stop_loss == 2410.0
    assert 2390.0 in sig.take_profits
    print("PASS: test_basic_sell")


def test_entry_zone():
    """Test entry zone with @ prefix."""
    parser = SignalParser(min_confidence=0.3)
    msg = "GOLD SELL @ 2348-2350 SL 2355 TP1 2342 TP2 2335"
    sig = parser.parse(msg)
    assert sig is not None
    assert sig.side == "SELL"
    assert sig.entry_min == 2348.0
    assert sig.entry_max == 2350.0
    assert sig.stop_loss == 2355.0
    assert 2342.0 in sig.take_profits
    assert 2335.0 in sig.take_profits
    print("PASS: test_entry_zone")


def test_slash_tps():
    """Test slash-separated TPs."""
    parser = SignalParser(min_confidence=0.3)
    msg = "XAUUSD BUY NOW SL: 2330 TP: 2345/2355/2365"
    sig = parser.parse(msg)
    assert sig is not None
    assert sig.side == "BUY"
    assert sig.stop_loss == 2330.0
    assert len(sig.take_profits) == 3
    assert 2345.0 in sig.take_profits
    assert 2355.0 in sig.take_profits
    assert 2365.0 in sig.take_profits
    print("PASS: test_slash_tps")


def test_comma_tps():
    """Test comma-separated TPs."""
    parser = SignalParser(min_confidence=0.3)
    msg = "BUY GOLD @ 2350 SL: 2345 TP: 2360, 2370, 2380"
    sig = parser.parse(msg)
    assert sig is not None
    assert sig.side == "BUY"
    assert sig.entry_min == 2350.0
    assert sig.stop_loss == 2345.0
    assert len(sig.take_profits) == 3
    assert 2360.0 in sig.take_profits
    assert 2370.0 in sig.take_profits
    assert 2380.0 in sig.take_profits
    print("PASS: test_comma_tps")


def test_emoji_signal():
    """Test signal with emojis."""
    parser = SignalParser(min_confidence=0.3)
    msg = "\U0001f7e2 BUY GOLD Entry: 2350-2352 SL: 2345 TP: 2360, 2370, 2380"
    sig = parser.parse(msg)
    assert sig is not None
    assert sig.side == "BUY"
    assert sig.entry_min == 2350.0
    assert sig.entry_max == 2352.0
    assert sig.stop_loss == 2345.0
    assert len(sig.take_profits) == 3
    print("PASS: test_emoji_signal")


def test_decimal_prices():
    """Test decimal price parsing."""
    parser = SignalParser(min_confidence=0.3)
    msg = "Gold Buy @ 2350.50, SL: 2345.00, TP: 2360.00"
    sig = parser.parse(msg)
    assert sig is not None
    assert sig.side == "BUY"
    assert sig.entry_min == 2350.50
    assert sig.stop_loss == 2345.00
    assert 2360.00 in sig.take_profits
    print("PASS: test_decimal_prices")


def test_no_signal():
    """Test that non-signal messages are rejected."""
    parser = SignalParser(min_confidence=0.3)
    msg = "Good morning everyone, have a great trading day!"
    sig = parser.parse(msg)
    assert sig is None, "Should reject non-signal message"
    print("PASS: test_no_signal")


def test_no_side_rejected():
    """Test that messages without buy/sell are rejected."""
    parser = SignalParser(min_confidence=0.3)
    msg = "XAUUSD @ 2350 SL 2345 TP 2360"
    sig = parser.parse(msg)
    assert sig is None, "Should reject message without side"
    print("PASS: test_no_side_rejected")


def test_pips_are_converted_to_prices_in_pipe_output():
    """Pip values should be converted to absolute prices before MT5 file output."""
    sig = TradeSignal(
        signal_id="abc123",
        timestamp="20240101120000",
        symbol="XAUUSD",
        side="BUY",
        entry_type="LIMIT",
        entry_min=4168.0,
        entry_max=4172.0,
        stop_loss=40.0,
        sl_type="PIPS",
        take_profits=[90.0, 130.0, 0.0],
        tp_type="PIPS",
        move_to_be=True,
        confidence=0.95,
        raw_text="BUY LIMIT:4168-4172 SL:40 pips TP1 90 PIPS TP2 130 PIPS TP3 OPEN",
    )
    pipe = sig.to_pipe_string()
    assert "|" in pipe
    assert "4167.60000" in pipe
    assert "4168.90000" in pipe
    assert "4169.30000" in pipe
    assert "PRICE" in pipe
    print("PASS: test_pips_are_converted_to_prices_in_pipe_output")


def test_pipe_serialization():
    """Test pipe serialization/deserialization."""
    sig = TradeSignal(
        signal_id="20240101120000_abc12345",
        timestamp="20240101120000",
        symbol="XAUUSD",
        side="BUY",
        entry_type="LIMIT",
        entry_min=4325.50,
        entry_max=4328.0,
        stop_loss=40.0,
        sl_type="PIPS",
        take_profits=[90.0, 130.0, 0.0],
        tp_type="PIPS",
        move_to_be=True,
        confidence=0.95,
        raw_text="BUY LIMIT:4328-4325.50 SL:40 pips TP.1 90 PIPS TP.2 130 PIPS TP.3 OPEN",
    )
    pipe = sig.to_pipe_string()
    assert "|" in pipe

    restored = TradeSignal.from_pipe_string(pipe)
    assert restored is not None
    assert restored.side == "BUY"
    assert restored.entry_type == "LIMIT"
    assert restored.entry_min == 4325.50
    assert restored.entry_max == 4328.0
    assert restored.stop_loss == 4285.50
    assert restored.sl_type == "PRICE"
    assert restored.tp_type == "PRICE"
    assert len(restored.take_profits) == 3
    assert restored.take_profits[0] == 4415.50
    assert restored.take_profits[1] == 4455.50
    assert restored.take_profits[2] == 0.0  # OPEN
    assert restored.move_to_be == True
    print("PASS: test_pipe_serialization")


def test_long_short_synonyms():
    """Test LONG/SHORT as synonyms for BUY/SELL."""
    parser = SignalParser(min_confidence=0.3)
    sig1 = parser.parse("LONG XAUUSD @ 2350 SL 2345 TP 2360")
    assert sig1 is not None and sig1.side == "BUY"

    sig2 = parser.parse("SHORT XAUUSD @ 2350 SL 2355 TP 2340")
    assert sig2 is not None and sig2.side == "SELL"
    print("PASS: test_long_short_synonyms")


def test_market_order_no_entry():
    """Test signal with no explicit entry price (market order)."""
    parser = SignalParser(min_confidence=0.3)
    msg = "BUY NOW XAUUSD SL: 2330 TP: 2350"
    sig = parser.parse(msg)
    assert sig is not None
    assert sig.side == "BUY"
    assert sig.stop_loss == 2330.0
    assert 2350.0 in sig.take_profits
    assert sig.entry_min == 0.0
    print("PASS: test_market_order_no_entry")


def test_buy_limit_format():
    """Test BUY LIMIT order format."""
    parser = SignalParser(min_confidence=0.3)
    msg = "BUY LIMIT XAUUSD @ 2350 SL 2345 TP 2360"
    sig = parser.parse(msg)
    assert sig is not None
    assert sig.side == "BUY"
    assert sig.entry_type == "LIMIT"
    assert sig.entry_min == 2350.0
    print("PASS: test_buy_limit_format")


def test_sell_limit_format():
    """Test SELL LIMIT order format."""
    parser = SignalParser(min_confidence=0.3)
    msg = "SELL LIMIT GOLD @ 2400 SL 2410 TP 2390"
    sig = parser.parse(msg)
    assert sig is not None
    assert sig.side == "SELL"
    assert sig.entry_type == "LIMIT"
    assert sig.entry_min == 2400.0
    print("PASS: test_sell_limit_format")


def test_pips_sl():
    """Test pips-based stop loss."""
    parser = SignalParser(min_confidence=0.3)
    msg = "BUY XAUUSD @ 2350 SL: 50 pips TP 2360"
    sig = parser.parse(msg)
    assert sig is not None
    assert sig.stop_loss == 50.0
    assert sig.sl_type == "PIPS"
    print("PASS: test_pips_sl")


def test_tp_dot_notation():
    """Test TP with dot notation: TP.1, TP.2."""
    parser = SignalParser(min_confidence=0.3)
    msg = "BUY GOLD @ 2350 SL 2345 TP.1 2360 TP.2 2370 TP.3 2380"
    sig = parser.parse(msg)
    assert sig is not None
    assert len(sig.take_profits) == 3
    assert sig.take_profits[0] == 2360.0
    assert sig.take_profits[1] == 2370.0
    assert sig.take_profits[2] == 2380.0
    print("PASS: test_tp_dot_notation")


def test_tp_open():
    """Test OPEN TP (no fixed target)."""
    parser = SignalParser(min_confidence=0.3)
    msg = "BUY GOLD @ 2350 SL 2345 TP.1 2360 TP.2 OPEN"
    sig = parser.parse(msg)
    assert sig is not None
    assert len(sig.take_profits) == 2
    assert sig.take_profits[0] == 2360.0
    assert sig.take_profits[1] == 0.0  # OPEN
    print("PASS: test_tp_open")


def test_move_to_be():
    """Test break-even detection."""
    parser = SignalParser(min_confidence=0.3)
    msg = "BUY GOLD @ 2350 SL 2345 TP 2360 AFTER TP.1 SL MOVE TO BE"
    sig = parser.parse(msg)
    assert sig is not None
    assert sig.move_to_be == True
    print("PASS: test_move_to_be")


def test_abbreviated_zone():
    """Test abbreviated zone: 4384-88 → 4384-4388."""
    parser = SignalParser(min_confidence=0.3)
    msg = "Sell Gold 4384-88 SL 4392 TP 4354"
    sig = parser.parse(msg)
    assert sig is not None
    assert sig.side == "SELL"
    assert sig.entry_min == 4384.0
    assert sig.entry_max == 4388.0
    print("PASS: test_abbreviated_zone")


def test_reversed_zone():
    """Test reversed zone: 4328-4325.50 → 4325.50-4328."""
    parser = SignalParser(min_confidence=0.3)
    msg = "BUY LIMIT:4328-4325.50 SL 4300 TP 4400"
    sig = parser.parse(msg)
    assert sig is not None
    assert sig.entry_min == 4325.50
    assert sig.entry_max == 4328.0
    print("PASS: test_reversed_zone")


def test_multi_line_signal():
    """Test multi-line signal with extra text."""
    parser = SignalParser(min_confidence=0.3)
    msg = """
    H4 setup.

    GOLD SIGNAL

    BUY LIMIT:4328-4325.50

    SL:40 pips out from end of zone

    TP.1 90 PIPS, TP.2 130 PIPS, TP.3 OPEN

    AFTER TP.1 SL MOVE TO BE.

    Risk: 1%
    """
    sig = parser.parse(msg)
    assert sig is not None
    assert sig.side == "BUY"
    assert sig.entry_type == "LIMIT"
    assert sig.entry_min == 4325.50
    assert sig.entry_max == 4328.0
    assert sig.sl_type == "PIPS"
    assert sig.stop_loss == 40.0
    assert sig.tp_type == "PIPS"
    assert len(sig.take_profits) == 3
    assert sig.take_profits[2] == 0.0
    assert sig.move_to_be == True
    assert sig.timeframe == "H4"
    print("PASS: test_multi_line_signal")


def test_bare_entry_after_side():
    """Test bare entry: BUY 2350 SL 2345 TP 2360."""
    parser = SignalParser(min_confidence=0.3)
    msg = "BUY 2350 SL 2345 TP 2360"
    sig = parser.parse(msg)
    assert sig is not None
    assert sig.side == "BUY"
    assert sig.entry_min == 2350.0
    assert sig.entry_max == 2350.0
    assert sig.stop_loss == 2345.0
    assert 2360.0 in sig.take_profits
    print("PASS: test_bare_entry_after_side")


def test_signal_id_unique():
    """Test that signal IDs include message hash for uniqueness."""
    parser = SignalParser(min_confidence=0.3)
    msg1 = "BUY XAUUSD @ 2350 SL 2345 TP 2360"
    msg2 = "BUY XAUUSD @ 2360 SL 2350 TP 2370"
    sig1 = parser.parse(msg1)
    sig2 = parser.parse(msg2)
    # Different messages → different hash in ID
    assert sig1.signal_id[-8:] != sig2.signal_id[-8:]
    assert len(sig1.signal_id) > 15  # Has timestamp + hash
    print("PASS: test_signal_id_unique")


if __name__ == "__main__":
    print("Running parser tests...\n")

    # Real samples (most important)
    test_real_sample_1()
    test_real_sample_2()

    # Core format tests
    test_basic_buy()
    test_basic_sell()
    test_entry_zone()
    test_slash_tps()
    test_comma_tps()
    test_emoji_signal()
    test_decimal_prices()
    test_no_signal()
    test_no_side_rejected()
    test_pips_are_converted_to_prices_in_pipe_output()
    test_pipe_serialization()
    test_long_short_synonyms()
    test_market_order_no_entry()

    # New format tests
    test_buy_limit_format()
    test_sell_limit_format()
    test_pips_sl()
    test_tp_dot_notation()
    test_tp_open()
    test_move_to_be()
    test_abbreviated_zone()
    test_reversed_zone()
    test_multi_line_signal()
    test_bare_entry_after_side()
    test_signal_id_unique()

    print(f"\n{'='*50}")
    print("All tests passed!")
    print(f"{'='*50}")
