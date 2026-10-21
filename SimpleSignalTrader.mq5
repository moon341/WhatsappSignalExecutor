//+------------------------------------------------------------------+
//|                                          SimpleSignalTrader.mq5 |
//|                     Simple file-watching signal trader example   |
//+------------------------------------------------------------------+
#property copyright "WhatsApp Signal Bridge"
#property version   "1.00"
#property strict

#include <Trade\Trade.mqh>

input string SignalFileName = "signals.txt"; // relative to MQL5/Files or full path
input bool   EnableTrading   = false;          // true to actually send orders
input bool   EnableTrailingStop = true;        // update active trades with a trailing SL
input double LotSize         = 0.01;
input int    MagicNumber     = 12345;
input int    PollSeconds     = 1;              // check every second
input int    PendingOrderExpiryMinutes = 120; // 0 disables expiry; pending orders older than this are removed
input double TrailingStopPrice = 1.00;        // fixed gold price distance in XAUUSD price units (0 disables trailing)

CTrade trade;
string  g_lastFileContent = "";
string  g_processedSignalIds[];
long    g_tpOrderTickets[];
string  g_tpLevelLists[];
int     g_tpIndexes[];

int FindTpRecordIndex(const long ticket)
{
   for(int i = 0; i < ArraySize(g_tpOrderTickets); i++)
   {
      if(g_tpOrderTickets[i] == ticket)
         return(i);
   }
   return(-1);
}

void SaveTpLevelsForOrder(const long ticket, const string tpField)
{
   if(ticket <= 0)
      return;

   string tpParts[];
   int tpCount = StringSplit(tpField, '/', tpParts);
   string serialized = "";
   for(int i = 0; i < tpCount; i++)
   {
      string value = tpParts[i];
      StringTrimLeft(value);
      StringTrimRight(value);
      if(StringLen(value) == 0)
         continue;
      if(StringLen(serialized) > 0)
         serialized += "/";
      serialized += value;
   }

   int idx = FindTpRecordIndex(ticket);
   if(idx >= 0)
   {
      g_tpLevelLists[idx] = serialized;
      g_tpIndexes[idx] = 0;
      return;
   }

   int size = ArraySize(g_tpOrderTickets);
   ArrayResize(g_tpOrderTickets, size + 1);
   ArrayResize(g_tpLevelLists, size + 1);
   ArrayResize(g_tpIndexes, size + 1);
   g_tpOrderTickets[size] = ticket;
   g_tpLevelLists[size] = serialized;
   g_tpIndexes[size] = 0;
}

void AdvanceTpIfCloseToMarket(const ulong ticket, const ENUM_POSITION_TYPE posType, const double currentStop, const double bid, const double ask)
{
   if(ticket == 0)
      return;

   long positionOrigin = PositionGetInteger(POSITION_IDENTIFIER);
   if(positionOrigin <= 0)
      return;

   int idx = FindTpRecordIndex(positionOrigin);
   if(idx < 0)
      return;

   string tpParts[];
   int tpCount = StringSplit(g_tpLevelLists[idx], '/', tpParts);
   if(tpCount <= 0)
      return;

   int activeIndex = g_tpIndexes[idx];
   if(activeIndex < 0)
      activeIndex = 0;

   if(activeIndex >= tpCount)
      return;

   double activeTarget = StringToDouble(tpParts[activeIndex]);
   double currentPrice = (posType == POSITION_TYPE_BUY) ? bid : ask;
   double distance = MathAbs(currentPrice - activeTarget);
   if(distance > 2.0)
      return;

   if(activeIndex + 1 >= tpCount)
      return;

   double nextTarget = StringToDouble(tpParts[activeIndex + 1]);
   bool ok = trade.PositionModify(ticket, currentStop, nextTarget);
   if(ok)
   {
      g_tpIndexes[idx] = activeIndex + 1;
      Print("SimpleSignalTrader: TP advanced ticket=", ticket,
            " from=", DoubleToString(activeTarget, Digits()),
            " to=", DoubleToString(nextTarget, Digits()),
            " market=", DoubleToString(currentPrice, Digits()),
            " distance=", DoubleToString(distance, Digits()));
   }
}

