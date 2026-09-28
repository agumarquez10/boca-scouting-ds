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

Los notebooks activos se ejecutan con kernel Python 3 desde Jupyter (`python -m
jupyter notebook`). `src/model_training.ipynb` es legado: no ejecutarlo para
entrenar ni generar artefactos; usar `src/train_model.py`.

## Reglas de Data Science (obligatorias)

1. **Etiqueta**: criterio manual del usuario (prioridad a las correcciones de
   `data/etiquetas_manuales.csv`), no la fórmula histórica. `rating` y derivados
   NUNCA son features.
2. **Split por jugador** (no por fila): `temporada >= 2023` → test. CV y OOF
   también por jugador (GroupKFold): sin GroupKFold el OOF se infla ~+0.03.
3. Desbalance ~2.4:1 → `class_weight='balanced'`; reportar precision/recall/F1,
   AUC-ROC y AUPRC (para ranking), no solo accuracy.
4. Los outliers (goles/asistencias) son leyendas: NO se eliminan.
5. Sin features con `|r| > 0.8` entre sí.
6. La inferencia SIEMPRE usa los pkl (`modelo_adn_boca.pkl`, `scaler.pkl`,
   `features_list.pkl`, `position_encoder.pkl`, `config.pkl`), nunca recalcula.
7. `penalty='l1'` requiere `solver='saga'` (sin `l1_ratio`).

## Features del modelo (esquema 9)

`goles`, `asistencias`, `edad` + 6 dummies de posición (`position_encoder.pkl`).
Son 9 features; `rating` queda fuera porque no hay un valor comparable para los
candidatos del mercado. La etiqueta es manual, por eso goles/asistencias no
codifican una fórmula determinista de la etiqueta.

Se seleccionó Logistic L1 (`penalty='l1'`, `solver='saga'`) para el ranking.
La selección de `C` usa AUPRC con GroupKFold por jugador y el escalador se ajusta
dentro de cada fold. Validación temporal por snapshots recientes (una fila por
jugador):

| Última temporada del jugador | Jugadores (+) | L1 AUPRC | L1 AUC-ROC | Precisión top-10 |
|---|---:|---:|---:|---:|
| 2015–2019 | 38 (14) | 0.695 | 0.769 | 6/10 |
| 2020–2022 | 37 (10) | 0.731 | 0.791 | 7/10 |
| 2023–2024 | 50 (12) | 0.736 | 0.854 | 7/10 |

La prevalencia de cada bloque (0.368, 0.270 y 0.240) es su baseline de AUPRC.
El RF queda como comparador: lideró en los bloques antiguos, pero bajó a AUPRC
0.643 y precisión top-10 5/10 en 2023–2024. Las cohortes son pequeñas, así que
los resultados orientan la elección, no garantizan el rendimiento futuro.

## Datos

| Archivo | Descripción |
|---|---|
| `data/adn_boca_real.csv` | Raw etiquetado (con rating, 795 filas) |
| `data/adn_boca_real_features.csv` | Features sin rating (795×14, fuente de entrenamiento) |
| `data/scouting_resultado_historico.csv` | Predicciones del modelo (OOF en train, test directo) |
| `data/scouting_resultado.csv` | **Ranking semanal de candidatos** (salida del pipeline) |
| `data/sentimiento_hinchada.csv` | Comentarios + VADER compound + clasificación |
| `data/boca_juniors.db` | `candidatos_mercado`, `scouting_resultado`, `adn_boca`, ... |

Credenciales en `secrets/.env` (no versionado; ver `.env.example`).

## Estado y deudas técnicas

- [x] EDA con esquema nuevo (incl. correlaciones por posición)
- [x] Esquema de 9 features y validación temporal por jugador de L1/RF
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
