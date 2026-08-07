"""
Live PR Report Viewer + SQL Server logger.

Pulls JSON from SapPrReport.php server-side (avoids browser CORS issues),
serves an auto-refreshing HTML table, and simultaneously writes a
timestamped history log into SQL Server (192.168.66.33 / QMS_PR_Report).

Run:
    pip install flask requests pyodbc
    py app.py
Then open http://localhost:5001 (or http://<server-34-ip>:5001) in a browser.
"""

from flask import Flask, jsonify, render_template_string
import requests

import db_config as cfg

try:
    import db_writer
    _DB_WRITER_AVAILABLE = True
except Exception as _e:
    _DB_WRITER_AVAILABLE = False
    _DB_WRITER_IMPORT_ERROR = _e

app = Flask(__name__)

PORT = 5001
REFRESH_SECONDS = 5

INDEX_HTML = """
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<title>Live PR Report</title>
<style>
  :root {
    --bg: #0f1115;
    --panel: #161a21;
    --border: #2a2f3a;
    --text: #e6e9ef;
    --muted: #8b93a5;
    --accent: #4f9dff;
    --row-alt: #12151b;
    --row-hover: #1c2129;
  }
  * { box-sizing: border-box; }
  body {
    margin: 0;
    background: var(--bg);
    color: var(--text);
    font-family: 'Segoe UI', Roboto, Arial, sans-serif;
    font-size: 13px;
  }
  header {
    position: sticky;
    top: 0;
    z-index: 10;
    background: var(--panel);
    border-bottom: 1px solid var(--border);
    padding: 12px 20px;
    display: flex;
    align-items: center;
    justify-content: space-between;
    flex-wrap: wrap;
    gap: 10px;
  }
  header h1 { font-size: 16px; margin: 0; font-weight: 600; }
  .status { display: flex; align-items: center; gap: 8px; color: var(--muted); }
  .dot {
    width: 8px; height: 8px; border-radius: 50%;
    background: #3ddc84; box-shadow: 0 0 6px #3ddc84;
    animation: pulse 1.5s infinite;
  }
  .dot.error { background: #ff5c5c; box-shadow: 0 0 6px #ff5c5c; animation: none; }
  @keyframes pulse { 0% { opacity: 1; } 50% { opacity: 0.3; } 100% { opacity: 1; } }
  #search {
    background: var(--bg); border: 1px solid var(--border); color: var(--text);
    padding: 6px 10px; border-radius: 6px; width: 240px;
  }
  #search:focus { outline: none; border-color: var(--accent); }
  .table-wrap { overflow: auto; height: calc(100vh - 58px); }
  table { border-collapse: collapse; width: 100%; white-space: nowrap; }
  thead th {
    position: sticky; top: 0; background: var(--panel); color: var(--accent);
    text-align: left; padding: 8px 12px; border-bottom: 2px solid var(--border);
    font-weight: 600; z-index: 5; cursor: pointer; user-select: none;
  }
  thead th:hover { color: #fff; }
  tbody td { padding: 6px 12px; border-bottom: 1px solid var(--border); }
  tbody tr:nth-child(even) { background: var(--row-alt); }
  tbody tr:hover { background: var(--row-hover); }
  .meta { color: var(--muted); padding: 10px 20px; }
  .err-banner { color: #ff5c5c; padding: 10px 20px; display: none; }
</style>
</head>
<body>
<header>
  <h1>Live PR Report</h1>
  <input id="search" type="text" placeholder="Filter rows..." />
  <div class="status">
    <span class="dot" id="dot"></span>
    <span id="statusText">Loading...</span>
  </div>
</header>
<div class="err-banner" id="errBanner"></div>
<div class="meta" id="meta"></div>
<div class="table-wrap">
  <table>
    <thead><tr id="headRow"></tr></thead>
    <tbody id="body"></tbody>
  </table>
</div>

<script>
const REFRESH_MS = {{ refresh_seconds }} * 1000;
let rawRows = [];
let columns = [];
let sortCol = null;
let sortDir = 1;

function setStatus(ok, text) {
  document.getElementById('dot').className = ok ? 'dot' : 'dot error';
  document.getElementById('statusText').textContent = text;
}

function renderHead() {
  const headRow = document.getElementById('headRow');
  headRow.innerHTML = '';
  columns.forEach(col => {
    const th = document.createElement('th');
    th.textContent = col + (sortCol === col ? (sortDir === 1 ? ' \u25B2' : ' \u25BC') : '');
    th.onclick = () => {
      if (sortCol === col) { sortDir *= -1; } else { sortCol = col; sortDir = 1; }
      renderHead();
      renderBody();
    };
    headRow.appendChild(th);
  });
}

function renderBody() {
  const filter = document.getElementById('search').value.toLowerCase();
  let rows = rawRows.filter(r => !filter || JSON.stringify(r).toLowerCase().includes(filter));

  if (sortCol) {
    rows = rows.slice().sort((a, b) => {
      const av = (a[sortCol] ?? '').toString();
      const bv = (b[sortCol] ?? '').toString();
      const an = parseFloat(av), bn = parseFloat(bv);
      let cmp;
      if (!isNaN(an) && !isNaN(bn) && av.trim() !== '' && bv.trim() !== '') {
        cmp = an - bn;
      } else {
        cmp = av.localeCompare(bv);
      }
      return cmp * sortDir;
    });
  }

  const body = document.getElementById('body');
  body.innerHTML = '';
  const frag = document.createDocumentFragment();
  rows.forEach(row => {
    const tr = document.createElement('tr');
    columns.forEach(col => {
      const td = document.createElement('td');
      const val = row[col];
      td.textContent = (val === null || val === undefined) ? '' : val;
      tr.appendChild(td);
    });
    frag.appendChild(tr);
  });
  body.appendChild(frag);

  document.getElementById('meta').textContent =
    `${rows.length} of ${rawRows.length} rows` + (filter ? ' (filtered)' : '');
}

async function refresh() {
  try {
    const res = await fetch('/api/data');
    const json = await res.json();
    if (!json.ok) throw new Error(json.error || 'Unknown error');

    rawRows = json.rows;
    if (rawRows.length > 0) {
      const newColumns = Object.keys(rawRows[0]);
      if (JSON.stringify(newColumns) !== JSON.stringify(columns)) {
        columns = newColumns;
        renderHead();
      }
    }
    renderBody();
    document.getElementById('errBanner').style.display = 'none';
    setStatus(true, 'Live \u00b7 updated ' + new Date().toLocaleTimeString());
  } catch (e) {
    setStatus(false, 'Error \u00b7 retrying...');
    const banner = document.getElementById('errBanner');
    banner.textContent = 'Fetch failed: ' + e.message;
    banner.style.display = 'block';
  }
}

document.getElementById('search').addEventListener('input', renderBody);

refresh();
setInterval(refresh, REFRESH_MS);
</script>
</body>
</html>
"""


def normalize_rows(data):
    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        for key in ("data", "rows", "result", "results", "d"):
            if key in data and isinstance(data[key], list):
                return data[key]
        return [data]
    return []


@app.route("/")
def index():
    return render_template_string(INDEX_HTML, refresh_seconds=REFRESH_SECONDS)


@app.route("/api/data")
def api_data():
    try:
        resp = requests.get(cfg.SOURCE_URL, timeout=15)
        resp.raise_for_status()
        data = resp.json()
        rows = normalize_rows(data)
        return jsonify({"ok": True, "rows": rows, "count": len(rows)})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 200


if __name__ == "__main__":
    if _DB_WRITER_AVAILABLE:
        try:
            db_writer.start_background_thread()
        except Exception as e:
            print(f"[db_writer] Failed to start: {e}")
            print("[db_writer] The live table will still work; SQL logging is disabled.")
    else:
        print(f"[db_writer] Not available ({_DB_WRITER_IMPORT_ERROR}). "
              f"Run: pip install pyodbc")

    print(f"Serving live PR report on http://localhost:{PORT}")
    app.run(host="0.0.0.0", port=PORT, debug=False)