bool IsSignalAlreadyProcessed(const string signalId)
{
   for(int i = 0; i < ArraySize(g_processedSignalIds); i++)
   {
      if(g_processedSignalIds[i] == signalId)
         return(true);
   }
   return(false);
}

void AppendProcessedSignalIdToFile(const string signalId)
{
   if(StringLen(signalId) == 0)
      return;

   string processedFile = SignalFileName;
   int pos = StringFind(processedFile, ".txt");
   if(pos > 0)
      processedFile = StringSubstr(processedFile, 0, pos) + ".processed.txt";

   int handle = FileOpen(processedFile, FILE_READ | FILE_WRITE | FILE_TXT | FILE_ANSI);
   if(handle == INVALID_HANDLE)
   {
      handle = FileOpen(processedFile, FILE_WRITE | FILE_TXT | FILE_ANSI);
      if(handle == INVALID_HANDLE)
      {
         Print("SimpleSignalTrader: could not open processed ledger -> ", processedFile, " error=", GetLastError());
         return;
      }
   }

   FileSeek(handle, 0, SEEK_END);
   FileWriteString(handle, signalId + "\n");
   FileClose(handle);
   Print("SimpleSignalTrader: wrote processed signal ID to ledger: ", processedFile, " id=", signalId);
}

void MarkSignalProcessed(const string signalId)
{
   if(StringLen(signalId) == 0)
      return;

   if(IsSignalAlreadyProcessed(signalId))
      return;

   int size = ArraySize(g_processedSignalIds);
   ArrayResize(g_processedSignalIds, size + 1);
   g_processedSignalIds[size] = signalId;
   AppendProcessedSignalIdToFile(signalId);
}

void LoadProcessedSignalIdsFromQueue(const string content)
{
   if(StringLen(content) == 0)
      return;

   string lines[];
   int count = StringSplit(content, '\n', lines);
   for(int i = 0; i < count; i++)
   {
      string line = lines[i];
      StringTrimLeft(line);
      StringTrimRight(line);
      if(StringLen(line) == 0)
         continue;

      string parts[];
      int partCount = StringSplit(line, '|', parts);
      if(partCount < 1)
         continue;

      string signalId = parts[0];
      StringTrimLeft(signalId);
      StringTrimRight(signalId);
      if(StringLen(signalId) > 0)
         MarkSignalProcessed(signalId);
   }
}

void ClearSignalFilesAtStartup()
{
   int handle = FileOpen(SignalFileName, FILE_WRITE | FILE_TXT | FILE_ANSI);
   if(handle != INVALID_HANDLE)
   {
      FileWriteString(handle, "");
      FileClose(handle);
      Print("SimpleSignalTrader: cleared startup signal queue: ", SignalFileName);
   }
   else
   {
      Print("SimpleSignalTrader: could not clear signal queue ", SignalFileName, " error=", GetLastError());
   }

   Print("SimpleSignalTrader: left processed ledger intact; monitor.py is responsible for clearing processed entries alongside signals.txt");
}

//+------------------------------------------------------------------+
int OnInit()
{
   Print("SimpleSignalTrader: initializing");
   ClearSignalFilesAtStartup();

   string startupContent = ReadSignalFileContent(SignalFileName);
   if(StringLen(startupContent) > 0)
   {
      LoadProcessedSignalIdsFromQueue(startupContent);
      Print("SimpleSignalTrader: loaded ", ArraySize(g_processedSignalIds), " existing signal IDs from startup queue.");
   }

   int timerSeconds = PollSeconds;
   if(timerSeconds < 1)
      timerSeconds = 1;

   trade.SetExpertMagicNumber(MagicNumber);
   EventSetTimer(timerSeconds);
   Print("SimpleSignalTrader: watching file -> ", SignalFileName, " timerSeconds=", timerSeconds);
   return(INIT_SUCCEEDED);
}

