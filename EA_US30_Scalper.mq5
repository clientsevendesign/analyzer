//+------------------------------------------------------------------+
//|                                              EA_US30_Scalper.mq5 |
//|                  Starter MQL5 EA for US30 scalping               |
//+------------------------------------------------------------------+
#property copyright "Copilot"
#property version   "1.00"
#property strict

input string   SymbolName = "US30Cash";
input int      FastEmaPeriod = 9;
input int      SlowEmaPeriod = 21;
input int      AtrPeriod = 14;
input double   RiskPerTradePct = 0.5;
input int      MagicNumber = 830100;
input int      SessionStartHour = 9;
input int      SessionEndHour = 22;

int OnInit()
  {
   Print("EA initialized for ", SymbolName);
   return(INIT_SUCCEEDED);
  }

void OnDeinit(const int reason)
  {
   Print("EA deinitialized. Reason: ", reason);
  }

void OnTick()
  {
   if(!IsWithinSession()) return;

   double fastEma = iMA(SymbolName, PERIOD_M1, FastEmaPeriod, 0, MODE_EMA, PRICE_CLOSE, 0);
   double slowEma = iMA(SymbolName, PERIOD_M1, SlowEmaPeriod, 0, MODE_EMA, PRICE_CLOSE, 0);
   double atr = iATR(SymbolName, PERIOD_M1, AtrPeriod, 0);

   if(_IsNan(fastEma) || _IsNan(slowEma) || _IsNan(atr)) return;

   // Placeholder logic: buy when fast EMA is above slow EMA and ATR is healthy.
   // Replace with your final MQL5 strategy once validated in Python.
   if(fastEma > slowEma && atr > 20.0)
     {
      Print("Buy signal placeholder");
     }
   else if(fastEma < slowEma && atr > 20.0)
     {
      Print("Sell signal placeholder");
     }
  }

bool IsWithinSession()
  {
   MqlDateTime dt;
   TimeToStruct(TimeCurrent(), dt);
   return(dt.hour >= SessionStartHour && dt.hour < SessionEndHour);
  }
