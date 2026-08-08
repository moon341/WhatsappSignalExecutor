# WhatsApp to MT5 Signal Bridge for XAUUSD (Gold)

Automatically reads trade signals from a WhatsApp group, parses them, and executes trades in MetaTrader 5.

## How It Works

```
WhatsApp Group → Python Monitor (WhatsApp Web) → Signal Parser → Signal File → MT5 Expert Advisor → Trade Execution
```

1. **Python Monitor** (`monitor.py`) opens WhatsApp Web in Chrome, monitors your gold signals group for new messages
2. **Signal Parser** (`parser.py`) extracts buy/sell direction, entry zone, stop loss, and take profit levels — handling both absolute prices and pips-based values
3. **Signal Writer** (`signal_writer.py`) writes parsed signals to a file in the MT5 `MQL5/Files` folder with atomic writes and rollback safety
4. **MT5 Expert Advisor** (`XAUUSD_SignalTrader.mq5`) reads the file and automatically executes trades with safety guardrails

---

## Prerequisites

- **Windows 10 or 11**
- **Python 3.9+** — [Download from python.org](https://www.python.org/downloads/) (check "Add Python to PATH" during install)
- **Google Chrome** — [Download](https://www.google.com/chrome/)
- **MetaTrader 5** — installed and running
- **WhatsApp account** — with access to the signals group on your phone

---

## Quick Setup

### Step 1: Install

Extract the zip to `C:\WhatsAppSignalBot`, then run:

```cmd
cd C:\WhatsAppSignalBot
setup_windows.bat
```

This creates the directory structure, installs Python dependencies, creates the Chrome profile folder, and runs parser tests.

### Step 2: Configure

Open `config.json` in Notepad and edit:

1. **`group_name`** — Set to your WhatsApp group name (case-insensitive)
2. **`signal_file.output_path`** — Set to your MT5 Files folder path

To find your MT5 Files folder:
- Open MT5 → **File → Open Data Folder** → navigate to `MQL5\Files`
- Copy the full path from the address bar

### Step 3: Install the EA

1. In MT5: **File → Open Data Folder** → `MQL5\Experts`
2. Copy `XAUUSD_SignalTrader.mq5` there
3. Open MetaEditor (F4), open the file, press **F7** to compile
4. Verify: "0 errors, 0 warnings"

### Step 4: Attach EA to Chart

1. Open a XAUUSD chart in MT5
2. Drag `XAUUSD_SignalTrader` from Navigator → Expert Advisors onto the chart
3. Check "Allow Algorithmic Trading" in the Common tab
4. Review inputs in the Inputs tab
5. Click OK
6. Enable the **AutoTrading** button (green) in the toolbar

### Step 5: Start Monitoring

```cmd
cd C:\WhatsAppSignalBot
start_monitor.bat
```

**First run:** Chrome opens WhatsApp Web. Scan the QR code (WhatsApp → Settings → Linked Devices → Link a Device). The session persists for future runs.

---

## Supported Signal Formats

The parser handles your real group signal formats:

### Format 1: Pips-based (BUY LIMIT)
```
H1 setup.
GOLD
BUY LIMIT:4328-4325.50
SL:40 pips out from end of zone
TP.1 90 PIPS, TP.2 130 PIPS, TP.3 OPEN
AFTER TP.1 SL MOVE TO BE.
```
- Entry zone: 4325.50 - 4328 (normalized from reversed input)
- SL: 40 pips below the entry zone (calculated by EA)
- TP1: 90 pips, TP2: 130 pips, TP3: OPEN (no fixed target)
- Move SL to break-even after TP1

### Format 2: Absolute prices (SELL)
```
M30 setup.
Sell Gold 4384-88
SL 4392
TP1 4354
TP2 4318
TP3 4299
TP4 4251
```
- Entry zone: 4384 - 4388 (expanded from "4384-88")
- SL: 4392 (absolute price)
- TPs: 4 absolute price levels

### Other supported formats:
```
BUY XAUUSD @ 2350 SL 2345 TP 2360
SELL XAUUSD @ 2400 SL 2410 TP 2390
XAUUSD BUY NOW SL: 2330 TP: 2345/2355/2365
BUY GOLD @ 2350 SL: 2345 TP: 2360, 2370, 2380
Gold Buy @ 2350.50, SL: 2345.00, TP: 2360.00
LONG XAUUSD @ 2350 SL 2345 TP 2360
```

### Adding Custom Formats

Edit `parser.py` — add regex patterns in `_compile_patterns()`. Run `python test_parser.py` to verify.

---

## MT5 Expert Advisor Settings

| Parameter | Default | Description |
|-----------|---------|-------------|
| `EnableTrading` | `false` | **Set to `true` for live trading.** Default is log-only. |
| `LotSize` | `0.01` | Fixed lot size per trade |
| `UseRiskPercent` | `false` | Use risk-based lot sizing |
| `RiskPercent` | `1.0` | Risk % of balance per trade |
| `MagicNumber` | `77001` | Magic number for EA trades |
| `MaxSpreadPoints` | `50` | Max allowed spread |
| `MaxOpenPositions` | `3` | Max simultaneous positions |
| `CloseOnOppositeSignal` | `true` | Close on opposite signal |
| `PipValue` | `1.0` | 1 pip = 1.0 price units (XAUUSD) |
| `EnableBreakEven` | `true` | Move SL to BE after TP1 |
| `BreakEvenBufferPips` | `2` | BE buffer above entry |
| `SkipIfOutsideZone` | `true` | Skip market orders outside entry zone |
| `RequireSL` | `true` | Require stop loss |
| `MinSLDistance` | `50` | Min SL distance in points |
| `DisableOnDrawdown` | `false` | Disable on drawdown |
| `MaxDrawdownPercent` | `20.0` | Max drawdown % |
| `AllowTradingHours` | `false` | Restrict to trading hours |
| `TradingStartHour` | `0` | Start hour (server time) |
| `TradingEndHour` | `23` | End hour (server time) |

---

## Key Features

### Pips-based SL/TP
When signals use pips ("TP.1 90 PIPS"), the EA calculates absolute prices from the entry zone. For BUY: SL = entry_min - pips, TP = entry_min + pips. For SELL: SL = entry_max + pips, TP = entry_max - pips.

### OPEN Take Profits
"TP.3 OPEN" means no fixed target — the trade runs until the SL is hit or the position is manually closed.

### Break-Even Management
When "AFTER TP.1 SL MOVE TO BE" is detected, the EA automatically moves the stop loss to break-even (entry + small buffer) after price moves 50% toward TP1.

### LIMIT Orders
"BUY LIMIT" signals create pending limit orders at the entry zone price, not market orders.

### Entry Zone Protection
When `SkipIfOutsideZone=true`, market orders are skipped if the current price is outside the signal's entry zone.

### Atomic File Writes
Signal files are written to a temp file first, then atomically renamed. The EA never reads a partially written file. If the write fails (e.g., MT5 is reading), it retries automatically.

---

## Testing

### Test the Parser
```cmd
cd C:\WhatsAppSignalBot
python test_parser.py
```
25 tests covering real signal formats and edge cases.

### Test on Demo Account
1. Open a demo account in MT5
2. Attach the EA with `EnableTrading=false` (log-only)
3. Start the monitor and watch the MT5 Experts/Journal tab
4. Verify signals are parsed correctly
5. Set `EnableTrading=true` on demo
6. Monitor for several days before going live

---

## File Structure

```
WhatsAppSignalBot/
├── monitor.py                  ← WhatsApp Web monitor (main script)
├── parser.py                   ← Signal parser
├── signal_writer.py            ← Atomic signal file writer
├── test_parser.py              ← 25 parser tests
├── config.example.json         ← Example configuration
├── config.json                 ← Your configuration
├── requirements.txt            ← Python dependencies
├── XAUUSD_SignalTrader.mq5     ← MT5 Expert Advisor
├── setup_windows.bat           ← Windows setup script
├── start_monitor.bat           ← Monitor launcher
└── README.md                   ← This file
```

---

## Troubleshooting

### WhatsApp Web doesn't load
- Ensure Chrome is installed and updated
- Delete the profile: `rmdir /s /q C:\WhatsAppSignalBot\chrome-profile`
- Run again and re-scan QR code

### Group not found
- Verify `group_name` in config.json matches exactly
- Make sure the group appears in your recent chats

### Signals not detected
- Run `python test_parser.py` to verify parser
- Check log: `C:\WhatsAppSignalBot\signal_bridge.log`
- If your format differs, add a test case and adjust parser patterns

### EA not reading signals
- Verify `output_path` in config.json points to MT5's `MQL5\Files` folder
- Check MT5 Journal tab for errors
- Ensure EA is on a XAUUSD chart with "Allow Algorithmic Trading" checked
- AutoTrading button must be green

### Limit order not placed
- Check if current price is on the correct side of the entry zone
- BUY LIMIT requires price above the zone; SELL LIMIT requires price below
- Check spread and max positions limits

---

## Important Warnings

1. **TEST ON DEMO FIRST.** Never enable live trading without thorough testing.
2. **Auto-trading is risky.** WhatsApp signals are not financial advice. You can lose money.
3. **WhatsApp Web may change.** DOM selectors can break when WhatsApp updates their web interface.
4. **Keep Chrome open.** The monitor needs Chrome to stay open and connected.
5. **Monitor your trades.** Check the EA regularly.
6. **Use proper risk management.** Start with 0.01 lots and low risk percentage.
7. **The EA must be compiled in MetaEditor on your machine.** Python tests pass, but MQL5 compilation and demo testing are your responsibility.
