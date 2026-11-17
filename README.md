# Penca Mundial 2026 — Pronósticos por cuotas

Genera tus pronósticos para la Penca a partir de las **cuotas reales de las mejores casas de apuestas**, eligiendo el marcador que **maximiza los puntos esperados** (sistema 8/5/3). Incluye una segunda línea de **riesgo** para jugar con dos cuentas y maximizar la chance de ganar pools grandes.

## Archivos

- `penca_mundial.py` — baja cuotas, calcula los pronósticos y exporta CSV + checklist HTML.
- `simulador_penca.py` — simula miles de Mundiales para decidir cuánto arriesgar según el tamaño del pool.

## Qué hace (en una línea)

Cuotas 1X2 + Over/Under → les quita el margen de la casa → ajusta un modelo de Poisson → calcula la probabilidad de cada marcador → elige el que más puntos rinde.

---

## Puesta en marcha

### 1. Dependencias
```bash
pip install requests numpy scipy
```

### 2. API key (gratis)
Sacá tu key en **https://the-odds-api.com** (plan free, 500 requests/mes — sobra).
Después, una de dos:
```bash
export ODDS_API_KEY="tu_api_key_aca"
```
o pegала directo en la variable `API_KEY` arriba de todo en `penca_mundial.py`.

### 3. Generar pronósticos

**Solo la cuenta segura (cuenta A):**
```bash
python3 penca_mundial.py
```

**Las dos cuentas a la vez (A segura + B con 5 batacazos):**
```bash
python3 penca_mundial.py --riesgo k=5
```

Genera:
| Archivo | Para qué |
|---|---|
| `predicciones.csv` / `predicciones.html` | **Cuenta A — segura** (máx. puntos esperados) |
| `predicciones_riesgo.csv` / `predicciones_riesgo.html` | **Cuenta B — riesgo** (igual a la A pero con `k` batacazos) |

Abrí los `.html` en el navegador: están agrupados por día, con el marcador y los puntos esperados de cada partido. Tildá cada uno a medida que lo cargás en la app (el progreso queda guardado aunque cierres). Los batacazos de la cuenta B salen marcados con ⚡.

---

## La estrategia de las dos cuentas

- **Cuenta A (segura):** gana los pools **chicos** (grupos de amigos), donde alcanza con un buen puntaje promedio.
- **Cuenta B (riesgo):** tu boleto para los pools **grandes/públicos**, donde para salir 1º hay que despegarse de la manada que juega a los favoritos.

No las pongas iguales: dos líneas idénticas no te dan dos chances reales. La cuenta B se desvía **solo en los partidos parejos** (los de mayor chance de batacazo), no en los favoritazos.

### ¿Cuántos batacazos (`k`)?
Corré el simulador para saberlo según tus pools:
```bash
python3 simulador_penca.py predicciones.csv
```
Te imprime la probabilidad de ganar con cuenta segura vs riesgo vs las dos, para pools de distinto tamaño, y el `k` óptimo de cada uno. Antes ajustá `CHALK_FRAC` dentro del archivo según qué tan "favoriteros" sean tus grupos (más chalk = conviene arriesgar más).

---

## Próximas fechas y eliminatorias

El script ya viene filtrado a la **Fecha 1** de grupos. Para las siguientes, editá estas dos líneas en `penca_mundial.py` (los rangos están anotados ahí mismo):
```python
DESDE = "2026-06-18"   # Fecha 2
HASTA = "2026-06-24"
```
y volvés a correr. Sirve igual para los cruces de eliminatoria: cuando las casas publiquen las cuotas, ajustás las fechas y corrés de nuevo.

> Las cuotas de las fechas 2 y 3 se afinan recién cuando se acercan los partidos, así que conviene regenerar cerca de cada fecha.

---

## Detalles y límites

- **Solo cuenta el resultado de los 90 minutos** (sin alargue ni penales), igual que las reglas de la Penca. Como la fase de grupos no tiene alargue, las cuotas 1X2 coinciden perfecto.
- Si algún partido todavía no tiene cuotas (faltan días para el debut), aparece solo cuando las casas lo abran.
- La "confianza" del marcador exacto siempre va a ser baja (~12-16%) incluso en favoritazos — es normal, el exacto es difícil; lo que manda y está alto es la probabilidad del ganador.
- Si el torneo no aparece, corré `python3 penca_mundial.py --sports` para ver la "sport key" activa y actualizá `SPORT_KEY`.

## Ajustes rápidos (en `penca_mundial.py`)

| Variable | Qué controla |
|---|---|
| `API_KEY` | tu key de The Odds API |
| `SPORT_KEY` | el torneo (`soccer_fifa_world_cup`) |
| `BOOKMAKERS` / `REGIONS` | qué casas promediar |
| `DESDE` / `HASTA` | ventana de fechas a generar |