//+------------------------------------------------------------------+
void OnDeinit(const int reason)
{
   EventKillTimer();
   Print("SimpleSignalTrader: stopped reason=", reason);
}

//+------------------------------------------------------------------+
void UpdateTrailingStops()
{
   if(!EnableTrailingStop)
      return;

   int total = PositionsTotal();
   for(int i = total - 1; i >= 0; i--)
   {
      ulong ticket = PositionGetTicket(i);
      if(ticket == 0)
         continue;

      if(!PositionSelectByTicket(ticket))
         continue;

      ENUM_POSITION_TYPE posType = (ENUM_POSITION_TYPE)PositionGetInteger(POSITION_TYPE);
      double openPrice = PositionGetDouble(POSITION_PRICE_OPEN);
      double currentStop = PositionGetDouble(POSITION_SL);
      double takeProfit = PositionGetDouble(POSITION_TP);
      double bid = SymbolInfoDouble(_Symbol, SYMBOL_BID);
      double ask = SymbolInfoDouble(_Symbol, SYMBOL_ASK);
      double trailDistance = TrailingStopPrice;
      double newStop = currentStop;

      if(posType == POSITION_TYPE_BUY)
      {
         double profit = bid - openPrice;
         if(profit > trailDistance)
         {
            double candidate = bid - trailDistance;
            if(currentStop == 0 || candidate > currentStop)
               newStop = candidate;
         }
      }
      else if(posType == POSITION_TYPE_SELL)
      {
         double profit = openPrice - ask;
         if(profit > trailDistance)
         {
            double candidate = ask + trailDistance;
            if(currentStop == 0 || candidate < currentStop)
               newStop = candidate;
         }
      }

      if(newStop > 0 && newStop != currentStop)
      {
         bool ok = trade.PositionModify(ticket, newStop, takeProfit);
         Print("SimpleSignalTrader: trailing stop updated ticket=", ticket,
               " oldStop=", DoubleToString(currentStop, Digits()),
               " newStop=", DoubleToString(newStop, Digits()),
               " success=", ok);
      }

      AdvanceTpIfCloseToMarket(ticket, posType, currentStop, bid, ask);
   }
}

void RemoveExpiredPendingOrders()
{
   if(PendingOrderExpiryMinutes <= 0)
      return;

   datetime now = TimeCurrent();
   long expireSeconds = (long)PendingOrderExpiryMinutes * 60;

   for(int i = OrdersTotal() - 1; i >= 0; i--)
   {
      ulong ticket = OrderGetTicket(i);
      if(ticket == 0)
         continue;

      // Use the default MQL5 overload; no SELECT_BY_TICKET / MODE_TRADES constants needed
      if(!OrderSelect(ticket))
         continue;

      long orderMagic = (long)OrderGetInteger(ORDER_MAGIC);
      if(orderMagic != (long)MagicNumber)
         continue;

      int type = (int)OrderGetInteger(ORDER_TYPE);
      if(type != ORDER_TYPE_BUY_LIMIT && type != ORDER_TYPE_SELL_LIMIT &&
         type != ORDER_TYPE_BUY_STOP && type != ORDER_TYPE_SELL_STOP)
         continue;

      datetime openedAt = (datetime)OrderGetInteger(ORDER_TIME_SETUP);
      long ageSeconds = (long)(now - openedAt);

      if(ageSeconds > expireSeconds)
      {
         bool ok = trade.OrderDelete(ticket);
         Print("SimpleSignalTrader: removed expired pending order ticket=", ticket,
               " ageSec=", ageSeconds, " success=", ok);
      }
   }
}

void OnTimer()
{
   RemoveExpiredPendingOrders();

   string content = ReadSignalFileContent(SignalFileName);
   if(StringLen(content) == 0)
   {
      Print("SimpleSignalTrader: no signal content read");
      return;
   }

   if(content != g_lastFileContent)
   {
      Print("SimpleSignalTrader: detected file update");
      g_lastFileContent = content;
      ProcessSignalFile(content);
   }

   if(EnableTrailingStop)
      UpdateTrailingStops();
}

