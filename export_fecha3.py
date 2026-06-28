#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Exporta la Fecha 3 (matchday 3) a archivos propios: línea segura + batacazos.
Reusa el modelo de regenerar.py. Fecha 3 = 24/06..28/06 UTC, sacando
Colombia-RD Congo (02:00 UTC del 24 = noche del 23 = Fecha 2)."""
import csv, datetime as dt
import regenerar as R

DESDE, HASTA = "2026-06-24", "2026-06-29"
EXCLUIR = {("Colombia", "DR Congo")}      # spillover de Fecha 2
N_BATACAZOS = 3                            # cuántos batacazos juega la cuenta B

def es_fecha3(r):
    d = r["Fecha/Hora (UTC)"][:10]
    return DESDE <= d < HASTA and (r["Local"], r["Visitante"]) not in EXCLUIR

rows = []
for r in csv.DictReader(open("predicciones.csv", encoding="utf-8")):
    if not es_fecha3(r):
        continue
    pH = float(r["P(Local) %"])/100; pD = float(r["P(Empate) %"])/100; pA = float(r["P(Visit) %"])/100
    tot = R.ANCHOR_BASE + R.ANCHOR_SPREAD*abs(pH-pA)
    lh, la, rho = R.fit(pH, pD, pA, tot); M = R.matrix(lh, la, rho)
    gi, gj = R.seguro_pick(M, pH, pA)
    ui, uj = R.underdog_pick(M, pH, pA)
    rows.append({"raw": r["Fecha/Hora (UTC)"], "home": r["Local"], "away": r["Visitante"],
                 "safe": (gi, gj), "ep_safe": R.ep_de(gi, gj, M), "p_safe": M[gi][gj],
                 "risk": (ui, uj), "ep_risk": R.ep_de(ui, uj, M), "p_risk": M[ui][uj],
                 "pH": pH, "pD": pD, "pA": pA, "p_under": min(pH, pA)})
rows.sort(key=lambda x: x["raw"])

# batacazos: los N partidos más parejos (mayor prob del underdog)
order = sorted(range(len(rows)), key=lambda i: -rows[i]["p_under"])
flips = set(order[:N_BATACAZOS])

R.write_csv(rows, "predicciones_fecha3.csv", flips=set())
R.write_html(rows, "predicciones_fecha3.html",
             "FECHA 3 — Cuenta A (segura, variada): marcador más probable del favorito.",
             "penca_f3_segura_", flips=set())
R.write_csv(rows, "predicciones_fecha3_riesgo.csv", flips=flips)
R.write_html(rows, "predicciones_fecha3_riesgo.html",
             f"FECHA 3 — Cuenta B (riesgo): segura + {N_BATACAZOS} batacazos (⚡).",
             "penca_f3_riesgo_", flips=flips)

print(f"\nFecha 3: {len(rows)} partidos")
print("Batacazos (cuenta B):")
for i in flips:
    r = rows[i]
    print(f"  ⚡ {r['home']} vs {r['away']}: {r['risk'][0]}-{r['risk'][1]} "
          f"(en vez de {r['safe'][0]}-{r['safe'][1]}; underdog ~{r['p_under']*100:.0f}%)")
