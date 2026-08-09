//+------------------------------------------------------------------+
//|                                          XAUUSD_SignalTrader.mq5 |
//|                                  WhatsApp Signal Bridge for MT5   |
//|                                                                  |
//|  Reads trade signals from a file written by the Python monitor.  |
//|  Handles both absolute price and pips-based SL/TP.               |
//|  Supports LIMIT orders, break-even management, and OPEN TPs.     |
//|                                                                  |
//|  SAFETY: Test on a DEMO account first!                           |
//|          Default EnableTrading = false (log-only mode).          |
//+------------------------------------------------------------------+
#property copyright   "WhatsApp Signal Bridge"
#property version     "2.00"
#property description "Reads WhatsApp trade signals from file and executes them."
#property description "Supports pips-based SL/TP, LIMIT orders, break-even."
#property description "TEST ON DEMO FIRST. Set EnableTrading=true to trade."

#include <Trade\Trade.mqh>
#include <Trade\PositionInfo.mqh>
#include <Trade\SymbolInfo.mqh>

//--- Input parameters
input group "=== Trading Control ==="
input bool     EnableTrading      = false;    // Enable live trading (false = log only)
input double   LotSize            = 0.01;     // Fixed lot size
input bool     UseRiskPercent     = false;    // Use risk-based lot sizing
input double   RiskPercent        = 1.0;      // Risk % of balance per trade (if UseRiskPercent=true)
input int      MagicNumber        = 77001;    // Magic number for signal trades
input int      MaxSpreadPoints    = 50;      // Max allowed spread (in points)
input int      MaxOpenPositions   = 3;       // Max simultaneous positions from signals
input bool     CloseOnOppositeSignal = true;  // Close positions on opposite signal

input group "=== Signal File ==="
input string   SignalFileName    = "C:\Users\noman\OneDrive\Desktop\testbot\signals.txt"; // Signal file name (in MQL5/Files/)
input int      PollIntervalMs     = 1000;     // How often to check for new signals (ms)

input group "=== Take Profit Settings ==="
input bool     UseMultipleTPs     = true;     // Split lots across multiple TPs
input double   PipValue           = 1.0;     // 1 pip = this many price units (XAUUSD: 1.0 = $1 per pip)

input group "=== Break-Even Settings ==="
input bool     EnableBreakEven    = true;     // Move SL to break-even after TP1 is hit
input int      BreakEvenBufferPips = 2;        // Buffer above entry for BE (in pips)

input group "=== Safety Filters ==="
input bool     AllowTradingHours  = false;    // Restrict trading to certain hours
input int      TradingStartHour   = 0;        // Trading start hour (server time)
input int      TradingEndHour     = 23;       // Trading end hour (server time)
input int      Slippage           = 10;       // Max slippage in points
input bool     RequireSL          = true;     // Require stop loss on every trade
input double   MinSLDistance      = 50.0;     // Minimum SL distance in points
input bool     DisableOnDrawdown  = false;    // Disable trading if drawdown exceeds threshold
input double   MaxDrawdownPercent = 20.0;     // Max drawdown % before disabling
input bool     SkipIfOutsideZone  = true;     // Skip market orders if price is outside entry zone

input group "=== Symbol ==="
input string   TradingSymbol      = "XAUUSD"; // Trading symbol (gold)

//--- Global variables
CTrade         trade;
CPositionInfo  posInfo;
CSymbolInfo    symInfo;

string         g_lastProcessedID = "";
datetime       g_lastCheckTime   = 0;
int            g_totalTrades     = 0;
string         g_activeSymbol    = "";

