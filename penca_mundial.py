#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
penca_mundial.py
================
Genera el MARCADOR EXACTO MÁS PROBABLE de cada partido del Mundial 2026
a partir de las cuotas reales de las mejores casas de apuestas (The Odds API).

Cómo funciona:
  1) Baja las cuotas 1X2 (ganador) y Over/Under (totals) de The Odds API.
     UN solo request trae TODOS los partidos del torneo con decenas de casas.
  2) Les quita el margen de la casa  -> probabilidades "justas".
  3) Promedia entre todas las casas disponibles.
  4) Ajusta un modelo de Poisson para encontrar los goles esperados de cada
     equipo que mejor reproducen esas probabilidades.
  5) Calcula la probabilidad de cada marcador exacto y elige el que maximiza
     los puntos esperados (sistema 8/5/3).
  6) Exporta predicciones.csv y predicciones.html (checklist con progreso).

USO:
  export ODDS_API_KEY="tu_key"        (o se usa la hardcodeada abajo)
  python3 penca_mundial.py            -> genera predicciones (Fecha 1)
  python3 penca_mundial.py --sports   -> lista las sport keys de fútbol activas
  python3 penca_mundial.py --riesgo k=5  -> también genera la línea de riesgo

Requisitos: pip install requests numpy scipy
"""

import os
import sys
import csv
import json
import math
import html
import datetime as dt

import requests
import numpy as np
from scipy.optimize import minimize

# ----------------------------------------------------------------------------
# CONFIGURACIÓN
# ----------------------------------------------------------------------------
API_KEY = os.environ.get("ODDS_API_KEY", "fc842a3652714d1f07225a5d130538e6")

# Clave del torneo en The Odds API. Si no trae partidos, corré --sports.
SPORT_KEY = "soccer_fifa_world_cup"

REGIONS = "eu,uk"          # de dónde traer casas (eu+uk cubre las europeas top)

# Casas "sharp" a promediar (las más afiladas/profesionales). El script usa SOLO
# estas; si alguna no aparece para un partido, se ignora sin romper. Dejá la
# lista vacía ([]) para promediar TODAS las casas disponibles (consenso amplio).
BOOKMAKERS = ["pinnacle", "betfair_ex_eu", "betfair_ex_uk", "onexbet"]

# Filtro por fecha. Por defecto: TODA la fase de grupos del Mundial 2026.
#   Fase de grupos: 2026-06-11 -> 2026-06-27   (DESDE 06-11, HASTA 06-28)
#   Fecha 1: 2026-06-11 -> 2026-06-17   (DESDE 06-11, HASTA 06-18)
#   Fecha 2: 2026-06-18 -> 2026-06-23   (DESDE 06-18, HASTA 06-24)
#   Fecha 3: 2026-06-24 -> 2026-06-27   (DESDE 06-24, HASTA 06-28)
DESDE = "2026-06-11"       # inclusive
HASTA = "2026-06-29"       # exclusive (cubre hasta el 28, último día de grupos)

MAX_GOLES = 8
OUT_CSV  = "predicciones.csv"
OUT_HTML = "predicciones.html"

API_BASE = "https://api.the-odds-api.com/v4"

# Cache local del dataset crudo, para no re-gastar créditos en cada corrida.
RAW_CACHE = "odds_theoddsapi_raw.json"

# Traducciones al español
ES = {
    "South Africa": "Sudáfrica", "South Korea": "Corea del Sur",
    "Czech Republic": "Rep. Checa", "Czechia": "Rep. Checa",
    "Bosnia & Herzegovina": "Bosnia", "Bosnia and Herzegovina": "Bosnia",
    "Switzerland": "Suiza", "Brazil": "Brasil", "Morocco": "Marruecos",
    "Scotland": "Escocia", "Turkey": "Turquía", "Türkiye": "Turquía",
    "Germany": "Alemania", "Netherlands": "Países Bajos", "Japan": "Japón",
    "Sweden": "Suecia", "Spain": "España", "Cape Verde": "Cabo Verde",
    "Belgium": "Bélgica", "Egypt": "Egipto", "Saudi Arabia": "Arabia Saudita",
    "Uruguay": "Uruguay", "Iran": "Irán", "New Zealand": "Nueva Zelanda",
    "France": "Francia", "Senegal": "Senegal", "Iraq": "Irak",
    "Norway": "Noruega", "Argentina": "Argentina", "Algeria": "Argelia",
    "Austria": "Austria", "Jordan": "Jordania", "Portugal": "Portugal",
    "DR Congo": "RD Congo", "England": "Inglaterra", "Croatia": "Croacia",
    "Ghana": "Ghana", "Panama": "Panamá", "Uzbekistan": "Uzbekistán",
    "Colombia": "Colombia", "Mexico": "México", "Canada": "Canadá",
    "Qatar": "Qatar", "USA": "EE.UU.", "United States": "EE.UU.",
    "Australia": "Australia", "Paraguay": "Paraguay", "Haiti": "Haití",
    "Ivory Coast": "Costa de Marfil", "Ecuador": "Ecuador", "Tunisia": "Túnez",
    "Curaçao": "Curazao", "Curacao": "Curazao",
}
def es(name): return ES.get(name, name)

# ----------------------------------------------------------------------------
# 1) BAJAR CUOTAS
# ----------------------------------------------------------------------------
def list_sports():
    r = requests.get(f"{API_BASE}/sports", params={"apiKey": API_KEY, "all": "true"}, timeout=30)
    r.raise_for_status()
    for s in r.json():
        if s.get("group") == "Soccer":
            print(f"  {s['key']:42s} {'ACTIVA' if s.get('active') else 'inactiva'}  {s['title']}")

def get_events(force_refresh=False):
    """Trae todos los partidos del torneo con mercados h2h (1X2) y totals (O/U).
    Cachea el dataset crudo: re-correr no gasta créditos salvo --refresh."""
    if os.path.exists(RAW_CACHE) and not force_refresh:
        with open(RAW_CACHE, encoding="utf-8") as f:
            return json.load(f)
    r = requests.get(
        f"{API_BASE}/sports/{SPORT_KEY}/odds",
        params={
            "apiKey": API_KEY,
            "regions": REGIONS,
            "markets": "h2h,totals",
            "oddsFormat": "decimal",
        },
        timeout=30,
    )
    r.raise_for_status()
    rem = r.headers.get("x-requests-remaining")
    used = r.headers.get("x-requests-last")
    if rem is not None:
        print(f"  (créditos: gastó {used} en esta llamada, quedan {rem} este mes)")
    data = r.json()
    with open(RAW_CACHE, "w", encoding="utf-8") as f:
        json.dump(data, f)
    return data

# ----------------------------------------------------------------------------
# 2-3) QUITAR MARGEN Y PROMEDIAR ENTRE CASAS
# ----------------------------------------------------------------------------
def devig(odds):
    """Lista de cuotas decimales -> probabilidades justas (normaliza el margen)."""
    inv = [1.0 / o for o in odds if o and o > 1.0]
    s = sum(inv)
    return [x / s for x in inv] if s > 0 else None

def parse_event(ev):
    """Devuelve (home, away, pH, pD, pA, total) promediando las casas sharp
    (BOOKMAKERS); si la lista está vacía, promedia todas. None si falta info."""
    home, away = ev["home_team"], ev["away_team"]
    probs_1x2, totals_pts = [], []

    for bk in ev.get("bookmakers", []):
        if BOOKMAKERS and bk.get("key") not in BOOKMAKERS:
            continue
        markets = {m["key"]: m for m in bk.get("markets", [])}
        h2h = markets.get("h2h")
        if h2h:
            d = {o["name"]: o["price"] for o in h2h["outcomes"]}
            if home in d and away in d and "Draw" in d:
                p = devig([d[home], d["Draw"], d[away]])
                if p:
                    probs_1x2.append(p)
        tot = markets.get("totals")
        if tot and tot["outcomes"]:
            point = tot["outcomes"][0].get("point")
            over  = next((o for o in tot["outcomes"] if o["name"] == "Over"), None)
            under = next((o for o in tot["outcomes"] if o["name"] == "Under"), None)
            if point and over and under:
                p = devig([over["price"], under["price"]])
                if p:
                    po = p[0]
                    totals_pts.append(point + (po - 0.5) * 1.6)

    if not probs_1x2:
        return None
    pH, pD, pA = np.mean(probs_1x2, axis=0)
    total = float(np.mean(totals_pts)) if totals_pts else None
    return home, away, float(pH), float(pD), float(pA), total

# ----------------------------------------------------------------------------
# 4-5) AJUSTE POISSON + MATRIZ DE MARCADORES
# ----------------------------------------------------------------------------
def poisson_pmf(k, lam):
    return math.exp(-lam) * lam**k / math.factorial(k)

def outcome_probs(lh, la, n=MAX_GOLES):
    ph = [poisson_pmf(i, lh) for i in range(n + 1)]
    pa = [poisson_pmf(j, la) for j in range(n + 1)]
    M  = np.outer(ph, pa)
    M /= M.sum()
    return np.tril(M, -1).sum(), np.trace(M), np.triu(M, 1).sum(), M

def fit_lambdas(pH, pD, pA, total):
    def loss(x):
        lh, la = x
        qH, qD, qA, _ = outcome_probs(lh, la, n=10)
        err = (qH - pH)**2 + (qD - pD)**2 + (qA - pA)**2
        if total:
            err += 0.15 * ((lh + la) - total)**2
        return err
    best, bestval = None, 1e9
    for x0 in [(1.3, 1.1), (1.8, 0.8), (0.8, 1.8), (1.0, 1.0), (2.2, 0.6)]:
        res = minimize(loss, x0, method="L-BFGS-B", bounds=[(0.05, 5.0), (0.05, 5.0)])
        if res.fun < bestval:
            bestval, best = res.fun, res.x
    return float(best[0]), float(best[1])

def _sign(x): return (x > 0) - (x < 0)

def _puntos(pi, pj, ai, aj):
    # 8: marcador exacto
    if pi == ai and pj == aj:
        return 8
    # 5: mismo ganador Y misma diferencia de goles (solo victorias, no empates).
    #    Un empate que no sea exacto NO cobra 5: cae al 3 de abajo.
    if (pi - pj) == (ai - aj) and pi != pj:
        return 5
    # 3: acertar el signo del resultado (gana local / empate / gana visitante)
    if _sign(pi - pj) == _sign(ai - aj):
        return 3
    return 0

def puntos_esperados(pi, pj, M):
    n = M.shape[0]
    ep = 0.0
    for ai in range(n):
        for aj in range(n):
            p = M[ai, aj]
            if p:
                ep += p * _puntos(pi, pj, ai, aj)
    return ep

def predict(pH, pD, pA, total):
    lh, la = fit_lambdas(pH, pD, pA, total)
    _, _, _, M = outcome_probs(lh, la)
    mi, mj = np.unravel_index(np.argmax(M), M.shape)
    best, bestEP = (int(mi), int(mj)), -1.0
    n = M.shape[0]
    for pi in range(n):
        for pj in range(n):
            ep = puntos_esperados(pi, pj, M)
            if ep > bestEP:
                bestEP, best = ep, (pi, pj)
    gi, gj = best
    return int(gi), int(gj), float(M[gi, gj]), float(bestEP), int(mi), int(mj), lh, la

# ----------------------------------------------------------------------------
# 6) LÍNEAS A JUGAR Y EXPORTAR
# ----------------------------------------------------------------------------
def underdog_pick(M, pH, pA):
    if pA >= pH:
        sub = np.tril(M, -1)
    else:
        sub = np.triu(M, 1)
    i, j = np.unravel_index(np.argmax(sub), sub.shape)
    return int(i), int(j)

def build_rows(events):
    desde = dt.date.fromisoformat(DESDE)
    hasta = dt.date.fromisoformat(HASTA)
    rows = []
    for ev in events:
        ko = ev.get("commence_time", "")
        try:
            when = dt.datetime.fromisoformat(ko.replace("Z", "+00:00"))
        except Exception:
            when = None
        if when is not None and not (desde <= when.date() < hasta):
            continue
        parsed = parse_event(ev)
        if not parsed:
            continue
        home, away, pH, pD, pA, total = parsed
        gh, ga, p_exact, ep, mi, mj, lh, la = predict(pH, pD, pA, total)
        _, _, _, M = outcome_probs(lh, la)
        ui, uj = underdog_pick(M, pH, pA)
        rows.append({
            "kickoff": when, "kickoff_raw": ko,
            "home": home, "away": away,
            "safe": f"{gh}-{ga}", "ep_safe": ep, "p_exact": p_exact,
            "risk": f"{ui}-{uj}", "ep_risk": puntos_esperados(ui, uj, M),
            "p_under": min(pH, pA),
            "pH": pH, "pD": pD, "pA": pA,
        })
    rows.sort(key=lambda r: r["kickoff_raw"])
    return rows

def make_line(rows, k):
    flip = set()
    if k > 0:
        order = sorted(range(len(rows)), key=lambda i: -rows[i]["p_under"])
        flip = set(order[:k])
    entries = []
    for i, r in enumerate(rows):
        f = i in flip
        entries.append({
            "kickoff": r["kickoff"], "kickoff_raw": r["kickoff_raw"],
            "home": r["home"], "away": r["away"],
            "score": r["risk"] if f else r["safe"],
            "ep": r["ep_risk"] if f else r["ep_safe"],
            "p_exact": r.get("p_exact", 0.0),
            "flipped": f, "pH": r["pH"], "pD": r["pD"], "pA": r["pA"],
        })
    return entries

def write_csv(entries, path):
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["Fecha/Hora (UTC)", "Local", "Visitante", "Pronostico",
                    "Jugada", "Pts esperados", "P(marcador exacto) %",
                    "P(Local) %", "P(Empate) %", "P(Visit) %"])
        for e in entries:
            w.writerow([e["kickoff_raw"], e["home"], e["away"], e["score"],
                        "Batacazo" if e["flipped"] else "Segura", f'{e["ep"]:.2f}',
                        f'{e.get("p_exact",0)*100:.0f}',
                        f'{e["pH"]*100:.0f}', f'{e["pD"]*100:.0f}', f'{e["pA"]*100:.0f}'])
    print(f"  -> {path}")

HTML_HEAD = """<!doctype html><html lang="es"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Penca Mundial 2026 — Pronósticos</title>
<style>
:root{--bordo:#6b1220;--gold:#c9a24a;--bg:#faf7f2;--ink:#23201c;--mut:#8a8278}
*{box-sizing:border-box}body{margin:0;font:16px/1.5 -apple-system,system-ui,Segoe UI,Roboto,sans-serif;background:var(--bg);color:var(--ink)}
header{background:var(--bordo);color:#fff;padding:20px 16px}
header h1{margin:0;font-size:20px}header p{margin:6px 0 0;color:#f0d9b8;font-size:13px}
.prog{max-width:760px;margin:14px auto 0;padding:0 16px}
.bar{height:8px;background:#e7e0d5;border-radius:99px;overflow:hidden}
.bar>i{display:block;height:100%;background:var(--gold);width:0}
main{max-width:760px;margin:0 auto;padding:8px 16px 60px}
h2{font-size:14px;text-transform:uppercase;letter-spacing:.06em;color:var(--bordo);margin:22px 0 8px;border-bottom:1px solid #e7e0d5;padding-bottom:6px}
.m{display:flex;align-items:center;gap:12px;padding:10px 8px;border-radius:10px}
.m:hover{background:#fff}
.m.risk{background:#fff7e6}
.m input{width:20px;height:20px;accent-color:var(--bordo);flex:none}
.tm{flex:1;min-width:0}
.tm .t{font-weight:600}.tm .s{color:var(--mut);font-size:12px}
.sc{font-weight:700;color:var(--bordo);font-size:18px;font-variant-numeric:tabular-nums;flex:none}
.m.risk .sc{color:#b9770a}
.cf{font-size:11px;color:var(--mut);flex:none;width:58px;text-align:right}
.done .tm,.done .sc{opacity:.4;text-decoration:line-through}
</style></head><body>"""

HTML_TAIL = """</main>
<script>
const PREFIX='__STOREKEY__';
const boxes=[...document.querySelectorAll('.m input')];
document.getElementById('tot').textContent=boxes.length;
function refresh(){let n=0;boxes.forEach((b,i)=>{const l=b.closest('.m');
 if(b.checked){n++;l.classList.add('done')}else{l.classList.remove('done')}});
 document.getElementById('n').textContent=n;
 document.getElementById('fill').style.width=(boxes.length? n/boxes.length*100:0)+'%'}
boxes.forEach((b,i)=>{b.checked=localStorage.getItem(PREFIX+i)==='1';
 b.addEventListener('change',()=>{localStorage.setItem(PREFIX+i,b.checked?'1':'0');refresh()})});
refresh();
</script></body></html>"""

def write_html(entries, path, subtitulo, storekey):
    by_day = {}
    for e in entries:
        d = e["kickoff"].date().isoformat() if e["kickoff"] else "Sin fecha"
        by_day.setdefault(d, []).append(e)

    parts = [HTML_HEAD,
             f'<header><h1>Penca Mundial 2026</h1><p>{html.escape(subtitulo)}</p></header>',
             '<div class="prog"><div class="bar"><i id="fill"></i></div>'
             '<div style="font-size:12px;color:var(--mut);margin-top:6px">'
             '<span id="n">0</span> de <span id="tot">0</span> cargados</div></div>',
             '<main>']

    idx = 0
    for day in sorted(by_day):
        try:
            label = dt.date.fromisoformat(day).strftime("%d/%m")
        except Exception:
            label = day
        parts.append(f'<h2>{label}</h2>')
        for e in by_day[day]:
            hh  = e["kickoff"].strftime("%H:%M UTC") if e["kickoff"] else ""
            cls = "m risk" if e["flipped"] else "m"
            mark  = "⚡ " if e["flipped"] else ""
            extra = " · batacazo" if e["flipped"] else ""
            pex = e.get("p_exact", 0) * 100
            parts.append(
                f'<label class="{cls}" data-i="{idx}">'
                f'<input type="checkbox">'
                f'<span class="tm"><span class="t">{html.escape(es(e["home"]))} '
                f'vs {html.escape(es(e["away"]))}</span>'
                f'<span class="s">{hh}{extra} · exacto ~{pex:.0f}%</span></span>'
                f'<span class="sc">{mark}{e["score"]}</span>'
                f'<span class="cf">{e["ep"]:.1f} pts</span></label>'
            )
            idx += 1

    parts.append(HTML_TAIL.replace("__STOREKEY__", storekey))
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(parts))
    print(f"  -> {path}")

# ----------------------------------------------------------------------------
def parse_k(argv):
    for i, a in enumerate(argv):
        if a.startswith("--riesgo"):
            if "=" in a:
                try: return int(a.split("=")[-1])
                except ValueError: return 5
            if i + 1 < len(argv):
                try: return int(argv[i + 1].replace("k=", ""))
                except ValueError: pass
            return 5
    return 0

def main():
    if "--sports" in sys.argv:
        list_sports(); return

    k = parse_k(sys.argv)
    force = "--refresh" in sys.argv

    print("Bajando cuotas…")
    events = get_events(force_refresh=force)
    print(f"  partidos con cuotas: {len(events)}")
    rows = build_rows(events)
    print(f"  pronósticos generados (Fecha 1): {len(rows)}")
    if not rows:
        print("  (no hay cuotas para la ventana de fechas configurada)")
        return

    segura = make_line(rows, 0)
    write_csv(segura, OUT_CSV)
    write_html(segura, OUT_HTML,
               "Cuenta A — SEGURA: marcador de máximos puntos esperados (8/5/3). "
               "Fase de grupos · cuotas casas sharp.", "penca_segura_")

    if k > 0:
        riesgo   = make_line(rows, k)
        risk_csv  = OUT_CSV.replace(".csv", "_riesgo.csv")
        risk_html = OUT_HTML.replace(".html", "_riesgo.html")
        write_csv(riesgo, risk_csv)
        write_html(riesgo, risk_html,
                   f"Cuenta B — RIESGO: igual a la segura pero con {k} batacazos. "
                   "Fase de grupos · cuotas casas sharp.", "penca_riesgo_")
        flips = [e for e in riesgo if e["flipped"]]
        print(f"\n  Línea RIESGO (cuenta B) — {k} batacazos:")
        for e in flips:
            print(f"    ⚡ {e['home']} vs {e['away']}: {e['score']} "
                  f"(P batacazo ~{min(e['pH'], e['pA'])*100:.0f}%)")

    print("\nListo. Abrí los .html en el navegador.")

if __name__ == "__main__":
    main()
