# Scouting & Hype Boca Juniors

Sistema de Data Science para identificar fichajes con "ADN Boca" y medir el
sentimiento de la hinchada. Produce un ranking semanal de candidatos del
mercado y un tweet con el top 5.

## Pipeline

```
candidatos_mercado (API Football) ─┐
                                  ├─► scouting_pipeline.py ─► scouting_resultado.csv ─┐
modelo_adn_boca.pkl + scaler +      │                                                  ├─► automatizacion.py ─► tweet top-5
position_encoder (models/*.pkl)     │                                                  │
                                   ▼                                                  │
Reddit (praw + VADER) ─► sentimiento_hinchada.ipynb ─► sentimiento_hinchada.csv ───────┘
```

## Cómo correr

```powershell
# 1. Entrenar / re-entrenar el modelo (genera models/*.pkl y scouting_resultado_historico.csv)
python src/train_model.py

# 2. Scouting de candidatos (ranking + tabla SQLite)
python src/scouting_pipeline.py

# 3. Automatización semanal completa (scouting + sentimiento + tweet)
python src/automatizacion.py
```

Los notebooks (`src/eda.ipynb`, `src/model_training.ipynb`, etc.) se ejecutan
con kernel Python 3 desde Jupyter (`python -m jupyter notebook`).

## Reglas de Data Science (obligatorias)

1. **Etiqueta**: `(rating >= 7.0) & (goles + asistencias >= 3)`. `rating` y
   derivados NUNCA son features.
2. **Split por jugador** (no por fila): `temporada >= 2023` → test.
3. Desbalance 4.2:1 → `class_weight='balanced'`; reportar precision/recall/F1 y
   AUC-ROC, no solo accuracy.
4. Los outliers (goles/asistencias) son leyendas: NO se eliminan.
5. Sin features con `|r| > 0.8` entre sí.
6. La inferencia SIEMPRE usa los pkl (`modelo_adn_boca.pkl`, `scaler.pkl`,
   `features_list.pkl`, `position_encoder.pkl`, `config.pkl`), nunca recalcula.
7. `penalty='l1'` requiere `solver='saga'` (sin `l1_ratio`).

## Features del modelo (perfil puro)

`pases_precisos`, `edad`, `temporadas_en_dataset`, `partidos_por_temporada`,
`perfil_ofensivo` + 6 dummies de posición (`position_encoder.pkl`). Son 11
features; quedan descartados goles/asistencias/rating y pares colineales
(`edad` vs `edad_primer_registro`, `experiencia` vs `temporadas_en_dataset`).

Resultado (LogisticRegression balanceada, C=10): **AUC-ROC test 0.887**,
OOF 0.930. Alternativas: `modelo_logistic_l1.pkl` (L1, saga, AUC 0.866) y
`modelo_random_forest.pkl` (RandomForest, AUC 0.881).

## Datos

| Archivo | Descripción |
|---|---|
| `data/adn_boca_real.csv` | Raw etiquetado (con rating, 810 filas) |
| `data/adn_boca_real_features.csv` | Features sin rating (fuente de entrenamiento) |
| `data/scouting_resultado_historico.csv` | Predicciones del modelo (OOF en train, test directo) |
| `data/scouting_resultado.csv` | **Ranking semanal de candidatos** (salida del pipeline) |
| `data/sentimiento_hinchada.csv` | Comentarios + VADER compound + clasificación |
| `data/boca_juniors.db` | `candidatos_mercado`, `scouting_resultado`, `adn_boca`, ... |

Credenciales en `secrets/.env` (no versionado; ver `.env.example`).

## Estado y deudas técnicas

- [x] EDA con esquema nuevo (incl. correlaciones por posición)
- [x] Modelo de perfil puro + L1 corregido + RandomForest
- [x] Pipeline de scouting sobre `candidatos_mercado`
- [x] NLP de sentimiento con fallback a placeholders
- [x] Automatización local (script + Task Scheduler)
- [ ] Refrescar `candidatos_mercado` por API (API_KEY vacía — **rotar keys**:
      quedaron en el historial git)
- [ ] Activar scrape real de Reddit (app tipo *script*; hoy 401 → placeholders)
- [ ] Publicar tweet real (faltan credenciales OAuth 1.0a; hoy se escribe
      `data/tweet_top5.txt`)

### Sentimiento (límites)
VADER está entrenado en inglés; se aplica un lexicón mínimo español-futbolero
en `src/sentimiento_hinchada.ipynb`. Mejorar con un modelo de español cuando
haya datos reales.

## Automatización semanal (Windows Task Scheduler)

Crear una tarea que ejecute `src/automatizacion.py` (probablemente con
`python.exe` de Anaconda base) cada lunes:

```powershell
schtasks /Create /SC WEEKLY /D MON /ST 09:00 /TN "BocaScouting" /TR "C:\Users\Agu\Desktop\boca-scouting-ds\venv\Scripts\python.exe C:\Users\Agu\Desktop\boca-scouting-ds\src\automatizacion.py"
```

## Tests

```powershell
python -m pytest tests -q
```

Cubren: rating fuera de features, definición de etiqueta, split por jugador,
multicolinealidad, pkls cargables, consistencia config/features, ranking y
histórico válidos.