//+------------------------------------------------------------------+
//| Expert initialization                                            |
//+------------------------------------------------------------------+
int OnInit()
{
    Print("ENTER: OnInit() - initializing expert");
    trade.SetExpertMagicNumber(MagicNumber);
    trade.SetDeviationInPoints(Slippage);

    // Determine active symbol (don't modify the input `TradingSymbol` constant)
    g_activeSymbol = TradingSymbol;
    // If the configured symbol is not known, try the current chart symbol
    if(!symInfo.Name(g_activeSymbol))
    {
        Print("ERROR: Configured symbol '", g_activeSymbol, "' not found in Market Watch.");
        string chartSym = Symbol();
        Print("Attempting to use current chart symbol: ", chartSym);
        if(symInfo.Name(chartSym))
        {
            g_activeSymbol = chartSym;
            Print("Using chart symbol: ", g_activeSymbol);
        }
        else
        {
            Print("ERROR: Neither configured symbol nor chart symbol are available. Add symbol to Market Watch or set the `TradingSymbol` input to your broker's symbol name.");
            return INIT_FAILED;
        }
    }

    // Ensure trade filling mode matches the active symbol
    if(!trade.SetTypeFillingBySymbol(g_activeSymbol))
        Print("WARNING: Could not set filling mode for symbol ", g_activeSymbol, ". Using default.");

    // Initialization diagnostics
    Print("INIT DIAGNOSTICS:");
    Print("  Configured TradingSymbol: ", TradingSymbol);
    Print("  Resolved Active Symbol: ", g_activeSymbol);
    Print("  SignalFileName: ", SignalFileName);
    bool fileExists = FileIsExist(SignalFileName);
    Print("  Signal file exists (FileIsExist): ", fileExists);
    if(fileExists)
    {
        int fh = FileOpen(SignalFileName, FILE_READ | FILE_TXT | FILE_ANSI);
        if(fh == INVALID_HANDLE)
            Print("  Signal file cannot be opened. GetLastError(): ", GetLastError());
        else
        {
            Print("  Signal file opened successfully.");
            FileClose(fh);
        }
    }
    Print("  Account balance: ", AccountInfoDouble(ACCOUNT_BALANCE), "  Equity: ", AccountInfoDouble(ACCOUNT_EQUITY));
    Print("  Server time (TimeCurrent): ", TimeCurrent());
    // Visible notifications for quick debugging
    Alert("XAUUSD_SignalTrader: INIT completed. Active symbol= " , g_activeSymbol);
    Comment("XAUUSD_SignalTrader active: " + g_activeSymbol + " - see Experts tab for details.");

    Print("========================================");
    Print("XAUUSD Signal Trader v2.00");
    Print("  Symbol:         ", g_activeSymbol);
    Print("  Signal File:    ", SignalFileName);
    Print("  EnableTrading:  ", EnableTrading);
    Print("  LotSize:        ", LotSize);
    Print("  PipValue:       ", PipValue);
    Print("  MagicNumber:    ", MagicNumber);
    Print("  MaxSpread:      ", MaxSpreadPoints, " points");
    Print("  MaxPositions:   ", MaxOpenPositions);
    Print("  BreakEven:      ", EnableBreakEven);
    Print("  SkipOutsideZone: ", SkipIfOutsideZone);
    Print("========================================");

    if(!EnableTrading)
        Print("WARNING: Trading is DISABLED (log-only mode). Set EnableTrading=true to trade.");

    // Read existing signals to set last processed ID (skip already processed)
    g_lastProcessedID = ReadLastSignalID();

    return INIT_SUCCEEDED;
}

//+------------------------------------------------------------------+
//| Expert deinitialization                                          |
//+------------------------------------------------------------------+
void OnDeinit(const int reason)
{
    Print("ENTER: OnDeinit() - reason=", reason);
    Print("Signal Trader stopped. Total trades executed: ", g_totalTrades);
}

