"""Bygger en fristående ögonblicksbild av dashboarden (data inbakad) till data/dashboard.html.
Carl publicerar den filen som en privat webbsida efter varje session.

  python dashboard/build.py
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from carl import dashboard_data, db  # noqa: E402

TEMPLATE = ROOT / "dashboard" / "index.html"
OUT = ROOT / "data" / "dashboard.html"


def render(data: dict) -> str:
    blob = json.dumps(data, ensure_ascii=False, default=str).replace("</", "<\\/")
    return TEMPLATE.read_text(encoding="utf-8").replace("/*__CARL_DATA__*/null", blob, 1)


def main() -> None:
    with db.session() as conn:
        db.ensure_agent(conn)
        data = dashboard_data.build(conn)
    OUT.write_text(render(data), encoding="utf-8")
    print(f"Dashboard byggd: {OUT.relative_to(ROOT)}  (värde {data['totalt']:,.2f} kr)")


if __name__ == "__main__":
    main()
