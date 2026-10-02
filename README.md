# Scouting & Hype Boca Juniors

Radar semanal de jugadores destacados en los equipos de la fecha de varias
ligas. La L1 ordena qué perfiles se parecen más a las etiquetas manuales de
ADN Boca; el siguiente objetivo es sumar sentimiento real y publicar el top 5.

## Arquitectura

```
FotMob Team of the Week + fixtures ─┐
FotMob playerStats (todos los torneos de club)├─► scouting_pipeline.py ─► ranking_jugadores_fecha_YYYY-Www.csv
modelo L1 + scaler + encoder ─────────┘                                  │
                                                                           └─► corrida_semanal.py ─┬─► sentiment_radar.py ─► tweet_top5.txt (borrador)
                                                        (gate de 3 ligas)    └─► landing_data.py ─► web/data.js
```

## Página del radar (`web/`)

`src/landing_data.py` arma `web/data.js` (un global `window.RADAR_DATA`) con los
rankings semanales, el sentimiento ya cacheado, el histórico consolidado y los
metadatos del modelo. Es una lectura de los CSV y de `models/`: no consulta la
API ni recalcula el modelo. La página (`web/index.html` + `styles.css` + `app.js`)
es estática y se abre con doble click, sin servidor ni build.

Muestra la planilla de la semana (top 5 ordenados por el score del modelo, con
selector de semana), el corte por puesto y el top 5 de reacción de la hinchada. A
pedido del usuario la página **no muestra el score ni la probabilidad
calibrada** (el orden viene del modelo pero el número no se publica, y `data.js`
ni siquiera lo exporta), ni la tabla histórica completa de apariciones en el top
5, ni el texto del tweet, ni las deudas.

El corte por puesto son los tres grupos DEL/MED/DEF con sus tres candidatos, el
mismo `seleccionar_por_puesto` que usa `automatizacion` para componer el tweet:
la página muestra los nueve nombres con club y G+A, y el sentimiento si está
cacheado para esa semana, pero no el texto del tweet. Debajo va un cuarto cuadro
`SENT` con el top 3 por sentimiento entre esos nueve (`top_por_sentimiento`, el
mismo criterio que la línea SENT del tweet). El cuadro SENT siempre reserva los
tres lugares: sin `sentimiento_radar_YYYY-Www.csv` para esa semana muestra
"sin datos de sentimiento", nunca 0, y se completa solo en la próxima corrida
(`corrida_semanal.py` regenera la landing).

La sección **La reacción de la hinchada** lee lo que deja
`sentimiento_historico.py` (`data/sentimiento_historico.csv` y su consolidado),
sin recalcular nada: la cobertura en una cinta y una tabla con el **top 5** de
los 44 jugadores medidos (en el orden del consolidado: pico y después media), con
la reacción media en barra divergente (cero al centro, jade arriba / sirena
abajo), semanas medidas, pico, piso y con qué fuentes se midió. Pico y piso quedan
vacíos cuando el jugador tiene una sola medición, porque con un dato no hay
rango. El desglose por jugador (prensa y/o YouTube) queda como tooltip en el
valor de los cuadros por puesto. Ojo con el límite metodológico: el sentimiento
se consulta el día que corre el script, no en la fecha de la semana, así que
mide cómo se menciona hoy a los jugadores de aquel equipo de la fecha.

`web/data.js` sigue exportando el histórico completo de apariciones aunque la
página no lo muestre, porque `corrida_semanal.py` lo lee en su log
(`len(datos["historico"])`). Para sacarlo del bundle hay que cambiar esa línea
primero. Los borradores se recomponen con `automatizacion.componer_tweet` sobre
los rankings guardados: solo el sentimiento que está cacheado para esa semana
(`sentimiento_radar_YYYY-Www.csv`) entra al texto, y lo que falta se muestra como
"sin sentimiento medido".

Los prototipos `scouting_mercado.py`, `ranking_acumulado.py` y `semanal.py`
conservan un flujo histórico de mercado con filtros/deduplicación distintos; no
se usan para el nuevo radar TOTW.

## Cómo correr

```powershell
# 1. Entrenar / re-entrenar el modelo (genera models/*.pkl y scouting_resultado_historico.csv)
python src/train_model.py

# 2. Radar de equipos de la fecha (semana ISO completa anterior, UTC)
python src/scouting_pipeline.py

# 3. Ranking histórico acumulado (apariciones en el top 5 de los rankings semanales)
python src/ranking_historico.py

# 4. Automatización semanal: corre el radar, arma el top 3 por puesto
#    (DEL/MED/DEF) + top 3 por sentimiento (hinchada+medios) y escribe el
#    borrador en data/tweet_top5.txt (no publica)
python src/automatizacion.py

# 5. Refrescar la página del radar (lee los CSV y escribe web/data.js)
python src/landing_data.py
```