//+------------------------------------------------------------------+
//| Expert tick function                                            |
//+------------------------------------------------------------------+
void OnTick()
{
    Print("ENTER: OnTick() - checking for signals. lastProcessedID=", g_lastProcessedID);
    datetime now = TimeCurrent();
    if(now - g_lastCheckTime < PollIntervalMs / 1000)
        return;
    g_lastCheckTime = now;

    if(!symInfo.RefreshRates())
        return;

    // Check drawdown safety
    if(DisableOnDrawdown && IsMaxDrawdownExceeded())
    {
        static datetime lastDDWarning = 0;
        if(now - lastDDWarning > 300)
        {
            Print("WARNING: Max drawdown exceeded. Trading disabled.");
            lastDDWarning = now;
        }
        return;
    }

    // Check trading hours
    if(AllowTradingHours && !IsWithinTradingHours())
        return;

    // Manage break-even for existing positions
    if(EnableBreakEven)
        ManageBreakEven();

    // Read signal file
    string signals[];
    int count = ReadSignalFile(signals);
    Print("ReadSignalFile returned count=", count);
    if(count == 0)
        return;

    // Process new signals
    bool foundNew = false;
    for(int i = 0; i < count; i++)
    {
        string line = signals[i];
        if(StringLen(line) < 5)
            continue;

        string parts[];
        int numParts = StringSplit(line, '|', parts);
        if(numParts < 13)
            continue;

        string signalID = parts[0];
        if(signalID == g_lastProcessedID)
        {
            foundNew = true;
            continue;
        }

        if(foundNew || g_lastProcessedID == "")
        {
            if(g_lastProcessedID == "" && !foundNew)
            {
                // First run - mark last signal as processed without trading
                g_lastProcessedID = parts[0];
                continue;
            }
            ProcessSignal(parts, numParts);
            g_lastProcessedID = signalID;
        }
    }

    // If we didn't find last processed ID, process new ones
    if(!foundNew && g_lastProcessedID != "" && count > 0)
    {
        for(int i = 0; i < count; i++)
        {
            string parts[];
            int numParts = StringSplit(signals[i], '|', parts);
            if(numParts < 13)
                continue;
            ProcessSignal(parts, numParts);
            g_lastProcessedID = parts[0];
        }
    }
    else if(count > 0 && g_lastProcessedID == "")
    {
        string parts[];
        StringSplit(signals[count-1], '|', parts);
        if(ArraySize(parts) >= 13)
            g_lastProcessedID = parts[0];
        Print("Initial run: marking last signal as processed. New signals will be traded.");
    }
}

//+------------------------------------------------------------------+
//| Read signal file into array of strings                           |
//+------------------------------------------------------------------+
int ReadSignalFile(string &lines[])
{
    string filePath = SignalFileName;

    Print("ENTER: ReadSignalFile() - opening file: ", filePath);

    if(!FileIsExist(filePath))
        return 0;

    int handle = FileOpen(filePath, FILE_READ | FILE_TXT | FILE_ANSI);
    if(handle == INVALID_HANDLE)
    {
        Print("ERROR: Cannot open signal file: ", filePath, " Error: ", GetLastError());
        return 0;
    }

    ArrayResize(lines, 0);
    int count = 0;

    while(!FileIsEnding(handle))
    {
        string line = FileReadString(handle);
        line = StringTrimLeft(line);
        line = StringTrimRight(line);
        if(StringLen(line) > 0)
        {
            ArrayResize(lines, count + 1);
            lines[count] = line;
            count++;
        }
    }

    FileClose(handle);
    return count;
}

//+------------------------------------------------------------------+
//| Read last signal ID from file (for initial sync)                 |
//+------------------------------------------------------------------+
string ReadLastSignalID()
{
    Print("ENTER: ReadLastSignalID() - scanning file for last ID");
    string lines[];
    int count = ReadSignalFile(lines);
    if(count == 0)
        return "";

    string parts[];
    StringSplit(lines[count-1], '|', parts);
    if(ArraySize(parts) >= 13)
        return parts[0];
    return "";
}

