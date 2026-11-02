# MEMORY.md — Memoria temporal del proyecto

`AGENTS.md` exige leer esta memoria al inicio y actualizarla al cierre. Máximo 50 líneas; mantener hechos vigentes, en español.

## 1. Estado actual del proyecto
- Objetivo: radar semanal de jugadores de los TOTW (FotMob) con score del modelo y sentimiento. Tweet real y ampliación del sentimiento siguen pendientes.
- Modelo: Logistic L1 (`penalty='l1'`, `solver='saga'`, C=10, `class_weight='balanced'`), 9 features (goles, asistencias, edad, dummies de posición). `rating` no es feature. CV/OOF por jugador (GroupKFold). Platt → `probabilidad_adn`. Test: AUC 0.767, AUPRC 0.740, Brier 0.172→0.160. Métricas en `models/evaluacion.json` (la landing las lee).
- Ligas activas: Argentina, Brasil, Perú, Chile, Paraguay. Ecuador y Uruguay en stand by; MLS quitada.
- Automatización (2/11/2026): tarea de Windows `BocaScoutingDiaria`, todos los días 18:00, ejecuta `src/corrida_semanal.py --diaria` (revisa las últimas 3 semanas cerradas y aplica tope de YouTube de 1000 unidades/día). Primera ejecución programada: 2/11 18:00. Con "ejecutar al perder" activado; requiere PC encendida.
- Corrida diaria: por semana, FotMob → si hay liga nueva o cambió el ranking, reescribe (`--revisar`); si no, sale sin cambios. Gate 3 ligas (exit 2 si no se cumple). Marcadores en `data/estado/corrida_YYYY-Www.json`. Cuota en `data/estado/cuota_youtube_YYYY-MM-DD.json`. Solo la última semana escribe `tweet_top5.txt`.
- Serie W34–W43 con regla por ronda (la unidad es la ronda, se asigna a la semana de la mayoría de sus partidos UTC). W39/W40 marcadas como falta de muestra por fecha FIFA (`data/semanas_sin_muestra.json`). W43 sin Chile (FotMob aún no publicó la ronda 25). W44 (cerró 2/11): solo Brasil y Paraguay publicaron → gate no cumplido, reintenta.
- Jugadores de Boca excluidos del radar (`_es_club_excluido`).
- Sentimiento: relevancia (`src/relevancia.py`: mención del jugador, español, mínimo 3 textos por fuente). Motor `vader_lexico_2`, escala ±50. Sin BERT.
- Landing `web/` estática: `src/landing_data.py` → `web/data.js`. El tweet no se publica (falta OAuth 1.0a). Tests: **193 pasan** (2026-11-02).
- Línea base (`src/linea_base.py` → `models/linea_base.json`, sin reentrenar producción): en CV repetido (20 × 5 folds, GroupKFold estratificado) la logística goles+asistencias supera al L1 de 9 features en AUPRC en 0 de 20 repeticiones (diferencia −0.011, IC95 [−0.021, −0.004]). En prueba, la diferencia es indistinguible de cero (IC95 incluye 0). Landing muestra ambas. Los tests tienen clave de YouTube vacía (fixture en `tests/conftest.py`).

## 2. Decisiones tomadas y por qué
- Corrida diaria y no semanal: idempotente, así que reintentar es barato; FotMob publica con atraso.
- Revisar 3 semanas: cierra ligas tardías y correcciones de cálculo (ej. Chile de W43).
- Tope de YouTube por día (1000) y no solo por corrida: una corrida manual extra el mismo día no puede exceder el tope. Búsqueda = 100 unidades, comentarios = 1.
- Jugador pendiente por cuota: no se cachea como "sin datos", así la siguiente corrida lo reintenta.
- Solo la última semana escribe el tweet principal: las revisiones de semanas viejas no lo pisan.
- Renormalizar la escala sobre componentes activos en vez de encender BERT (evita ~500MB y latencia).
- Marcador por semana: una tarea diaria no re-consume cuota ni pisa una semana publicada sin motivo.

## 3. Aprendizajes y errores a evitar
- FotMob publica TOTW por ronda (~11 jugadores) y los fixtures no traen round token: el filtro es el `matchId`.
- El token `x-mas` de la librería `fotmob` falla sin cachear (21 s por request). `src/fotmob_api.py` lo parchea (timeout 25 s, reintentos).
- No usar stats actuales para backfill histórico: son acumulados a la fecha de hoy.
- YouTube `search.list` cuesta 100 unidades. Antes `buscar_videos` tragaba el error de cuota; ahora marca la cuota agotada.
- Los `NaN` del CSV no son `None`: contar datos con `pd.notna` (bug corregido en históricos y tweet).
- No mezclar `ligas_con_totw` (lista) y `n_ligas_con_totw` (conteo) en un mismo dict.
- No convertir faltantes en cero. En tests, `monkeypatch` debe apuntar al módulo donde se usa el nombre.
- Los tests que llegan a la medición de sentimiento pueden consultar YouTube si hay clave: el fixture de `conftest.py` la anula. Antes de esto, corridas de test pudieron gastar cuota real (no cuantificado).
- Nunca `display: flex` sobre un `<td>`/`<th>`.
- Herramienta de shell: cualquier código de salida distinto de 0 se muestra como "Exited with code 1".

## 4. Fase 3 (validación del sentimiento) — en curso
- Hallazgo 19/10: solo 27% de textos de prensa y 13% de YouTube mencionan al jugador. Filtro aplicado en código (27/10), sin re-medir todavía.
- Con el filtro y mínimo 3 textos, W43 queda con 5 de 9 jugadores con dato. Decidir `MIN_TEXTOS` (3 o 2) y presupuesto antes de re-medir.
- Datasets TASS/InterTASS: piden licencia y contraseña (paso del usuario). `robertuito` se entrenó con TASS: no evaluarlo ahí.
- Etiquetas: `data/etiquetado/rubrica.md`; evaluación con `src/evaluar_sentimiento.py` (≥30 etiquetas).

## 5. Próximos pasos
1. Verificar la primera corrida programada (2/11 18:00) en `outputs/logs/corrida_semanal.log`. Commit manual de `web/` (Vercel publica desde GitHub).
1b. Decisión pendiente: el modelo no supera a goles+asistencias en CV. Opciones: más datos, simplificar, o justificar con otro criterio.
1c. Conflicto: AGENTS.md pide "sin warnings" y `penalty='l1'` está deprecado en sklearn 1.8 (warning en train_model y linea_base). Decidir si migrar a `l1_ratio=1`.
2. Re-medir sentimiento por tandas diarias (decidir `MIN_TEXTOS` antes).
3. Agregar ligas (Chile cuando publique W43; Ecuador/Uruguay en stand by) con consulta de solo lectura antes de activar.
4. Tweet real (OAuth 1.0a) y publicación de la landing (no hay hosting definido).
5. Fase 3: etiquetado y decisión de la mezcla de pesos.

## Estado Git observado
- Commits de Fase 2/3 ya están en `6b416f8`. Cambios de automatización y filtro por ronda/cuota sin commitear al 2/11. `models/` y `data/` no se versionan.