El pipeline semanal no requiere `API_KEY`: refresca fixtures/TOTW y perfiles
FotMob, actualiza la caché `api_cache` de SQLite y guarda el ranking y un CSV
separado de jugadores no resueltos. Las features se alinean con el alcance del
entrenamiento (que incluye copas/continental): se suman goles/asistencias de
todos los torneos de CLUB de la temporada vía `playerStats`, validando ID, club,
liga y temporada del TOTW (matching tolerante al sufijo de fase, p. ej.
`2026/2027 - Apertura`). Los torneos de selecciones se excluyen por heurística
de nombre; si un torneo club no reporta goles/asistencias, el jugador queda sin
score. `torneos_sin_matches` marca torneos sin reporte de partidos (auditoría,
no es feature). Si hay fixtures en la semana pero el TOTW aún no está publicado,
el pipeline lo informa como aviso. Ligas activas: Argentina, Brasil, Perú,
Chile y Paraguay; Ecuador y Uruguay en stand by (FotMob no publica TOTW para
esas ligas: el endpoint de rounds devuelve `null`) y MLS quitada a pedido del
usuario. Validación live de la semana 21–28/09/2026: Argentina y Perú puntuaron
2+2; Paraguay 2; Brasil y Chile en parón de liga. No hacer backfill con perfiles
actuales para fechas históricas: sus totales pueden incluir partidos posteriores
a esa fecha.

### Ranking histórico
`src/ranking_historico.py` consolida los `ranking_jugadores_fecha_*.csv` por
`player_id_fotmob` y guarda `data/ranking_historico_acumulado.csv`. Reporta
`apariciones_top5`, `semanas_en_ranking`, `mejor_posicion`, `score_max/medio` y
`tasa_top5` (apariciones / semanas en que la liga principal del jugador tuvo
TOTW). La tasa normaliza el sesgo de volumen de Brasil. Los goles/asistencias
son acumulados de temporada y se toman de la última aparición, no se suman
entre semanas.

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
   `features_list.pkl`, `position_encoder.pkl`, `config.pkl`, `calibrador.pkl`),
   nunca recalcula.
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
los resultados orientan la elección, no garantizan el rendimiento futuro. El
score se usa para ordenar este universo seleccionado por TOTW; no es una
probabilidad calibrada para todo el mercado.

### Probabilidad calibrada (`probabilidad_adn`)
La salida del modelo está reponderada por `class_weight='balanced'` y nunca se
había calibrado. Se aplica un calibrador **Platt** (sigmoid) ajustado sobre el
OOF por jugador y guardado en `models/calibrador.pkl` (`src/calibracion.py`).
En test: **Brier 0.1716 → 0.1595** y **ECE(5) 0.1071 → 0.0647**. Interpretación:
P(etiqueta manual = ADN Boca | features) bajo la distribución de entrenamiento;
sobre TOTW es una extrapolación (no hay etiquetas de verificación allí). El
ranking sigue ordenándose por el score bruto: Platt con pendiente `a>0` es
monotónico y no cambia el orden. La columna aparece en
`scouting_resultado_historico.csv` y en el próximo CSV semanal.

## Datos

| Archivo | Descripción |
|---|---|
| `data/adn_boca_real.csv` | Raw etiquetado (con rating, 795 filas) |
| `data/adn_boca_real_features.csv` | Features sin rating (795×14, fuente de entrenamiento) |
| `data/scouting_resultado_historico.csv` | Predicciones del modelo (OOF en train, test directo; con `probabilidad_adn` calibrada) |
| `data/ranking_jugadores_fecha_YYYY-Www.csv` | Ranking semanal nuevo, una fila por jugador, con score y captura de stats |
| `data/jugadores_fecha_no_resueltos_YYYY-Www.csv` | TOTW sin cruce/estadísticas completas; no se puntúan |
| `data/ranking_historico_acumulado.csv` | Apariciones en el top 5 agregadas por jugador sobre todos los rankings semanales |
| `data/sentimiento_radar_YYYY-Www.csv` | Sentimiento por jugador del tweet (YouTube + prensa) con caché semanal |
| `data/sentimiento_historico.csv` | Sentimiento del corte por puesto en todas las semanas registradas |
| `web/data.js` | Datos de la página del radar, generados por `src/landing_data.py` |
| `data/scouting_resultado.csv` | Ranking antiguo de mercado; no lo genera el radar semanal |
| `data/sentimiento_hinchada.csv` | Comentarios + VADER compound + clasificación |
| `data/boca_juniors.db` | `candidatos_mercado`, `scouting_resultado`, `adn_boca`, ... |

