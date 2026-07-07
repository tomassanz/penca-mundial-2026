#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
puntos.py
=========
Calcula cuántos puntos llevamos en la Penca (sistema 8/5/3) comparando una
planilla de pronósticos contra los resultados REALES.

  8 = marcador exacto
  5 = mismo ganador Y misma diferencia de goles (solo victorias, no empates)
  3 = acertar quién ganó / empate
  0 = nada

Uso:
  python3 puntos.py                         # predicciones.csv vs resultados.csv
  python3 puntos.py predicciones_riesgo.csv resultados.csv
  python3 puntos.py predicciones.csv resultados.csv --fecha 1

Formato de resultados.csv (los nombres van como en la planilla, en inglés):
  Local,Visitante,GolesLocal,GolesVisitante
  Qatar,Switzerland,0,2
  Brazil,Morocco,1,1
  ...
Las filas sin goles cargados (vacías) se ignoran (partido todavía no jugado).
Hay una plantilla lista en resultados.csv para ir completando.
"""
import sys
import csv

def _sign(x): return (x > 0) - (x < 0)

def puntos(pi, pj, ai, aj):
    if pi == ai and pj == aj: return 8
    if (pi - pj) == (ai - aj) and pi != pj: return 5
    if _sign(pi - pj) == _sign(ai - aj): return 3
    return 0

def parse_marcador(s):
    a, b = s.replace(" ", "").split("-")
    return int(a), int(b)

def load_resultados(path):
    out = {}
    with open(path, encoding="utf-8") as f:
        for r in csv.DictReader(f):
            gl, gv = r.get("GolesLocal", ""), r.get("GolesVisitante", "")
            if gl.strip() == "" or gv.strip() == "":
                continue
            out[(r["Local"].strip(), r["Visitante"].strip())] = (int(gl), int(gv))
    return out

def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    pred_path = args[0] if len(args) > 0 else "predicciones.csv"
    res_path = args[1] if len(args) > 1 else "resultados.csv"
    fecha = None
    if "--fecha" in sys.argv:
        i = sys.argv.index("--fecha")
        if i + 1 < len(sys.argv):
            fecha = sys.argv[i + 1]

    # rangos de cada fecha de grupos (para el filtro --fecha)
    rangos = {"1": ("2026-06-11", "2026-06-18"),
              "2": ("2026-06-18", "2026-06-24"),
              "3": ("2026-06-24", "2026-06-29")}

    resultados = load_resultados(res_path)
    if not resultados:
        print(f"No hay resultados cargados en {res_path}. Completá los goles y volvé a correr.")
        return

    total = 0
    breakdown = {8: 0, 5: 0, 3: 0, 0: 0}
    print(f"{'PARTIDO':<40}{'PRONÓST.':<10}{'REAL':<8}{'PTS'}")
    print("-" * 64)
    jugados = 0
    with open(pred_path, encoding="utf-8") as f:
        for r in csv.DictReader(f):
            if fecha and fecha in rangos:
                d = r["Fecha/Hora (UTC)"][:10]
                if not (rangos[fecha][0] <= d < rangos[fecha][1]):
                    continue
            key = (r["Local"].strip(), r["Visitante"].strip())
            if key not in resultados:
                continue
            pi, pj = parse_marcador(r["Pronostico"])
            ai, aj = resultados[key]
            pts = puntos(pi, pj, ai, aj)
            total += pts
            breakdown[pts] += 1
            jugados += 1
            nombre = f"{r['Local']} vs {r['Visitante']}"
            print(f"{nombre:<40}{r['Pronostico']:<10}{f'{ai}-{aj}':<8}{pts}")

    print("-" * 64)
    print(f"\nPartidos puntuados: {jugados}")
    print(f"  Exactos (8): {breakdown[8]}   Dif+ganador (5): {breakdown[5]}   "
          f"Ganador (3): {breakdown[3]}   Errados (0): {breakdown[0]}")
    print(f"TOTAL: {total} puntos" + (f"  ·  promedio {total/jugados:.2f}/partido" if jugados else ""))

if __name__ == "__main__":
    main()
