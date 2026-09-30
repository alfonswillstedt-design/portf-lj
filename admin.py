"""Huvudchattens överblick: läget på alla grenar (= alla chattar) i GitHub.

  python admin.py          # senaste aktivitet, problemrapporter och Carls portfölj per gren
"""
import sqlite3
import subprocess
import sys
import tempfile
from pathlib import Path

HUVUDGREN = "claude/zealous-galileo-d3iiyk"


def git(*a: str) -> str:
    return subprocess.run(["git", *a], capture_output=True, text=True).stdout.rstrip()


def main() -> int:
    git("fetch", "--all", "--prune", "-q")
    branches = [b.strip() for b in git("branch", "-r", "--format=%(refname:short)").splitlines()
                if b.strip() and not b.endswith("/HEAD")]
    main_ref = f"origin/{HUVUDGREN}"
    for b in branches:
        print(f"\n=== {b}{'  (HUVUDGREN)' if b == main_ref else ''}")
        print(git("log", "-3", "--format=  %h %ad  %s", "--date=format:%d/%m %H:%M", b))
        if b != main_ref:
            ahead = git("rev-list", "--count", f"{main_ref}..{b}")
            behind = git("rev-list", "--count", f"{b}..{main_ref}")
            print(f"  {ahead} commits före huvudgrenen, {behind} efter")
        prob = git("show", f"{b}:data/problem.md")
        if prob:
            oppna = [l for l in prob.splitlines() if l.startswith("- [ ]")]
            print(f"  PROBLEM: {len(oppna)} olösta" + "".join(f"\n    {l}" for l in oppna[:10]))
        blob = subprocess.run(["git", "show", f"{b}:data/carl.db"], capture_output=True).stdout
        if blob:
            with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
                f.write(blob)
            c = sqlite3.connect(f.name)
            try:
                kassa, konk = c.execute("SELECT kassa_sek, konkurser FROM accounts").fetchone()
                n = c.execute("SELECT COUNT(*) FROM trades").fetchone()[0]
                eq = c.execute("SELECT totalt_sek, tid FROM equity ORDER BY tid DESC LIMIT 1").fetchone()
                print(f"  Portfölj: {eq[0]:,.0f} kr ({eq[1][:16]}), kassa {kassa:,.0f} kr, {n} affärer, {konk} konkurser"
                      if eq else f"  Portfölj: kassa {kassa:,.0f} kr, {n} affärer")
            except Exception as e:
                print(f"  (kunde inte läsa databasen: {e})")
            finally:
                c.close()
                Path(f.name).unlink()
    return 0


if __name__ == "__main__":
    sys.exit(main())