Credenciales en `secrets/.env` (no versionado; ver `.env.example`).

## Estado y deudas técnicas

- [x] EDA con esquema nuevo (incl. correlaciones por posición)
- [x] Esquema de 9 features y validación temporal por jugador de L1/RF
- [x] MVP offline del radar semanal TOTW → stats por torneo FotMob (todas las competiciones de club) → ranking del modelo
- [x] Calibración Platt del score (`probabilidad_adn`) validada con Brier/ECE por jugador
- [x] Validación live de cobertura: Argentina, Perú y Paraguay puntuaron; Brasil/Chile en parón; Uruguay sin TOTW
- [x] Ranking histórico acumulado de apariciones en el top 5 (`ranking_historico.py`)
- [ ] Re-activar Ecuador y Uruguay (stand by en `ligas.py`) cuando FotMob publique su TOTW; re-validar Chile cuando haya fechas
- [x] NLP de sentimiento con fallback a placeholders
- [x] Automatización semanal conectada al radar TOTW (top 3 por puesto → borrador de tweet)
- [ ] Revocar credenciales antiguas que quedaron en el historial git (la clave actual ya está configurada)
- [ ] Activar scrape real de Reddit (app tipo *script*; hoy 401 → placeholders)
- [ ] Publicar tweet real (faltan credenciales OAuth 1.0a y `requests-oauthlib`;
      hoy se escribe `data/tweet_top5.txt`)
- [x] Sentimiento por jugador del TOTW (YouTube + prensa multi-medio, prioridad a medios) para el top 3 del tweet

### Sentimiento (límites)
VADER está entrenado en inglés; se aplica un lexicón mínimo español-futbolero
en `src/sentimiento_hinchada.ipynb`. Mejorar con un modelo de español cuando
haya datos reales.

## Corrida semanal (`src/corrida_semanal.py`)

Punto de entrada de la semana. Encadena radar TOTW → gate → ranking → sentimiento →
borrador de tweet → refresh de la landing, y aplica un **gate de cobertura**: solo
genera la salida si al menos **3 ligas** publicaron TOTW de verdad en la semana.

Que una liga tenga fixtures en el semana no cuenta: si el TOTW todavía no está
publicado (FotMob publica la fecha con días de atraso) la liga se cuenta como
`sin TOTW`. Si el gate no se cumple **no se escribe nada** (ni ranking, ni tweet, ni
`web/data.js`): la corrida anterior queda intacta y el siguiente intento reevalúa la
misma semana, así que conviene correrlo más de una vez por semana.

```powershell
python src/corrida_semanal.py                    # corrida normal
python src/corrida_semanal.py --min-ligas 4       # gate más exigente
python src/corrida_semanal.py --forzar            # ignora el gate
python src/corrida_semanal.py --sin-sentimiento   # solo ranking, no consume cuota de YouTube
```

Códigos de salida: `0` corrida completa · `2` no se produjo salida (gate no cumplido o
sin jugadores puntuables) · `1` error inesperado. Log rotativo en
`outputs/logs/corrida_semanal.log`.

## Automatización semanal (Windows Task Scheduler)

No hay tarea creada: se corre a mano con el comando de arriba. Si más adelante se
quiere programar, se apunta el Programador de tareas a `src/corrida_semanal.py`
conviene con **varios intentos por semana** (p. ej. martes, jueves y sábado) para
absorber la latencia de publicación de FotMob:

```powershell
schtasks /Create /SC WEEKLY /D TUE,THU,SAT /ST 08:00 /TN "BocaScouting" /TR "C:\Users\Agu\Desktop\boca-scouting-ds\venv\Scripts\python.exe C:\Users\Agu\Desktop\boca-scouting-ds\src\corrida_semanal.py"
```

El borrador queda en `data/tweet_top5.txt` y la página se regenera; no publica en
Twitter (esa integración está pendiente).

## Tests

```powershell
python -m pytest tests -q
```

Cubren reglas del modelo y casos offline del radar: semana/round, cruce estricto
de jugador, deduplicación semanal y rechazo de features faltantes.