//+------------------------------------------------------------------+
string ReadSignalFileContent(const string fileName)
{
   

   //Print("SimpleSignalTrader: reading signal file -> ", fileName);
   int handle = FileOpen(fileName, FILE_READ | FILE_TXT | FILE_ANSI);
   if(handle == INVALID_HANDLE)
   {
      Print("SimpleSignalTrader: cannot open file -> ", fileName, " error=", GetLastError());
      return("");
   }

   string content = "";
   int lineCount = 0;
   while(!FileIsEnding(handle))
   {
      string line = FileReadString(handle);
      StringTrimLeft(line);
      StringTrimRight(line);
      if(StringLen(line) > 0)
      {
         content += line + "\n";
         lineCount++;
      }
   }
   FileClose(handle);

   //Print("SimpleSignalTrader: file read complete -> ", fileName, " lines=", lineCount, " chars=", StringLen(content));
   return(content);
}

//+------------------------------------------------------------------+
void ProcessSignalFile(const string content)
{
   string lines[];
   int count = StringSplit(content, '\n', lines);
   for(int i = 0; i < count; i++)
   {
      string line = lines[i];
      StringTrimLeft(line);
      StringTrimRight(line);
      if(StringLen(line) == 0)
         continue;

      string parts[];
      int partCount = StringSplit(line, '|', parts);
      if(partCount < 1)
         continue;

      string signalId = parts[0];
      StringTrimLeft(signalId);
      StringTrimRight(signalId);
      if(StringLen(signalId) == 0)
         continue;

      if(IsSignalAlreadyProcessed(signalId))
      {
         Print("SimpleSignalTrader: already processed signalId=", signalId, " skipping queued replay.");
         continue;
      }

      Print("SimpleSignalTrader: parsing signal line -> ", line);
      ProcessSignalLine(line);
   }
}

