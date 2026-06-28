#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
regenerar.py
============
Reescribe predicciones.csv / .html (y la línea de riesgo) con la estrategia
SEGURA-VARIADA —el marcador más probable DEL FAVORITO— a partir de las
probabilidades 1X2 que ya están guardadas en predicciones.csv. No usa
numpy/scipy ni red: sirve para corregir las planillas sin volver a bajar cuotas.

Por qué existe: la línea original maximizaba puntos esperados (8/5/3) y eso
colapsa casi todo a 1-0 / 2-0. Esta versión mantiene el piso de la segura
(siempre banca al favorito, sin empates arriesgados) pero varía el marcador
según la fuerza del favorito: 1-0, 2-0, 2-1, 3-0... Da una planilla con cara
de fútbol de verdad sin resignar puntos (de hecho, en el backtest de la Fecha 1
sacó más puntos que la original).

OJO: el VOLUMEN de goles se estima desde el 1X2 con un anclaje (sin el mercado
de totales, que necesita bajar cuotas). El ganador sale del 1X2 guardado, que es
lo que más manda. Para la versión fina, re-corré penca_mundial.py (ya viene en
modo "seguro") cuando tengas red + API.

Uso:  python3 regenerar.py
"""
import csv
import math
import html
import datetime as dt

N = 8                       # goles 0..N
ANCHOR_BASE = 2.4           # goles totales esperados en un partido parejo
ANCHOR_SPREAD = 1.6         # cuánto suben los goles según lo desparejo del 1X2

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

# ---------------------------------------------------------------- modelo
def pois(k, lam): return math.exp(-lam) * lam**k / math.factorial(k)

def _tau(i, j, lh, la, rho):
    if i == 0 and j == 0: return 1.0 - lh * la * rho
    if i == 0 and j == 1: return 1.0 + lh * rho
    if i == 1 and j == 0: return 1.0 + la * rho
    if i == 1 and j == 1: return 1.0 - rho
    return 1.0

def matrix(lh, la, rho):
    ph = [pois(i, lh) for i in range(N + 1)]
    pa = [pois(j, la) for j in range(N + 1)]
    M = [[ph[i] * pa[j] for j in range(N + 1)] for i in range(N + 1)]
    for i in range(2):
        for j in range(2):
            M[i][j] = max(M[i][j] * _tau(i, j, lh, la, rho), 0.0)
    s = sum(sum(row) for row in M)
    return [[v / s for v in row] for row in M]

def outcome(M):
    h = d = a = 0.0
    for i in range(N + 1):
        for j in range(N + 1):
            if i > j: h += M[i][j]
            elif i == j: d += M[i][j]
            else: a += M[i][j]
    return h, d, a

def fit(pH, pD, pA, total):
    """Ajusta (lh, la, rho) para reproducir el 1X2, anclando el total de goles."""
    best, bv = None, 1e9
    grid = [x / 20 for x in range(4, 71)]            # 0.20 .. 3.55
    for lh in grid:
        for la in grid:
            for rho in (-0.08, 0.0, 0.08):
                h, d, a = outcome(matrix(lh, la, rho))
                e = (h - pH) ** 2 + (d - pD) ** 2 + (a - pA) ** 2 \
                    + 0.15 * ((lh + la) - total) ** 2
                if e < bv:
                    bv, best = e, (lh, la, rho)
    return best

def _puntos(pi, pj, ai, aj):
    if pi == ai and pj == aj: return 8
    if (pi - pj) == (ai - aj) and pi != pj: return 5
    s1 = (pi > pj) - (pi < pj); s2 = (ai > aj) - (ai < aj)
    return 3 if s1 == s2 else 0

def ep_de(pi, pj, M):
    return sum(M[ai][aj] * _puntos(pi, pj, ai, aj)
               for ai in range(N + 1) for aj in range(N + 1))

def mode(M):
    best, bv = (0, 0), -1.0
    for i in range(N + 1):
        for j in range(N + 1):
            if M[i][j] > bv:
                bv, best = M[i][j], (i, j)
    return best

def seguro_pick(M, pH, pA):
    """Marcador más probable DEL FAVORITO (nunca empate): banca siempre al
    favorito (mantiene el piso) pero elige el marcador según su fuerza."""
    best, bv = (0, 0), -1.0
    for i in range(N + 1):
        for j in range(N + 1):
            gana = (i > j) if pH >= pA else (j > i)
            if gana and M[i][j] > bv:
                bv, best = M[i][j], (i, j)
    return best

def underdog_pick(M, pH, pA):
    """Marcador más probable del lado del underdog (línea de batacazo)."""
    best, bv = (0, 0), -1.0
    for i in range(N + 1):
        for j in range(N + 1):
            lado = (i > j) if pA >= pH else (j > i)
            if lado and M[i][j] > bv:
                bv, best = M[i][j], (i, j)
    return best

# ---------------------------------------------------------------- carga
def load():
    rows = []
    with open("predicciones.csv", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            pH = float(r["P(Local) %"]) / 100
            pD = float(r["P(Empate) %"]) / 100
            pA = float(r["P(Visit) %"]) / 100
            tot = ANCHOR_BASE + ANCHOR_SPREAD * abs(pH - pA)
            lh, la, rho = fit(pH, pD, pA, tot)
            M = matrix(lh, la, rho)
            gi, gj = seguro_pick(M, pH, pA)
            ui, uj = underdog_pick(M, pH, pA)
            rows.append({
                "raw": r["Fecha/Hora (UTC)"], "home": r["Local"], "away": r["Visitante"],
                "safe": (gi, gj), "ep_safe": ep_de(gi, gj, M), "p_safe": M[gi][gj],
                "risk": (ui, uj), "ep_risk": ep_de(ui, uj, M), "p_risk": M[ui][uj],
                "pH": pH, "pD": pD, "pA": pA, "p_under": min(pH, pA),
            })
    rows.sort(key=lambda r: r["raw"])
    return rows

# ---------------------------------------------------------------- salida
def write_csv(rows, path, flips):
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["Fecha/Hora (UTC)", "Local", "Visitante", "Pronostico",
                    "Jugada", "Pts esperados", "P(marcador exacto) %",
                    "P(Local) %", "P(Empate) %", "P(Visit) %"])
        for i, r in enumerate(rows):
            f_ = i in flips
            sc = r["risk"] if f_ else r["safe"]
            ep = r["ep_risk"] if f_ else r["ep_safe"]
            pe = r["p_risk"] if f_ else r["p_safe"]
            w.writerow([r["raw"], r["home"], r["away"], f"{sc[0]}-{sc[1]}",
                        "Batacazo" if f_ else "Segura", f"{ep:.2f}", f"{pe*100:.0f}",
                        f'{r["pH"]*100:.0f}', f'{r["pD"]*100:.0f}', f'{r["pA"]*100:.0f}'])
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

def write_html(rows, path, subtitulo, storekey, flips):
    by_day = {}
    for i, r in enumerate(rows):
        when = dt.datetime.fromisoformat(r["raw"].replace("Z", "+00:00"))
        by_day.setdefault(when.date().isoformat(), []).append((i, r, when))
    parts = [HTML_HEAD,
             f'<header><h1>Penca Mundial 2026</h1><p>{html.escape(subtitulo)}</p></header>',
             '<div class="prog"><div class="bar"><i id="fill"></i></div>'
             '<div style="font-size:12px;color:var(--mut);margin-top:6px">'
             '<span id="n">0</span> de <span id="tot">0</span> cargados</div></div>',
             '<main>']
    idx = 0
    for day in sorted(by_day):
        label = dt.date.fromisoformat(day).strftime("%d/%m")
        parts.append(f'<h2>{label}</h2>')
        for i, r, when in by_day[day]:
            f_ = i in flips
            sc = r["risk"] if f_ else r["safe"]
            ep = r["ep_risk"] if f_ else r["ep_safe"]
            pe = (r["p_risk"] if f_ else r["p_safe"]) * 100
            hh = when.strftime("%H:%M UTC")
            cls = "m risk" if f_ else "m"
            mark = "⚡ " if f_ else ""
            extra = " · batacazo" if f_ else ""
            parts.append(
                f'<label class="{cls}" data-i="{idx}">'
                f'<input type="checkbox">'
                f'<span class="tm"><span class="t">{html.escape(es(r["home"]))} '
                f'vs {html.escape(es(r["away"]))}</span>'
                f'<span class="s">{hh}{extra} · exacto ~{pe:.0f}%</span></span>'
                f'<span class="sc">{mark}{sc[0]}-{sc[1]}</span>'
                f'<span class="cf">{ep:.1f} pts</span></label>'
            )
            idx += 1
    parts.append(HTML_TAIL.replace("__STOREKEY__", storekey))
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(parts))
    print(f"  -> {path}")

def riesgo_flips():
    """Lee qué partidos venían marcados como Batacazo en la línea de riesgo."""
    flips = set()
    try:
        base = [(r["home"], r["away"]) for r in load()]  # mismo orden
    except Exception:
        return flips
    try:
        with open("predicciones_riesgo.csv", encoding="utf-8") as f:
            risk_rows = list(csv.DictReader(f))
    except FileNotFoundError:
        return flips
    risk_bat = {(r["Local"], r["Visitante"]) for r in risk_rows
                if r["Jugada"].strip().lower() == "batacazo"}
    for i, key in enumerate(base):
        if key in risk_bat:
            flips.add(i)
    return flips

def main():
    print("Regenerando planillas con estrategia SEGURA-VARIADA (desde el 1X2 guardado)…")
    rows = load()
    from collections import Counter
    dist = Counter(f"{r['safe'][0]}-{r['safe'][1]}" for r in rows)
    write_csv(rows, "predicciones.csv", flips=set())
    write_html(rows, "predicciones.html",
               "Cuenta A — SEGURA (variada): marcador más probable del favorito. "
               "Fase de grupos · cuotas casas sharp.", "penca_segura_", flips=set())
    flips = riesgo_flips()
    if flips:
        write_csv(rows, "predicciones_riesgo.csv", flips=flips)
        write_html(rows, "predicciones_riesgo.html",
                   f"Cuenta B — RIESGO: segura + {len(flips)} batacazos. "
                   "Fase de grupos · cuotas casas sharp.", "penca_riesgo_", flips=flips)
    print("\nDistribución de marcadores (línea segura):")
    for k, v in dist.most_common():
        print(f"  {k}: {v}")
    emp = sum(v for k, v in dist.items() if k[0] == k[2])
    btts = sum(v for k, v in dist.items() if k[0] != "0" and k[2] != "0")
    print(f"  empates: {emp}/{len(rows)} · ambos marcan: {btts}/{len(rows)} "
          f"· marcadores distintos: {len(dist)}")

if __name__ == "__main__":
    main()
