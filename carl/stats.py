"""Carls statistik: hur går det egentligen? Bygger på avslutade affärer i databasen."""
from dataclasses import dataclass, field


@dataclass
class Group:
    namn: str
    antal: int = 0
    vinster: int = 0
    summa: float = 0.0
    vinst_summa: float = 0.0
    forlust_summa: float = 0.0

    def add(self, r: float) -> None:
        self.antal += 1
        self.summa += r
        if r > 0:
            self.vinster += 1
            self.vinst_summa += r
        else:
            self.forlust_summa += r

    @property
    def traffsakerhet(self) -> float:
        return 100 * self.vinster / self.antal if self.antal else 0.0

    @property
    def snitt_vinst(self) -> float:
        return self.vinst_summa / self.vinster if self.vinster else 0.0

    @property
    def snitt_forlust(self) -> float:
        n = self.antal - self.vinster
        return self.forlust_summa / n if n else 0.0

    @property
    def profit_factor(self) -> float | None:
        return self.vinst_summa / -self.forlust_summa if self.forlust_summa < 0 else None


@dataclass
class Stats:
    totalt: Group
    per_strategi: dict[str, Group] = field(default_factory=dict)
    per_havstang: dict[str, Group] = field(default_factory=dict)
    per_storlek: dict[str, Group] = field(default_factory=dict)
    per_riktning: dict[str, Group] = field(default_factory=dict)
    likvidationer: int = 0
    konkurser: int = 0
    avgifter_sek: float = 0.0
    storsta_vinst: tuple | None = None
    storsta_forlust: tuple | None = None
    saknar_lardom: list = field(default_factory=list)


def _lev_bucket(h: float) -> str:
    if h <= 1:
        return "1x (ingen)"
    if h <= 2:
        return "1–2x"
    if h <= 5:
        return "2–5x"
    return ">5x"


def _size_bucket(p: float | None) -> str:
    if p is None:
        return "okänd"
    if p < 5:
        return "<5 % av kontot"
    if p < 15:
        return "5–15 %"
    if p < 35:
        return "15–35 %"
    return ">35 %"


def compute(conn, agent_id: str = "carl") -> Stats:
    rows = conn.execute("SELECT * FROM trades WHERE agent_id=? AND resultat_sek IS NOT NULL ORDER BY id",
                        (agent_id,)).fetchall()
    st = Stats(Group("Totalt"))

    def g(d, k):
        return d.setdefault(k, Group(k))

    for t in rows:
        r = t["resultat_sek"]
        st.totalt.add(r)
        g(st.per_strategi, t["strategi"] or "(ingen)").add(r)
        g(st.per_havstang, _lev_bucket(t["havstang"])).add(r)
        g(st.per_storlek, _size_bucket(t["andel_procent"])).add(r)
        g(st.per_riktning, "blankning" if t["handling"] == "cover" else
          ("likvidation" if t["handling"] == "liquidation" else "lång")).add(r)
        if t["handling"] == "liquidation":
            st.likvidationer += 1
        if st.storsta_vinst is None or r > st.storsta_vinst[1]:
            st.storsta_vinst = (t["ticker"], r, t["tid"][:10])
        if st.storsta_forlust is None or r < st.storsta_forlust[1]:
            st.storsta_forlust = (t["ticker"], r, t["tid"][:10])
        if not t["lardom"]:
            st.saknar_lardom.append(t)
    acc = conn.execute("SELECT * FROM accounts WHERE agent_id=?", (agent_id,)).fetchone()
    if acc:
        st.konkurser, st.avgifter_sek = acc["konkurser"], acc["avgifter_sek"]
    return st


def format_stats(st: Stats) -> str:
    out = []
    t = st.totalt
    if not t.antal:
        out.append("Inga avslutade affärer än – ingen statistik att lära av.")
    else:
        pf = f"{t.profit_factor:.2f}" if t.profit_factor else "-"
        out.append(f"Avslutade affärer: {t.antal}   Träffsäkerhet: {t.traffsakerhet:.0f} %   "
                   f"Resultat: {t.summa:+,.0f} kr   Profit factor: {pf}")
        out.append(f"Snittvinst: {t.snitt_vinst:+,.0f} kr   Snittförlust: {t.snitt_forlust:+,.0f} kr")
        if st.storsta_vinst:
            out.append(f"Största vinst: {st.storsta_vinst[0]} {st.storsta_vinst[1]:+,.0f} kr ({st.storsta_vinst[2]})   "
                       f"Största förlust: {st.storsta_forlust[0]} {st.storsta_forlust[1]:+,.0f} kr ({st.storsta_forlust[2]})")
        for titel, d in (("Per strategi", st.per_strategi), ("Per hävstång", st.per_havstang),
                         ("Per positionsstorlek", st.per_storlek), ("Per riktning", st.per_riktning)):
            out.append(f"\n{titel}:")
            for grp in sorted(d.values(), key=lambda x: -x.summa):
                out.append(f"  {grp.namn:<18} {grp.antal:>3} st  träff {grp.traffsakerhet:>3.0f} %  "
                           f"resultat {grp.summa:>+10,.0f} kr  snitt {grp.summa / grp.antal:>+8,.0f} kr")
    out.append(f"\nLikvidationer: {st.likvidationer}   KONKURSER: {st.konkurser}   Betalda avgifter: {st.avgifter_sek:,.0f} kr")
    if st.saknar_lardom:
        out.append(f"\n⚠ {len(st.saknar_lardom)} avslutade affärer saknar lärdom: "
                   + ", ".join(f"#{x['id']} {x['ticker']}" for x in st.saknar_lardom)
                   + "\n  Skriv: python journal.py lardom <id> \"...\"")
    return "\n".join(out)