//+------------------------------------------------------------------+
void ProcessSignalLine(const string line)
{
   string parts[];
   int partCount = StringSplit(line, '|', parts);
   if(partCount < 13)
   {
      Print("SimpleSignalTrader: invalid signal format, expected id|timestamp|symbol|side|entry_type|entry_min|entry_max|sl|sl_type|tps|tp_type|move_to_be|confidence|raw_text -> ", line);
      return;
   }

   string signalId = parts[0];
   string symbol   = parts[2];
   string side     = parts[3];
   StringTrimLeft(signalId);
   StringTrimRight(signalId);
   StringTrimLeft(symbol);
   StringTrimRight(symbol);
   StringTrimLeft(side);
   StringTrimRight(side);

   //Print("DEBUG side=", side, " len=", StringLen(side));
   for(int i = 0; i < StringLen(side); i++)
   {
      int ch = StringGetCharacter(side, i);
      //Print("char[", i, "] = ", ch);
   }
   //Print("DEBUG CHECK side=", side, " upper=", StringToUpper(side), " rawLine=", line);

   bool isBuy = (side == "BUY" || StringToUpper(side) == "LONG");
   bool isSell = (side == "SELL" || StringToUpper(side) == "SHORT");
   if(!isBuy && !isSell)
   {
      //Print("SimpleSignalTrader: invalid side -> ", side, " rawLine=", line);
      return;
   }

   double volume = LotSize > 0 ? LotSize : 0.01;
   double entryMin = StringToDouble(parts[5]);
   double entryMax = StringToDouble(parts[6]);
   double sl = StringToDouble(parts[7]);
   double tp = 0.0;
   Print("entryType=", parts[4], " upper=", StringToUpper(parts[4]));
   string entryType = parts[4];
   Print("entryType=", entryType);
   if(entryMin <= 0)
      entryMin = SymbolInfoDouble(_Symbol, SYMBOL_ASK);
   if(entryMax <= 0)
      entryMax = entryMin;
   if(sl <= 0)
      sl = entryMin;

   string tpField = (partCount > 9) ? parts[9] : "0";
   if(tpField != "0")
   {
      string tpParts[];
      int tpCount = StringSplit(tpField, '/', tpParts);
      if(tpCount > 0)
      {
         string firstTp = tpParts[0];
         StringTrimLeft(firstTp);
         StringTrimRight(firstTp);
         tp = StringToDouble(firstTp);
      }
   }
   if(tp <= 0)
      tp = entryMax;

   double ask = SymbolInfoDouble(_Symbol, SYMBOL_ASK);
   double bid = SymbolInfoDouble(_Symbol, SYMBOL_BID);
   double currentPrice = isBuy ? ask : bid;
   double price = currentPrice;
   bool isLimit = (entryType == "LIMIT");

   if(entryMin > 0 && entryMax > 0 && isLimit)
   {
      if(isBuy)
      {
         // BUY LIMIT should use the lower bound of the zone, which is usually below current market.
         price = entryMax;
      }
      else
      {
         // SELL LIMIT should use the upper bound of the zone, which is usually above current market.
         price = entryMin;
      }
   }
   else if(entryMin > 0)
   {
      price = entryMin;
   }

   Print("SimpleSignalTrader: signal -> signalId=", signalId,
         " symbol=", symbol,
         " side=", side,
         " entryType=", entryType,
         " entryMin=", DoubleToString(entryMin, Digits()),
         " entryMax=", DoubleToString(entryMax, Digits()),
         " bid=", DoubleToString(bid, Digits()),
         " ask=", DoubleToString(ask, Digits()),
         " sl=", DoubleToString(sl, Digits()),
         " tp=", DoubleToString(tp, Digits()),
         " chosenLimitPrice=", DoubleToString(price, Digits()),
         " volume=", DoubleToString(volume, 2));

   if(isLimit && price > 0)
   {
      if(isBuy && price >= ask)
         Print("SimpleSignalTrader: WARNING - BUY LIMIT price is not below current ask. This can trigger invalid price.");
      if(isSell && price <= bid)
         Print("SimpleSignalTrader: WARNING - SELL LIMIT price is not above current bid. This can trigger invalid price.");
   }

   if(!EnableTrading)
   {
      Print("SimpleSignalTrader: trading disabled, skipping order execution.");
      return;
   }

   if(IsSignalAlreadyProcessed(signalId))
   {
      Print("SimpleSignalTrader: already processed signalId=", signalId, " skipping duplicate.");
      return;
   }

   bool result = false;
   Print("trade type isLimit=", (string)isLimit, " entryMin=", entryMin, " entryMax=", entryMax);
   if(isLimit && entryMin > 0 && entryMax > 0)
   {
      Print("if(isLimit && entryMin > 0 && entryMax > 0): true");
      if(isBuy)
         result = trade.BuyLimit(volume, price, _Symbol, sl, tp, ORDER_TIME_GTC, 0, "SimpleSignalTrader");
      else
         result = trade.SellLimit(volume, price, _Symbol, sl, tp, ORDER_TIME_GTC, 0, "SimpleSignalTrader");
   }
   //else if(isBuy)
   //   {
   //   Print("else if(isBuy)");
   //   result = trade.Buy(volume, _Symbol, price, sl, tp, "SimpleSignalTrader");
   //   }
   //else
   //   {
   //   Print("else");
   //   result = trade.Sell(volume, _Symbol, price, sl, tp, "SimpleSignalTrader");
   //   }
   if(result)
   {
      ulong placedTicket = trade.ResultOrder();
      SaveTpLevelsForOrder((long)placedTicket, tpField);
      MarkSignalProcessed(signalId);
      Print("SimpleSignalTrader: order placed successfully, ticket=", placedTicket,
            " price=", DoubleToString(trade.ResultPrice(), Digits()));
   }
   else
      Print("SimpleSignalTrader: order failed -> ", trade.ResultRetcode(), " comment=", trade.ResultComment());
}

//+------------------------------------------------------------------+