//+------------------------------------------------------------------+
//| Process a parsed signal                                          |
//| Format: id|ts|sym|side|etype|emin|emax|sl|sltype|tps|tptype|be|conf|raw
//+------------------------------------------------------------------+
void ProcessSignal(string &parts[], int numParts)
{
    Print("ENTER: ProcessSignal() - received parts count=", numParts);
    if(numParts > 0)
        Print("  incoming signal id=", parts[0]);
    string signalID  = parts[0];
    string timestamp = parts[1];
    string symbol    = parts[2];
    string side      = parts[3];
    string entryType = parts[4];
    double entryMin  = StringToDouble(parts[5]);
    double entryMax  = StringToDouble(parts[6]);
    double sl        = StringToDouble(parts[7]);
    string slType    = parts[8];
    string tpStr     = parts[9];
    string tpType    = parts[10];
    bool moveBE      = (parts[11] == "1");
    double confidence = StringToDouble(parts[12]);
    string rawText   = "";
    if(numParts > 13)
        rawText = parts[13];

    // Validate symbol
    if(symbol != g_activeSymbol && symbol != "XAUUSD" && symbol != "GOLD")
    {
        Print("Skipping signal - wrong symbol: ", symbol);
        return;
    }

    // Normalize side
    bool isBuy = (side == "BUY" || side == "LONG");
    bool isSell = (side == "SELL" || side == "SHORT");
    if(!isBuy && !isSell)
    {
        Print("Skipping signal - invalid side: ", side);
        return;
    }

    // Parse take profits
    double tpValues[];
    string tpParts[];
    int tpCount = StringSplit(tpStr, '/', tpParts);
    for(int i = 0; i < tpCount; i++)
    {
        double tp = StringToDouble(tpParts[i]);
        ArrayResize(tpValues, ArraySize(tpValues) + 1);
        tpValues[ArraySize(tpValues) - 1] = tp;
    }

    // Log the signal
    Print("========================================");
    Print("SIGNAL DETECTED:");
    Print("  ID:         ", signalID);
    Print("  Side:       ", side, " (", entryType, ")");
    Print("  Symbol:     ", symbol);
    Print("  Entry Zone: ", entryMin, " - ", entryMax);
    Print("  SL:         ", sl, " (", slType, ")");
    Print("  TP Type:    ", tpType);
    Print("  TPs:        ", tpCount, " levels");
    for(int i = 0; i < ArraySize(tpValues); i++)
    {
        if(tpValues[i] == 0)
            Print("    TP", i+1, ": OPEN (no fixed target)");
        else
            Print("    TP", i+1, ": ", tpValues[i], " (", tpType, ")");
    }
    Print("  Move to BE: ", moveBE ? "Yes" : "No");
    Print("  Confidence: ", confidence);
    Print("  Raw:        ", rawText);
    Print("========================================");

    if(!EnableTrading)
    {
        Print("LOG ONLY: Trading is disabled. EnableTrading=false.");
        return;
    }

    // Check max open positions
    int openPositions = CountSignalPositions();
    if(openPositions >= MaxOpenPositions)
    {
        Print("SKIP: Max open positions reached (", openPositions, "/", MaxOpenPositions, ")");
        return;
    }

    // Check spread
    double spread = (symInfo.Ask() - symInfo.Bid()) / symInfo.Point();
    if(spread > MaxSpreadPoints)
    {
        Print("SKIP: Spread too high (", spread, " > ", MaxSpreadPoints, " points)");
        return;
    }

    // Close opposite positions if enabled
    if(CloseOnOppositeSignal)
        CloseOppositePositions(isBuy);

    // Execute the trade
    ExecuteSignal(isBuy, entryType, entryMin, entryMax, sl, slType,
                  tpValues, tpType, moveBE, signalID);
}

