"""Live-dashboard med FastAPI (valfri – behövs bara om Carl körs som eget program).
Sidan hämtar ny data var 5:e sekund.

  pip install fastapi uvicorn
  python dashboard/app.py          # öppna sedan http://127.0.0.1:8000
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from fastapi import FastAPI  # noqa: E402
from fastapi.responses import HTMLResponse  # noqa: E402

from carl import dashboard_data, db  # noqa: E402

app = FastAPI(title="Carl-Gustaf")
PAGE = ("<!doctype html><html lang='sv'><head><meta charset='utf-8'>"
        "<meta name='viewport' content='width=device-width, initial-scale=1'></head><body style='margin:0'>"
        + (ROOT / "dashboard" / "index.html").read_text(encoding="utf-8") + "</body></html>")


@app.get("/", response_class=HTMLResponse)
def index():
    return PAGE


@app.get("/api/data")
def data():
    with db.session() as conn:
        db.ensure_agent(conn)
        return dashboard_data.build(conn)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8000)
