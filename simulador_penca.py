#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
simulador_penca.py
==================
Responde con NÚMEROS: ¿conviene jugar la línea segura (max puntos esperados),
una línea con varianza, o repartir entre dos cuentas (una segura + una de
riesgo)?  Y eso, ¿cómo cambia según el tamaño del pool?

Método (Montecarlo):
  - Reconstruye la distribución de marcadores de cada partido (Poisson) a partir
    de las probabilidades 1X2 que ya generó penca_mundial.py.
  - Simula miles de "Mundiales" sorteando resultados reales.
  - Modela un campo de rivales: una parte juega EXACTO los favoritos (chalk) y
    otra parte juega variado (sortea marcadores según las probabilidades).
  - Para cada estrategia mía, mide P(salir 1º) en pools de distinto tamaño.

Estrategias comparadas:
  SEGURA       -> la línea de máximos puntos esperados (penca_mundial.py)
  RIESGO(k)    -> la segura pero pateando el tablero en los k partidos con
                  mayor chance de batacazo (juega al underdog para despegarse)
  2 CUENTAS    -> P(que GANE al menos una de las dos: segura + riesgo)

Uso:
  python3 simulador_penca.py                 # corre el demo con datos sintéticos
  python3 simulador_penca.py predicciones.csv  # usa tu CSV real
