from __future__ import annotations

import json
from threading import Lock
from typing import Any, Dict, List

from flask import Flask, jsonify, render_template_string

app = Flask(__name__)
state_lock = Lock()
state: Dict[str, Any] = {
    "status": "idle",
    "last_signal": "None",
    "last_order": "None",
    "last_error": "None",
    "balance": None,
    "equity": None,
    "position": None,
    "equity_curve": [],
    "trade_log": [],
}

HTML = """
<!doctype html>
<html>
  <head>
    <meta charset='utf-8' />
    <title>US30 Scalper Dashboard</title>
    <style>
      body { font-family: Arial, sans-serif; margin: 24px; background: #111; color: #f5f5f5; }
      .card { background: #1d1d1d; padding: 16px; border-radius: 10px; margin-bottom: 16px; }
      .pill { display: inline-block; padding: 4px 8px; border-radius: 999px; background: #2e7d32; color: white; }
      code { background: #2b2b2b; padding: 2px 6px; border-radius: 4px; }
    </style>
  </head>
  <body>
    <h1>US30 Scalper Dashboard</h1>
    <div class='card'>
      <div class='pill' id='status'>idle</div>
      <p><strong>Last signal:</strong> <span id='last_signal'>None</span></p>
      <p><strong>Last order:</strong> <span id='last_order'>None</span></p>
      <p><strong>Last error:</strong> <span id='last_error'>None</span></p>
    </div>
    <div class='card'>
      <p><strong>Balance:</strong> <span id='balance'>-</span></p>
      <p><strong>Equity:</strong> <span id='equity'>-</span></p>
      <p><strong>Position:</strong> <span id='position'>-</span></p>
    </div>
    <div class='card'>
      <h3>Equity curve</h3>
      <svg id='equity_chart' width='100%' height='220'></svg>
    </div>
    <div class='card'>
      <h3>Recent trades</h3>
      <div id='trade_log'></div>
    </div>
    <script>
      async function refresh() {
        const res = await fetch('/api/status');
        const data = await res.json();
        document.getElementById('status').textContent = data.status;
        document.getElementById('last_signal').textContent = data.last_signal;
        document.getElementById('last_order').textContent = data.last_order;
        document.getElementById('last_error').textContent = data.last_error;
        document.getElementById('balance').textContent = data.balance ?? '-';
        document.getElementById('equity').textContent = data.equity ?? '-';
        document.getElementById('position').textContent = data.position ?? '-';
        renderChart(data.equity_curve || []);
        renderTrades(data.trade_log || []);
      }

      function renderChart(points) {
        const svg = document.getElementById('equity_chart');
        if (!points.length) {
          svg.innerHTML = '<text x="10" y="20">No equity data yet</text>';
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
        svg.innerHTML = `<polyline fill='none' stroke='#4caf50' stroke-width='2' points='${linePoints}' />`;
      }

      function renderTrades(trades) {
        const container = document.getElementById('trade_log');
        if (!trades.length) {
          container.innerHTML = '<div>No trades yet</div>';
          return;
        }
        container.innerHTML = trades.slice(-8).reverse().map((trade) => {
          const pnl = Number(trade.pnl || 0);
          const cls = pnl >= 0 ? '#4caf50' : '#ff5252';
          return `<div style='padding:6px 0;border-bottom:1px solid #333;color:${cls};'>${trade.side.toUpperCase()} | ${trade.entry_time} | PnL ${pnl.toFixed(2)}</div>`;
        }).join('');
      }
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


@app.post("/api/backtest")
def backtest():
    from mt5_backtest import run_mt5_backtest
    from config import load_config

    cfg = load_config()
    result = run_mt5_backtest(cfg, timeframe="M1", bars=1200)
    with state_lock:
        state["equity_curve"] = result.equity_curve
        state["trade_log"] = result.trades
        state["last_signal"] = f"Backtest: {result.metrics['trades']} trades"
        state["last_order"] = f"PnL {result.metrics['net_pnl']}"
    return jsonify(result.metrics)


def update_state(**kwargs):
    with state_lock:
        state.update(kwargs)


def run_dashboard(host: str = "127.0.0.1", port: int = 8081):
    app.run(host=host, port=port, debug=False, use_reloader=False)
