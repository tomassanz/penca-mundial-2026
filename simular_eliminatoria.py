#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
simular_eliminatoria.py
=======================
Simula los cruces de eliminatoria del Mundial 2026 cuando NO hay cuotas de
mercado (la API está cerrada). Ajusta una fuerza ATAQUE/DEFENSA por equipo a
partir de TODAS las cuotas 1X2 de la fase de grupos (predicciones.csv) y con eso
arma el 1X2 de cualquier cruce y predice el marcador a 90' (las reglas de la
penca cuentan solo los 90', sin alargue ni penales).

Estrategia de marcador: el más probable del favorito, pero si el cruce es muy
parejo y el empate a 90' es lo más probable, se juega el empate (en eliminatoria
el 1-1 a 90' es un resultado real y puntuable).
"""
import csv, math
import regenerar as R   # reusa fit/matrix/ep_de/es/HTML

N = R.N

def fit_lambdas_grupos():
    """Para cada partido de grupos, despeja (lh, la) del 1X2 guardado."""
    out = []
    for r in csv.DictReader(open("predicciones.csv", encoding="utf-8")):
        pH=float(r["P(Local) %"])/100; pD=float(r["P(Empate) %"])/100; pA=float(r["P(Visit) %"])/100
        tot = R.ANCHOR_BASE + R.ANCHOR_SPREAD*abs(pH-pA)
        lh, la, _ = R.fit(pH, pD, pA, tot)
        out.append((r["Local"], r["Visitante"], lh, la))
    return out

def ajustar_ratings(matches):
    """Gauss-Seidel sobre log-lambdas: log(lh)=H+atk[loc]-def[vis], log(la)=atk[vis]-def[loc]."""
    teams = sorted({t for m in matches for t in (m[0], m[1])})
    atk = {t: 0.0 for t in teams}; dfn = {t: 0.0 for t in teams}; H = 0.25
    for _ in range(300):
        # atk
        for t in teams:
            vals = []
            for h, a, lh, la in matches:
                if t == h: vals.append(math.log(max(lh,1e-3)) - H + dfn[a])
                if t == a: vals.append(math.log(max(la,1e-3)) + dfn[h])
            if vals: atk[t] = sum(vals)/len(vals)
        m = sum(atk.values())/len(atk)
        for t in teams: atk[t] -= m
        # def
        for t in teams:
            vals = []
            for h, a, lh, la in matches:
                if t == h: vals.append(atk[a] - math.log(max(la,1e-3)))   # rival visitante le mete la
                if t == a: vals.append(H + atk[h] - math.log(max(lh,1e-3)))
            if vals: dfn[t] = sum(vals)/len(vals)
        m = sum(dfn.values())/len(dfn)
        for t in teams: dfn[t] -= m
        # home adv
        H = sum(math.log(max(lh,1e-3)) - atk[h] + dfn[a] for h,a,lh,la in matches)/len(matches)
    return atk, dfn, H

def cruce(atk, dfn, A, B):
    """Marcador 90' de A vs B en cancha neutral.

    1) Ratings -> 1X2 del cruce (cancha neutral, sin ventaja de localía).
    2) Ese 1X2 se mete en el MISMO pipeline de grupos (anclaje de goles + Dixon-
       Coles) para que el volumen y la variedad de marcadores sean iguales.
    3) Marcador = moda; en eliminatoria SÍ se permite empate a 90' cuando el
       cruce es parejo (el 1-1 a 90' es real y puntuable), pero si hay favorito
       claro se juega su marcador más probable."""
    lA = math.exp(atk[A] - dfn[B]); lB = math.exp(atk[B] - dfn[A])
    h, d, a = R.outcome(R.matrix(lA, lB, 0.03))          # 1X2 neutral
    tot = R.ANCHOR_BASE + R.ANCHOR_SPREAD * abs(h - a)   # mismo anclaje que grupos
    lh, la, rho = R.fit(h, d, a, tot)
    M = R.matrix(lh, la, rho)
    cells = [(i,j) for i in range(N+1) for j in range(N+1)]
    mi, mj = max(cells, key=lambda ij: M[ij[0]][ij[1]])  # moda
    if mi == mj and max(h, a) - d >= 0.10:               # favorito claro: no empate
        fav_home = h >= a
        gana = [(i,j) for (i,j) in cells if (i>j if fav_home else j>i)]
        mi, mj = max(gana, key=lambda ij: M[ij[0]][ij[1]])
    return (mi, mj), (h, d, a), M[mi][mj]

CRUCES = [
    ("South Africa","Canada"),("Brazil","Japan"),("Germany","Paraguay"),
    ("Netherlands","Morocco"),("Ivory Coast","Norway"),("France","Sweden"),
    ("Mexico","Ecuador"),("England","DR Congo"),("Belgium","Senegal"),
    ("USA","Bosnia & Herzegovina"),("Spain","Austria"),("Portugal","Croatia"),
    ("Switzerland","Algeria"),("Australia","Egypt"),("Argentina","Cape Verde"),
    ("Colombia","Ghana"),
]

matches = fit_lambdas_grupos()
atk, dfn, H = ajustar_ratings(matches)

print(f"{'CRUCE (16avos)':<34}{'90min':<8}{'1X2 (T1/X/T2)':<16}{'PASA'}")
print("-"*74)
res=[]
for A,B in CRUCES:
    (mi,mj),(h,d,a),pe = cruce(atk,dfn,A,B)
    pasa = A if h>=a else B
    nota = "  (parejo→penales)" if abs(h-a)<0.08 else ""
    print(f"{R.es(A)+' vs '+R.es(B):<34}{f'{mi}-{mj}':<8}{int(h*100):>2}/{int(d*100):>2}/{int(a*100):<8} {R.es(pasa)}{nota}")
    res.append((A,B,mi,mj,h,d,a,pasa,pe))

with open("predicciones_16avos.csv","w",newline="",encoding="utf-8") as f:
    w=csv.writer(f); w.writerow(["Cruce","Pronostico 90'","P(T1)%","P(X)%","P(T2)%","P(exacto)%","Pasa (a octavos)"])
    for A,B,mi,mj,h,d,a,pasa,pe in res:
        w.writerow([f"{A} vs {B}",f"{mi}-{mj}",f"{h*100:.0f}",f"{d*100:.0f}",f"{a*100:.0f}",f"{pe*100:.0f}",pasa])
print("\n  -> predicciones_16avos.csv")

from collections import Counter
dist=Counter(f"{mi}-{mj}" for _,_,mi,mj,*_ in res)
print("Distribución:", dict(dist.most_common()))

print("\nTop 8 por fuerza (atk+def, más alto = mejor):")
for t in sorted(atk, key=lambda t: atk[t]+dfn[t], reverse=True)[:8]:
    print(f"  {R.es(t):<16} atk {atk[t]:+.2f}  def {dfn[t]:+.2f}")
