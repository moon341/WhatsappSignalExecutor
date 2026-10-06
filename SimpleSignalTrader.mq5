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
input double LotSize         = 0.01;
input int    MagicNumber     = 12345;
input int    PollSeconds     = 1;              // check every second

CTrade trade;
string  g_lastFileContent = "";
string  g_processedSignalIds[];

bool IsSignalAlreadyProcessed(const string signalId)
{
   for(int i = 0; i < ArraySize(g_processedSignalIds); i++)
   {
      if(g_processedSignalIds[i] == signalId)
         return(true);
   }
   return(false);
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
}

//+------------------------------------------------------------------+
int OnInit()
{
   Print("SimpleSignalTrader: initializing");

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
void OnTimer()
{


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
   Print(parts[4],StringToUpper(parts[4]));
   string entryType = parts[4];
   Print(entryType);
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

   double currentPrice = isBuy ? SymbolInfoDouble(_Symbol, SYMBOL_ASK) : SymbolInfoDouble(_Symbol, SYMBOL_BID);
   double price = currentPrice;
   bool isLimit = (entryType == "LIMIT");

   if(entryMin > 0 && entryMax > 0 && isLimit)
   {
      if(isBuy)
      {
         if(currentPrice > entryMax)
            price = entryMin;
         else if(currentPrice >= entryMin && currentPrice <= entryMax)
            price = entryMin;
         else
            price = entryMin;
      }
      else
      {
         if(currentPrice < entryMin)
            price = entryMax;
         else if(currentPrice >= entryMin && currentPrice <= entryMax)
            price = entryMax;
         else
            price = entryMax;
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
         " sl=", DoubleToString(sl, Digits()),
         " tp=", DoubleToString(tp, Digits()),
         " orderPrice=", DoubleToString(price, Digits()),
         " volume=", DoubleToString(volume, 2));

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
   Print("trade type",isLimit,entryMin,entryMax);
   if(isLimit && entryMin > 0 && entryMax > 0)
   {
      Print("if(isLimit && entryMin > 0 && entryMax > 0):true");
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
      MarkSignalProcessed(signalId);
      Print("SimpleSignalTrader: order placed successfully, ticket=", trade.ResultOrder(),
            " price=", DoubleToString(trade.ResultPrice(), Digits()));
   }
   else
      Print("SimpleSignalTrader: order failed -> ", trade.ResultRetcode(), " comment=", trade.ResultComment());
}

//+------------------------------------------------------------------+