"""
import sys
import csv
import numpy as np
import penca_mundial as P   # reutiliza fit_lambdas / outcome_probs / _puntos

MAXG = P.MAX_GOLES
S = MAXG + 1                      # marcadores por equipo: 0..MAXG
NCODES = S * S                    # marcadores posibles (codificados)
T = 8000                          # cantidad de Mundiales simulados
CHALK_FRAC = 0.55                 # fracción de rivales que juega solo favoritos
POOL_SIZES = [5, 20, 100, 500]
np.random.seed(7)

def code(i, j): return i * S + j
def dec(c):     return divmod(c, S)

# Tabla de puntos: L[pred_code, actual_code] -> puntos de la Penca (8/5/3/0)
L = np.zeros((NCODES, NCODES))
for c1 in range(NCODES):
    pi, pj = dec(c1)
    for c2 in range(NCODES):
        ai, aj = dec(c2)
        L[c1, c2] = P._puntos(pi, pj, ai, aj)

def matrix_from_1x2(pH, pD, pA):
    lh, la = P.fit_lambdas(pH, pD, pA, None)
    _, _, _, M = P.outcome_probs(lh, la, n=MAXG)
    return M / M.sum()

def best_score(M):
    """Marcador de máximos puntos esperados (línea SEGURA)."""
    best, bv = (0, 0), -1
    for pi in range(S):
        for pj in range(S):
            ep = (L[code(pi, pj)] * M.ravel()).sum()
            if ep > bv:
                bv, best = ep, (pi, pj)
    return best

def underdog_pick(M, pH, pA):
    """Marcador más probable del lado underdog (para la línea de RIESGO)."""
    # ¿quién es el underdog? el de menor prob de ganar
    if pA >= pH:   # el local es underdog (o parejo) -> mejor marcador con local arriba
        sub = np.tril(M, -1)
    else:          # el visitante es underdog -> marcador con visitante arriba
        sub = np.triu(M, 1)
    i, j = np.unravel_index(np.argmax(sub), sub.shape)
    return int(i), int(j)

def load_matches(path=None):
    """Devuelve lista de dicts por partido con M, código seguro, prob underdog."""
    rows = []
    if path:
        with open(path, encoding="utf-8") as f:
            for r in csv.DictReader(f):
                rows.append((float(r["P(Local) %"]) / 100,
                             float(r["P(Empate) %"]) / 100,
                             float(r["P(Visit) %"]) / 100))
    else:
        # DEMO: 24 partidos típicos de una Fecha 1 (favoritos + algunos parejos)
        favs = [(.64,.22,.14),(.40,.27,.33),(.55,.25,.20),(.58,.24,.18),
                (.30,.30,.40),(.62,.23,.15),(.18,.24,.58),(.36,.30,.34),
                (.80,.13,.07),(.52,.26,.22),(.33,.29,.38),(.43,.28,.29),
                (.85,.10,.05),(.60,.24,.16),(.12,.22,.66),(.50,.27,.23),
                (.57,.25,.18),(.20,.25,.55),(.70,.18,.12),(.48,.27,.25),
                (.66,.21,.13),(.38,.30,.32),(.74,.16,.10),(.28,.28,.44)]
        rows = favs
    out = []
    for pH, pD, pA in rows:
        M = matrix_from_1x2(pH, pD, pA)
        out.append({
            "M": M, "flat": M.ravel(),
            "safe": code(*best_score(M)),
            "risk": code(*underdog_pick(M, pH, pA)),
            "p_under": min(pH, pA),   # prob del batacazo
        })
    return out

def points_of(line_codes, actual_codes):
    """line_codes (m,), actual_codes (T,m) -> puntos por simulación (T,)."""
    pts = np.zeros(actual_codes.shape[0])
    for m, pc in enumerate(line_codes):
        pts += L[pc, actual_codes[:, m]]
    return pts

def field_points(field_codes, actual_codes):
    """field_codes (N,m), actual_codes (T,m) -> puntos (N,T)."""
    N = field_codes.shape[0]
    pts = np.zeros((N, T))
    for m in range(actual_codes.shape[1]):
        pts += L[field_codes[:, m][:, None], actual_codes[:, m][None, :]]
    return pts

def p_win(my_pts, field_pts_pool):
    """P(mi entrada supere a TODO el pool) con empates fraccionados."""
    fmax = field_pts_pool.max(axis=0)
    wins = (my_pts > fmax).astype(float)
    ties = (my_pts == fmax)
    if ties.any():
        # comparte el primer puesto con los rivales empatados
        n_tied = (field_pts_pool[:, ties] == fmax[ties]).sum(axis=0)
        wins[ties] = 1.0 / (1.0 + n_tied)
    return wins.mean()

def main():
    path = sys.argv[1] if len(sys.argv) > 1 else None
    M = load_matches(path)
    m = len(M)
    print(f"Partidos: {m}  |  Mundiales simulados: {T}  |  chalk={CHALK_FRAC:.0%}\n")

    safe = np.array([x["safe"] for x in M])
    # cantidad de batacazos para la línea de riesgo: los k partidos más "volcables"
    order = np.argsort([-x["p_under"] for x in M])   # mayor prob de batacazo primero

    # 1) sortear resultados reales de los T Mundiales
    actual = np.empty((T, m), dtype=int)
    for j, x in enumerate(M):
        actual[:, j] = np.random.choice(NCODES, size=T, p=x["flat"])

    # 2) armar el campo de rivales (máximo pool) una sola vez
    Nmax = max(POOL_SIZES)
    field = np.empty((Nmax, m), dtype=int)
    for n in range(Nmax):
        if np.random.rand() < CHALK_FRAC:
            field[n] = safe                                   # juega favoritos
        else:
            for j, x in enumerate(M):
                field[n, j] = np.random.choice(NCODES, p=x["flat"])  # variado
    fpts = field_points(field, actual)                        # (Nmax, T)

    safe_pts = points_of(safe, actual)

    # 3) elegir k* (nº de batacazos) por tamaño de pool
    print(f"{'Pool':>6} | {'SEGURA':>8} | {'RIESGO':>8} (k) | {'2 CUENTAS':>9}")
    print("-" * 48)
    for N in POOL_SIZES:
        pool = fpts[:N]
        ps = p_win(safe_pts, pool)
        # barrido de k para la línea de riesgo
        bestk, bestr, best_two = 0, -1, -1
        for k in range(0, min(12, m) + 1):
            risk = safe.copy()
            for idx in order[:k]:
                risk[idx] = M[idx]["risk"]
            rp = points_of(risk, actual)
            pr = p_win(rp, pool)
            two = p_win(np.maximum(safe_pts, rp), pool)   # gana cualquiera de las 2
            if two > best_two:
                best_two, bestr, bestk = two, pr, k
        print(f"{N:>6} | {ps*100:7.1f}% | {bestr*100:6.1f}% ({bestk:>2}) | {best_two*100:8.1f}%")

    print("\nLectura: 'k' = cuántos batacazos juega la cuenta de riesgo para ese pool.")
    print("Compará SEGURA sola vs 2 CUENTAS para ver cuánto suma separar las jugadas.")

if __name__ == "__main__":
    main()
