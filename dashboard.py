from __future__ import annotations

from threading import Lock
from typing import Any, Dict

from flask import Flask, jsonify, render_template_string

app = Flask(__name__)
state_lock = Lock()
state: Dict[str, Any] = {
    "status": "idle",
    "current_symbol": "US30Cash",
    "available_symbols": ["US30Cash", "GBPUSD"],
    "confidence_threshold": 65.0,
    "confidence": 0.0,
    "exit_confidence": 0.0,
    "market_condition": "ranging",
    "sentiment": "neutral",
    "decision_reason": "None",
    "last_signal": "None",
    "last_order": "None",
    "last_error": "None",
    "balance": None,
    "equity": None,
    "position": None,
    "win_rate": 0.0,
    "sharpe_ratio": 0.0,
    "groq_usage": {"calls": 0, "errors": 0, "prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
    "equity_curve": [],
    "trade_log": [],
    "ui_selected_symbol": "US30Cash",
}

HTML = """
<!doctype html>
<html>
  <head>
    <meta charset='utf-8' />
    <title>Analyzer Dashboard</title>
    <style>
      :root {
        --bg: #2a3f5f;
        --bg-soft: #4a5f7f;
        --card: #3a4f6f;
        --sky: #87ceeb;
        --sky-soft: #b0e0e6;
        --text: #eef6fb;
        --muted: #d0e2ec;
      }
      body {
        font-family: Inter, Segoe UI, Arial, sans-serif;
        margin: 0;
        background: linear-gradient(135deg, var(--bg), var(--bg-soft));
        color: var(--text);
      }
      .container { max-width: 1200px; margin: 0 auto; padding: 24px; }
      .header { display: flex; justify-content: space-between; align-items: center; gap: 16px; }
      .badge { background: var(--sky); color: #16304d; padding: 5px 10px; border-radius: 999px; font-weight: 700; }
      .grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(240px, 1fr)); gap: 16px; margin-top: 16px; }
      .card { background: rgba(58,79,111,0.95); border: 1px solid rgba(176,224,230,0.35); border-radius: 14px; padding: 16px; }
      .label { color: var(--muted); font-size: 12px; letter-spacing: .06em; text-transform: uppercase; }
      .value { font-size: 24px; margin-top: 8px; font-weight: 700; }
      .sub { margin-top: 8px; color: var(--sky-soft); font-size: 13px; }
      .meter { width: 100%; height: 12px; border-radius: 999px; background: rgba(255,255,255,0.18); overflow: hidden; margin-top: 12px; }
      .meter > div { height: 100%; width: 0%; background: var(--sky); transition: width .3s; }
      .chart-wrap { margin-top: 16px; }
      svg { width: 100%; height: 220px; }
      .trade-row { padding: 8px 0; border-bottom: 1px solid rgba(255,255,255,0.12); font-size: 13px; }
      .trade-row:last-child { border-bottom: none; }
      .positive { color: #b8ffcf; }
      .negative { color: #ffd0d0; }
      .selector { display:flex; gap:8px; align-items:center; }
      select { background:#243650; color:var(--text); border:1px solid var(--sky-soft); border-radius:8px; padding:6px 10px; }
      a { color: var(--sky-soft); }
    </style>
  </head>
  <body>
    <div class='container'>
      <div class='header'>
        <div>
          <h1>Analyzer Trading Dashboard</h1>
          <div class='sub'>Professional signal validation with Groq confidence scoring</div>
        </div>
        <div class='selector'>
          <span class='badge' id='status'>idle</span>
          <label for='symbol_selector'>Launch Symbol</label>
          <select id='symbol_selector'>
            <option>US30Cash</option>
            <option>GBPUSD</option>
          </select>
        </div>
      </div>

      <div class='grid'>
        <div class='card'>
          <div class='label'>AI Signal Confidence</div>
          <div class='value' id='confidence'>0%</div>
          <div class='meter'><div id='confidence_bar'></div></div>
          <div class='sub'>Threshold: <span id='confidence_threshold'>65</span>%</div>
        </div>
        <div class='card'>
          <div class='label'>Market Condition</div>
          <div class='value' id='market_condition'>ranging</div>
          <div class='sub'>Sentiment: <span id='sentiment'>neutral</span> | Exit confidence: <span id='exit_confidence'>0</span>%</div>
        </div>
        <div class='card'>
          <div class='label'>Performance</div>
          <div class='value'>Win Rate: <span id='win_rate'>0</span>%</div>
          <div class='sub'>Sharpe Ratio: <span id='sharpe_ratio'>0</span></div>
        </div>
        <div class='card'>
          <div class='label'>Groq Usage</div>
          <div class='sub'>Calls: <span id='g_calls'>0</span> | Errors: <span id='g_errors'>0</span></div>
          <div class='sub'>Prompt: <span id='g_prompt'>0</span> | Completion: <span id='g_completion'>0</span></div>
          <div class='sub'>Total tokens: <span id='g_total'>0</span></div>
        </div>
      </div>

      <div class='grid chart-wrap'>
        <div class='card'>
          <div class='label'>Account</div>
          <div class='sub'>Balance: <span id='balance'>-</span></div>
          <div class='sub'>Equity: <span id='equity'>-</span></div>
          <div class='sub'>Position: <span id='position'>-</span></div>
          <div class='sub'>Last signal: <span id='last_signal'>None</span></div>
          <div class='sub'>Last order: <span id='last_order'>None</span></div>
          <div class='sub'>Decision: <span id='decision_reason'>None</span></div>
          <div class='sub'>Last error: <span id='last_error'>None</span></div>
        </div>
        <div class='card'>
          <div class='label'>Equity Curve</div>
          <svg id='equity_chart'></svg>
        </div>
        <div class='card'>
          <div class='label'>Recent Trades</div>
          <div id='trade_log'></div>
        </div>
      </div>

      <div class='sub' style='margin-top:16px;'>UI selector updates launch command only (does not change a running bot). Run: <code id='switch_hint'>python bot.py --paper --symbol US30Cash</code></div>
    </div>

    <script>
      async function refresh() {
        const res = await fetch('/api/status');
        const data = await res.json();

        document.getElementById('status').textContent = data.status;
        document.getElementById('confidence').textContent = `${Number(data.confidence || 0).toFixed(1)}%`;
        document.getElementById('confidence_threshold').textContent = Number(data.confidence_threshold || 65).toFixed(0);
        document.getElementById('market_condition').textContent = data.market_condition || 'ranging';
        document.getElementById('sentiment').textContent = data.sentiment || 'neutral';
        document.getElementById('exit_confidence').textContent = Number(data.exit_confidence || 0).toFixed(1);
        document.getElementById('win_rate').textContent = Number(data.win_rate || 0).toFixed(2);
        document.getElementById('sharpe_ratio').textContent = Number(data.sharpe_ratio || 0).toFixed(3);

        const usage = data.groq_usage || {};
        document.getElementById('g_calls').textContent = usage.calls || 0;
        document.getElementById('g_errors').textContent = usage.errors || 0;
        document.getElementById('g_prompt').textContent = usage.prompt_tokens || 0;
        document.getElementById('g_completion').textContent = usage.completion_tokens || 0;
        document.getElementById('g_total').textContent = usage.total_tokens || 0;

        document.getElementById('balance').textContent = data.balance ?? '-';
        document.getElementById('equity').textContent = data.equity ?? '-';
        document.getElementById('position').textContent = data.position ?? '-';
        document.getElementById('last_signal').textContent = data.last_signal || 'None';
        document.getElementById('last_order').textContent = data.last_order || 'None';
        document.getElementById('decision_reason').textContent = data.decision_reason || 'None';
        document.getElementById('last_error').textContent = data.last_error || 'None';

        const currentSymbol = data.ui_selected_symbol || data.current_symbol || 'US30Cash';
        const select = document.getElementById('symbol_selector');
        if ([...select.options].every(o => o.value !== currentSymbol)) {
          const option = document.createElement('option');
          option.value = currentSymbol;
          option.textContent = currentSymbol;
          select.appendChild(option);
        }
        select.value = currentSymbol;
        updateSymbolHint(currentSymbol);

        const conf = Math.max(0, Math.min(100, Number(data.confidence || 0)));
        const bar = document.getElementById('confidence_bar');
        bar.style.width = `${conf}%`;
        bar.style.background = conf >= 75 ? '#8bf0ff' : conf >= 65 ? '#b0e0e6' : '#ffb3b3';

        renderChart(data.equity_curve || []);
        renderTrades(data.trade_log || []);
      }

      function renderChart(points) {
        const svg = document.getElementById('equity_chart');
        if (!points.length) {
          svg.innerHTML = '<text x="10" y="20" fill="#d0e2ec">No equity data yet</text>';
          return;
        }
        const width = 700;
        const height = 220;
        const max = Math.max(...points.map(p => p.equity));
        const min = Math.min(...points.map(p => p.equity));
        const pad = 20;
        const xStep = points.length > 1 ? (width - pad * 2) / (points.length - 1) : width / 2;
        const yScale = (value) => height - pad - ((value - min) / Math.max(1, max - min)) * (height - pad * 2);
        const linePoints = points.map((p, i) => `${i * xStep + pad},${yScale(p.equity)}`).join(' ');
        svg.innerHTML = `<polyline fill='none' stroke='#87ceeb' stroke-width='2.5' points='${linePoints}' />`;
      }

      function renderTrades(trades) {
        const container = document.getElementById('trade_log');
        if (!trades.length) {
          container.innerHTML = '<div class="sub">No trades yet</div>';
          return;
        }

        container.innerHTML = trades.slice(-8).reverse().map((trade) => {
          const pnl = Number(trade.pnl || 0);
          const cls = pnl >= 0 ? 'positive' : 'negative';
          const side = String(trade.side || '').toUpperCase();
          const time = trade.entry_time || '-';
          return `<div class='trade-row ${cls}'>${side} | ${time} | PnL ${pnl.toFixed(2)}</div>`;
        }).join('');
      }

      function updateSymbolHint(symbol) {
        document.getElementById('switch_hint').textContent = `python bot.py --paper --symbol ${symbol}`;
      }

      document.getElementById('symbol_selector').addEventListener('change', (event) => {
        const selected = event.target.value;
        updateSymbolHint(selected);
        fetch('/api/ui_symbol', {
          method: 'POST',
          headers: {'Content-Type': 'application/json'},
          body: JSON.stringify({symbol: selected}),
        });
      });

      setInterval(refresh, 5000);
      refresh();
    </script>
  </body>
</html>
"""


@app.get("/")
def index():
    return render_template_string(HTML)


@app.get("/api/status")
def status():
    return jsonify(state)


@app.post("/api/ui_symbol")
def set_ui_symbol():
    from flask import request

    payload = request.get_json(silent=True) or {}
    symbol = str(payload.get("symbol", "")).strip()
    if not symbol:
        return jsonify({"ok": False, "error": "symbol required"}), 400
    if symbol not in state.get("available_symbols", []):
        return jsonify({"ok": False, "error": "unsupported symbol"}), 400
    with state_lock:
        state["ui_selected_symbol"] = symbol
    return jsonify({"ok": True, "symbol": symbol})


@app.post("/api/backtest")
def backtest():
    from config import load_config
    from mt5_backtest import run_mt5_backtest

    cfg = load_config()
    result = run_mt5_backtest(cfg, timeframe="M1", bars=1200)
    with state_lock:
        state["equity_curve"] = result.equity_curve
        state["trade_log"] = result.trades
        state["last_signal"] = f"Backtest: {result.metrics['trades']} trades"
        state["last_order"] = f"PnL {result.metrics['net_pnl']}"
        state["win_rate"] = round(float(result.metrics.get("win_rate", 0.0)) * 100.0, 2)
        state["sharpe_ratio"] = float(result.metrics.get("sharpe_ratio", 0.0))
    return jsonify(result.metrics)



def update_state(**kwargs):
    with state_lock:
        state.update(kwargs)



def run_dashboard(host: str = "127.0.0.1", port: int = 8081):
    app.run(host=host, port=port, debug=False, use_reloader=False)
