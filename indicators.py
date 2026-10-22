"""Teknisk analys.

  python indicators.py VOLV-B.ST              # detaljerad analys av en ticker
  python indicators.py VOLV-B.ST AAPL NVDA    # jämförelsetabell
  python indicators.py --lista                # hela bevakningslistan i config.yaml
  python indicators.py --lista --grupp dolda  # bara en grupp (t.ex. mindre kända bolag)
  python indicators.py --lista --sortera rsi  # sortera (rsi, 1m, 3m, vol, fran_hogsta)
"""
import sys

from carl import config, indicators, prices


def fmt(v, d=1, pct=False):
    if v is None:
        return "-"
    return f"{v:+.{d}f}%" if pct else f"{v:,.{d}f}"


def detail(t: str) -> int:
    try:
        s = indicators.summarize(t, prices.history(t))
    except (prices.PriceError, ValueError) as e:
        print(f"{t}: FEL: {e}")
        return 2
    print(f"=== {s.ticker}  {s.pris:,.2f}  (stängning {s.datum}) ===")
    print(f"SMA20/50/200:   {fmt(s.sma20, 2)} / {fmt(s.sma50, 2)} / {fmt(s.sma200, 2)}")
    print(f"RSI14:          {s.rsi14:.1f}")
    print(f"MACD:           {s.macd:.3f}  signal {s.macd_signal:.3f}  hist {s.macd_hist:+.3f}")
    print(f"Volym:          {fmt(s.volym, 0)}  (snitt 20d {fmt(s.volym_snitt20, 0)}, {fmt(s.volym_ratio, 2)}x)")
    print(f"Volatilitet:    {fmt(s.volatilitet_ar)} % per år, ATR14 {fmt(s.atr14_procent, 2)} % per dag")
    print(f"Avkastning:     1v {fmt(s.avk_1v, pct=True)}  1m {fmt(s.avk_1m, pct=True)}  "
          f"3m {fmt(s.avk_3m, pct=True)}  1å {fmt(s.avk_1a, pct=True)}")
    print(f"52 veckor:      {s.lagsta_52v:,.2f} – {s.hogsta_52v:,.2f}  ({s.fran_hogsta_procent:+.1f}% från högsta)")
    for x in s.signaler:
        print(f"  • {x}")
    return 0


def table(tickers: list[str], sortera: str | None) -> int:
    rows, fel = [], []
    for t in tickers:
        try:
            rows.append(indicators.summarize(t, prices.history(t)))
        except (prices.PriceError, ValueError) as e:
            fel.append(f"{t}: {e}")
    key = {"rsi": lambda s: s.rsi14, "1m": lambda s: s.avk_1m or 0, "3m": lambda s: s.avk_3m or 0,
           "vol": lambda s: s.volatilitet_ar or 0, "fran_hogsta": lambda s: s.fran_hogsta_procent}.get(sortera)
    if key:
        rows.sort(key=key)
    print(f"{'Ticker':<20}{'Pris':>11}{'RSI':>6}{'MACDh':>9}{'>SMA50':>7}{'>SMA200':>8}{'1v':>8}{'1m':>8}{'3m':>8}"
          f"{'Vol%':>6}{'VolX':>6}{'Fr.högsta':>10}")
    for s in rows:
        a50 = "-" if not s.sma50 else ("ja" if s.pris > s.sma50 else "nej")
        a200 = "-" if not s.sma200 else ("ja" if s.pris > s.sma200 else "nej")
        print(f"{s.ticker:<20}{s.pris:>11,.2f}{s.rsi14:>6.0f}{s.macd_hist:>+9.2f}{a50:>7}{a200:>8}"
              f"{fmt(s.avk_1v, pct=True):>8}{fmt(s.avk_1m, pct=True):>8}{fmt(s.avk_3m, pct=True):>8}"
              f"{fmt(s.volatilitet_ar, 0):>6}{fmt(s.volym_ratio, 1):>6}{s.fran_hogsta_procent:>+9.1f}%")
    for f in fel:
        print("! " + f)
    return 0


def main(args: list[str]) -> int:
    sortera = args[args.index("--sortera") + 1] if "--sortera" in args else None
    grupp_namn = args[args.index("--grupp") + 1] if "--grupp" in args else None
    args = [a for a in args if a not in ("--sortera", sortera, "--grupp", grupp_namn)]
    if "--lista" in args:
        bl = config.load().get("bevakningslista", {})
        if grupp_namn:
            bl = {grupp_namn: bl.get(grupp_namn, [])}
        tickers = [t for grupp in bl.values() for t in grupp]
        return table(tickers, sortera)
    if not args:
        print(__doc__)
        return 1
    return detail(args[0]) if len(args) == 1 else table(args, sortera)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