//+------------------------------------------------------------------+
//| Execute the trade signal                                         |
//+------------------------------------------------------------------+
void ExecuteSignal(bool isBuy, string entryType, double entryMin, double entryMax,
                   double sl, string slType, double &tpValues[], string tpType,
                   bool moveBE, string signalID)
{
    Print("ENTER: ExecuteSignal() - id=", signalID, " isBuy=", isBuy, " entryType=", entryType,
          " entryMin=", entryMin, " entryMax=", entryMax, " sl=", sl, " slType=", slType);
    double currentPrice = isBuy ? symInfo.Ask() : symInfo.Bid();
    double point = symInfo.Point();
    double pip = PipValue; // 1 pip = PipValue price units

    // Determine entry price and order type
    double entryPrice = 0.0;
    bool isLimit = (entryType == "LIMIT");
    bool isStop = (entryType == "STOP");

    if(entryMin > 0 && entryMax > 0)
    {
        if(isLimit)
        {
            // For BUY LIMIT: place below current price
            // For SELL LIMIT: place above current price
            if(isBuy && currentPrice > entryMax)
            {
                // Price is above zone - place buy limit at zone
                entryPrice = entryMax;
                Print("BUY LIMIT: Current price ", currentPrice, " above zone. Placing limit at ", entryPrice);
            }
            else if(!isBuy && currentPrice < entryMin)
            {
                entryPrice = entryMin;
                Print("SELL LIMIT: Current price ", currentPrice, " below zone. Placing limit at ", entryPrice);
            }
            else if(SkipIfOutsideZone)
            {
                // Price is inside or on wrong side of zone for limit
                if(isBuy && currentPrice >= entryMin && currentPrice <= entryMax)
                {
                    // Price inside zone - execute as market
                    entryPrice = currentPrice;
                    Print("Price inside entry zone. Executing as market order at ", entryPrice);
                    isLimit = false;
                }
                else
                {
                    Print("SKIP: Price (", currentPrice, ") not suitable for ",
                          (isBuy ? "BUY" : "SELL"),
                          " LIMIT at zone ", entryMin, "-", entryMax);
                    return;
                }
            }
            else
            {
                entryPrice = currentPrice;
                isLimit = false;
            }
        }
        else
        {
            // Market order - check if price is in zone
            if(currentPrice >= entryMin && currentPrice <= entryMax)
            {
                entryPrice = currentPrice;
            }
            else if(SkipIfOutsideZone && entryMin != entryMax)
            {
                Print("SKIP: Current price (", currentPrice, ") outside entry zone (",
                      entryMin, "-", entryMax, ")");
                return;
            }
            else
            {
                entryPrice = currentPrice;
                Print("Using market price: ", entryPrice);
            }
        }
    }
    else
    {
        // No entry zone specified - market order
        entryPrice = currentPrice;
    }

    // Calculate SL price
    double slPrice = 0.0;
    if(sl > 0)
    {
        if(slType == "PIPS")
        {
            // Calculate SL from pips
            double entryRef = entryPrice;
            if(entryMin > 0 && entryMax > 0)
            {
                // For buy: SL below entry_min; for sell: SL above entry_max
                if(isBuy)
                    entryRef = entryMin;
                else
                    entryRef = entryMax;
            }
            if(isBuy)
                slPrice = entryRef - (sl * pip);
            else
                slPrice = entryRef + (sl * pip);
            Print("SL calculated from pips: ", sl, " pips from ", entryRef, " = ", slPrice);
        }
        else
        {
            // Absolute price
            slPrice = sl;
        }
    }

    // Validate SL
    if(RequireSL && slPrice <= 0)
    {
        Print("SKIP: Stop loss required but not provided/calculated.");
        return;
    }

    // Adjust SL if too close
    if(slPrice > 0)
    {
        double slDistance = MathAbs(entryPrice - slPrice) / point;
        if(slDistance < MinSLDistance)
        {
            Print("WARNING: SL distance (", slDistance, " pts) < minimum (", MinSLDistance, " pts). Adjusting.");
            if(isBuy)
                slPrice = entryPrice - MinSLDistance * point;
            else
                slPrice = entryPrice + MinSLDistance * point;
        }
    }

    // Calculate TP prices
    double tpPrices[];
    int tpCount = ArraySize(tpValues);
    for(int i = 0; i < tpCount; i++)
    {
        double tpPrice = 0.0;
        if(tpValues[i] == 0)
        {
            // OPEN - no TP
            tpPrice = 0.0;
        }
        else if(tpType == "PIPS")
        {
            double entryRef = entryPrice;
            if(entryMin > 0 && entryMax > 0)
            {
                if(isBuy)
                    entryRef = entryMin;
                else
                    entryRef = entryMax;
            }
            if(isBuy)
                tpPrice = entryRef + (tpValues[i] * pip);
            else
                tpPrice = entryRef - (tpValues[i] * pip);
        }
        else
        {
            tpPrice = tpValues[i];
        }

        ArrayResize(tpPrices, ArraySize(tpPrices) + 1);
        tpPrices[ArraySize(tpPrices) - 1] = tpPrice;
    }

    // Calculate lot size
    double lots = LotSize;
    if(UseRiskPercent)
        lots = CalculateLotSize(entryPrice, slPrice);

    // Normalize lot size
    double minLot = symInfo.LotsMin();
    double maxLot = symInfo.LotsMax();
    double lotStep = symInfo.LotsStep();
    lots = MathMax(minLot, MathMin(maxLot, MathFloor(lots / lotStep) * lotStep));

    // Determine primary TP (first non-zero TP)
    double primaryTP = 0;
    for(int i = 0; i < ArraySize(tpPrices); i++)
    {
        if(tpPrices[i] > 0)
        {
            primaryTP = tpPrices[i];
            break;
        }
    }

    // If no TP, calculate based on SL distance (1:2 RR)
    if(primaryTP <= 0 && slPrice > 0)
    {
        double slDist = MathAbs(entryPrice - slPrice);
        if(isBuy)
            primaryTP = entryPrice + slDist * 2;
        else
            primaryTP = entryPrice - slDist * 2;
        Print("No TP provided. Calculated TP at 1:2 RR: ", primaryTP);
    }

    Print("EXECUTING TRADE:");
    Print("  Type:    ", isBuy ? "BUY" : "SELL", isLimit ? " LIMIT" : "");
    Print("  Lots:    ", lots);
    Print("  Entry:   ", entryPrice);
    Print("  SL:      ", slPrice);
    Print("  TP:      ", primaryTP);

    bool result = false;
    ulong ticket = 0;

    if(isLimit)
    {
        // Place pending limit order
        if(isBuy)
            result = trade.BuyLimit(lots, entryPrice, g_activeSymbol, slPrice, primaryTP, ORDER_TIME_GTC, 0, "WhatsApp Signal");
        else
            result = trade.SellLimit(lots, entryPrice, g_activeSymbol, slPrice, primaryTP, ORDER_TIME_GTC, 0, "WhatsApp Signal");
    }
    else
    {
        // Market order
        if(isBuy)
            result = trade.Buy(lots, g_activeSymbol, entryPrice, slPrice, primaryTP, "WhatsApp Signal");
        else
            result = trade.Sell(lots, g_activeSymbol, entryPrice, slPrice, primaryTP, "WhatsApp Signal");
    }

    if(result)
    {
        g_totalTrades++;
        ticket = trade.ResultOrder();
        Print("ORDER PLACED: Ticket #", ticket, " at ", trade.ResultPrice());
    }
    else
    {
        Print("ORDER FAILED: ", trade.ResultRetcode(), " - ", trade.ResultComment());
    }
}

