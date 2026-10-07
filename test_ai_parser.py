"""
Standalone AI parser test script.

Usage:
  python test_ai_parser.py
  python test_ai_parser.py "BUY XAUUSD @ 2350 SL 2340 TP 2360"

This script loads `config.json` to read `ai_parser` settings and then uses
`ai_parser.AISignalParser` to parse a sample WhatsApp signal message.
"""

import json
import os
import sys

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))


def _deep_merge(base, override):
    result = dict(base or {})
    for key, value in (override or {}).items():
        if isinstance(value, dict) and isinstance(result.get(key), dict):
            result[key] = _deep_merge(result[key], value)
        else:
            result[key] = value
    return result


def resolve_ai_api_key(ai_config=None):
    ai_config = ai_config or {}
    configured = ai_config.get("api_key", "")
    if configured and configured not in ("", "YOUR_GROQ_API_KEY_HERE"):
        return configured

    for env_var in ("GROQ_API_KEY", "AI_API_KEY", "OPENAI_API_KEY"):
        env_value = os.getenv(env_var, "").strip()
        if env_value and env_value not in ("YOUR_GROQ_API_KEY_HERE", "YOUR_API_KEY_HERE"):
            return env_value

    return configured


def load_config(config_path=None, extra_config_paths=None):
    config_path = config_path or os.path.join(SCRIPT_DIR, "config.json")
    merged = {}
    for path in [config_path] + (extra_config_paths or []):
        if not path or not os.path.exists(path):
            continue
        with open(path, "r", encoding="utf-8") as f:
            merged = _deep_merge(merged, json.load(f))
    if not merged:
        raise FileNotFoundError(f"Config file not found: {config_path}")
    return merged


def main():
    config_path = os.path.join(SCRIPT_DIR, "config.json")
    if len(sys.argv) > 1 and os.path.isfile(sys.argv[1]):
        config_path = sys.argv[1]

    example_message = (
        sys.argv[1] if len(sys.argv) > 1 and not os.path.isfile(sys.argv[1]) else
        "H1 setup. GOLD BUY LIMIT:4328-4325.50 SL:40 pips TP.1 90 PIPS, TP.2 130 PIPS, TP.3 OPEN"
    )

    try:
        config = load_config(config_path)
    except Exception as exc:
        print(f"ERROR: Could not load config file: {exc}")
        sys.exit(1)

    ai_config = config.get("ai_parser", {})
    if not ai_config.get("enabled", False):
        print("ERROR: ai_parser.enabled is false in config.json. Enable AI parsing to run this test.")
        sys.exit(1)

    api_key = resolve_ai_api_key(ai_config)
    if not api_key or api_key == "YOUR_GROQ_API_KEY_HERE":
        print("ERROR: ai_parser.api_key is not configured. Set GROQ_API_KEY or add config.local.json.")
        sys.exit(1)

    try:
        from ai_parser import AISignalParser
    except Exception as exc:
        print("ERROR: Could not import AISignalParser from ai_parser module.")
        print("Install the required AI parser package or add ai_parser.py to the repository.")
        print(f"Import error: {exc}")
        sys.exit(1)

    fallback_parser = None
    try:
        from parser import SignalParser
        fallback_parser = SignalParser(
            symbol_aliases=config.get("parser", {}).get("symbol_aliases"),
            default_symbol=config.get("parser", {}).get("default_symbol", "XAUUSD"),
            min_confidence=config.get("parser", {}).get("min_confidence", 0.4),
            pip_value=config.get("parser", {}).get("pip_value", 1.0),
        )
    except Exception:
        fallback_parser = None

    kwargs = {
        "api_key": api_key,
        "model": ai_config.get("model", "llama-3.3-70b-versatile"),
        "base_url": ai_config.get("base_url", "https://api.groq.com/openai/v1"),
    }
    if fallback_parser is not None:
        kwargs["fallback_parser"] = fallback_parser

    try:
        parser = AISignalParser(**kwargs)
    except TypeError as exc:
        print("ERROR: AISignalParser initialization failed.")
        print(f"TypeError: {exc}")
        sys.exit(1)

    print("Testing AI parser with message:")
    print(example_message)
    print("---")

    try:
        signal = parser.parse(example_message, "unit-test")
    except Exception as exc:
        print(f"ERROR: AI parser raised an exception during parse: {exc}")
        sys.exit(1)

    if signal is None:
        print("AI parser returned no signal.")
        sys.exit(1)

    try:
        result = signal.to_dict()
    except Exception:
        result = {"signal": str(signal)}

    print("AI parser returned a signal:")
    for key, value in result.items():
        print(f"{key}: {value}")

    print("PASS: AI parser test completed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