//+------------------------------------------------------------------+
//| Calculate lot size based on risk percentage                      |
//+------------------------------------------------------------------+
double CalculateLotSize(double entryPrice, double slPrice)
{
    if(slPrice <= 0)
        return LotSize;

    double balance = AccountInfoDouble(ACCOUNT_BALANCE);
    double riskAmount = balance * RiskPercent / 100.0;

    double slDistance = MathAbs(entryPrice - slPrice);
    double tickValue = SymbolInfoDouble(g_activeSymbol, SYMBOL_TRADE_TICK_VALUE);
    double tickSize = SymbolInfoDouble(g_activeSymbol, SYMBOL_TRADE_TICK_SIZE);

    if(tickSize <= 0 || tickValue <= 0)
        return LotSize;

    double slTicks = slDistance / tickSize;
    double riskPerLot = slTicks * tickValue;

    if(riskPerLot <= 0)
        return LotSize;

    double lots = riskAmount / riskPerLot;
    return lots;
}

//+------------------------------------------------------------------+
//| Manage break-even: move SL to BE after first TP is hit           |
//+------------------------------------------------------------------+
void ManageBreakEven()
{
    Print("ENTER: ManageBreakEven() - checking positions for BE adjustments");
    for(int i = PositionsTotal() - 1; i >= 0; i--)
    {
        if(!posInfo.SelectByIndex(i))
            continue;

        if(posInfo.Magic() != MagicNumber || posInfo.Symbol() != g_activeSymbol)
            continue;

        ulong ticket = posInfo.Ticket();
        double openPrice = posInfo.PriceOpen();
        double currentSL = posInfo.StopLoss();
        double currentTP = posInfo.TakeProfit();
        bool isBuy = (posInfo.PositionType() == POSITION_TYPE_BUY);

        // Check if TP1 has been hit (price went past TP1)
        // If TP1 was the currentTP and position is still open, TP1 was hit
        // and TP was modified/removed, or position was partially closed.
        // For simplicity: if currentSL is 0 or far from entry, move to BE.

        double bePrice = isBuy ?
            openPrice + BreakEvenBufferPips * PipValue :
            openPrice - BreakEvenBufferPips * PipValue;

        // Check if price has moved favorably beyond a threshold (e.g., 50% of original TP distance)
        if(currentTP > 0)
        {
            double tpDistance = MathAbs(currentTP - openPrice);
            double currentPrice = isBuy ? symInfo.Bid() : symInfo.Ask();
            double moveDistance = isBuy ?
                (currentPrice - openPrice) : (openPrice - currentPrice);

            // If price has moved more than 50% toward TP, move SL to BE
            if(moveDistance > tpDistance * 0.5)
            {
                // Check if SL is already at or better than BE
                if(isBuy && (currentSL < bePrice || currentSL == 0))
                {
                    Print("Moving SL to break-even for ticket #", ticket, " (BE: ", bePrice, ")");
                    trade.PositionModify(ticket, bePrice, currentTP);
                }
                else if(!isBuy && (currentSL > bePrice || currentSL == 0))
                {
                    Print("Moving SL to break-even for ticket #", ticket, " (BE: ", bePrice, ")");
                    trade.PositionModify(ticket, bePrice, currentTP);
                }
            }
        }
    }
}

//+------------------------------------------------------------------+
//| Count positions opened by this EA                                |
//+------------------------------------------------------------------+
int CountSignalPositions()
{
    Print("ENTER: CountSignalPositions() - counting EA positions (Magic=", MagicNumber, ")");
    int count = 0;
    for(int i = PositionsTotal() - 1; i >= 0; i--)
    {
        if(posInfo.SelectByIndex(i))
        {
            if(posInfo.Magic() == MagicNumber && posInfo.Symbol() == g_activeSymbol)
                count++;
        }
    }
    return count;
}

//+------------------------------------------------------------------+
//| Close positions in opposite direction                           |
//+------------------------------------------------------------------+
void CloseOppositePositions(bool isBuySignal)
{
    Print("ENTER: CloseOppositePositions() - isBuySignal=", isBuySignal);
    for(int i = PositionsTotal() - 1; i >= 0; i--)
    {
        if(!posInfo.SelectByIndex(i))
            continue;

        if(posInfo.Magic() != MagicNumber || posInfo.Symbol() != g_activeSymbol)
            continue;

        bool isBuyPos = (posInfo.PositionType() == POSITION_TYPE_BUY);
        if(isBuyPos != isBuySignal)
        {
            ulong ticket = posInfo.Ticket();
            double volume = posInfo.Volume();
            Print("Closing opposite position #", ticket, " (", volume, " lots)");
            trade.PositionClose(ticket);
        }
    }
}

//+------------------------------------------------------------------+
//| Check if within trading hours                                    |
//+------------------------------------------------------------------+
bool IsWithinTradingHours()
{
    Print("ENTER: IsWithinTradingHours() - validating trading hours [", TradingStartHour, "-", TradingEndHour, "]");
    MqlDateTime dt;
    TimeToStruct(TimeCurrent(), dt);
    if(dt.hour < TradingStartHour || dt.hour >= TradingEndHour)
        return false;
    return true;
}

//+------------------------------------------------------------------+
//| Check if max drawdown is exceeded                                |
//+------------------------------------------------------------------+
bool IsMaxDrawdownExceeded()
{
    Print("ENTER: IsMaxDrawdownExceeded() - computing drawdown against MaxDrawdownPercent=", MaxDrawdownPercent);
    double balance = AccountInfoDouble(ACCOUNT_BALANCE);
    double equity = AccountInfoDouble(ACCOUNT_EQUITY);

    if(balance <= 0)
        return false;

    double drawdown = ((balance - equity) / balance) * 100.0;
    return drawdown >= MaxDrawdownPercent;
}
