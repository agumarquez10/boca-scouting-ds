# MEMORY.md — Memoria temporal del proyecto

`AGENTS.md` exige leer esta memoria al inicio y actualizarla al cierre. Máximo 50 líneas; mantener hechos vigentes, en español y con fundamentos DS/programación.

## 1. Estado actual del proyecto
- Objetivo: ranking semanal de jugadores de los TOTW de varias ligas; publicar el tweet y ampliar el sentimiento siguen pendientes.
- Modelo principal: Logistic L1 (`penalty='l1'`, `solver='saga'`, C=10, `class_weight='balanced'`), esquema de 9 features: goles, asistencias, edad y dummies de posición. Etiquetas manuales; `rating` no es feature. CV/OOF agrupado por jugador (GroupKFold) y test temporal.
- Score calibrado: `calibrador.pkl` (Platt sobre OOF por jugador) → `probabilidad_adn`. Test: Brier 0.1716→0.1595, ECE(5) 0.1071→0.0647, AUC-ROC 0.767, AUPRC 0.740; a=0.765>0 preserva el orden (se ordena por score bruto). `train_model.py` es reproducible (artefactos byte-idénticos al reentrenar) y escribe `models/evaluacion.json` (métricas, split, por clase) que la landing lee: no hay números a mano en el HTML.
- `src/scouting_pipeline.py`: semana ISO UTC → fixtures/TOTW FotMob → suma de `playerStats` por torneo de CLUB → L1 → ranking. Con `--semana YYYY-Www` reprocesa una semana cerrada (backfill).
- Ligas activas: Argentina, Brasil, Perú, Chile, Paraguay. Ecuador y Uruguay en stand by (`skip=True`); MLS quitada; México salió antes.
- **Serie W34–W43 (10 semanas)**: backfill 19/10 (W40 7 jugadores, con `--forzar`; W41 38; W42 21). W43 por corrida manual, re-corrida el 29/10 con `--forzar` (4 ligas: Argentina, Brasil, Perú, Paraguay; Chile sin TOTW; ranking 28 jugadores; sentimiento re-medido con reglas de `relevancia.py`: 5 de 9 con dato). Histórico: 187 jugadores. Sentimiento: 83 mediciones / 69 jugadores. 29/10: rankings W34–W43 recalculados con regla por ronda (`--forzar --sin-sentimiento`; respaldo en `%TEMP%\opencode\backup_pre_ronda`). Históricos midieron sentimiento de faltantes del top 3 (`barrer_semanas`, cuota no registrada). Cobertura baja: W39 1/8 con dato (solo Paraguay, gate forzado), W40 forzada con 1 liga (Argentina). W39/W40 marcadas como falta de muestra por fecha FIFA (ventana 21/09–06/10/2026, `data/semanas_sin_muestra.json`, la landing la muestra). Justificante parcial: Argentina y Paraguay sí jugaron en la ventana. Jugadores de Boca excluidos del radar (29/10, `_es_club_excluido` en `enriquecer_y_puntuar`); W37/38/40/42/43 recalculados sin ellos. Pendiente: re-medir por tandas diarias. W44 cierra el 2/11: correrla entonces.
- Caché local de FotMob (2502 entradas) tiene TOTW de ~30 semanas (Arg W04-W39, Bra W05-W38, Chi W05-W37, Per W05-W39, Par W04-W41).
- Sentimiento: `nlp_engine.py` renormaliza el ponderado sobre los componentes activos → con BERT apagado la escala real es ±50 (antes el techo era 27.5 y la landing anunciaba ±50). El léxico se indexa por token normalizado (claves con tilde ya coinciden; 'caño' estaba muerta) y se matchea por palabra completa (fin del doble conteo 'mufa'/'mufado'). BERT apagado por default. La caché guarda la columna `motor` (`vader_lexico_2`).
- Corrida semanal: `src/corrida_semanal.py` = gate (3 ligas) → ranking → sentimiento → tweet → **históricos → landing**. Es idempotente: marcador por semana en `data/estado/corrida_YYYY-Www.json` (`ranking` → `completa`); si está completa no vuelve a pegarle a FotMob, si tiene ranking retoma el tweet. Exit codes: 0 ok, 1 error, 2 sin salida, 3 parcial (`--sin-sentimiento`). Banderas: `--semana`, `--forzar`, `--sin-historicos`, `--log-dir`. Si se fuerza el gate, el marcador lleva `gate_forzado: true` (W40).
- Tests: **165 pasan** (2026-10-27; 154 el 19/10), incluido un test de integración sin red del paso de históricos. Los tests ya no escriben en `outputs/logs/` (antes lo contaminaban con 198 líneas `Liga0`).
- Landing `web/`: `src/landing_data.py` → `web/data.js` (`window.RADAR_DATA`), estática sin servidor. Escala y pesos (60/40) salen del código, no del HTML. Score/probabilidad y borrador siguen ocultos.

## 2. Decisiones tomadas y por qué
- L1 se priorizó para ranking por resultados temporales en AUPRC/top-N (puede cambiar con nueva evidencia). Platt sobre OOF por jugador corrige a la vez el sesgo de `class_weight='balanced'` y la falta de calibración; isotónica descartada por pocos datos (240 jugadores).
- Escala ±50: **renormalizar** sobre los componentes activos en vez de encender BERT (evita descargar ~500MB y multiplicar la latencia de CPU).
- Métricas de la web desde `models/evaluacion.json`: reentrenar no puede dejar la página publicando números viejos.
- Marcador por semana en vez de "re-ejecutar siempre": una tarea programada diaria no debe re-consumir cuota ni pisar una semana publicada.
- Re-medir W34–W39 con el motor nuevo en vez de reescalar: la mezcla final 60/40 entre fuentes hace que un reescale lineal no sea exacto. Costo ≈324 unidades de cuota de YouTube.
- Alinear inferencia con entrenamiento sumando todos los torneos de club: con `mainLeague` solo-liga se subestimarían a los que juegan copas. Matching de temporada tolerante al sufijo de fase.

## 3. Aprendizajes y errores a evitar
- FotMob publica el TOTW **por ronda** (~11 jugadores por ronda) y los fixtures **no traen round token** (0 de 495 en Argentina): el filtro real del pipeline es el `matchId` contra los fixtures de la semana. Una semana pasada solo tiene TOTW si alguna ronda publicada tiene partidos en ella → el gate de 3 ligas no siempre se puede cumplir hacia atrás (W40 quedó en 2). Una ronda puede cruzar el corte de lunes UTC: Argentina Ronda 14 (11 jugadores) tiene 6 partidos en W43 y 5 en W44 (domingos de noche en AR = lunes UTC); Regla desde 29/10: la unidad es la ronda; se asigna a la semana de la mayoría de sus partidos (UTC; empate → mediana), así el 11 entero queda en una semana. Las semanas ≤W42 se calcularon con la regla vieja (por partido).
- La librería `fotmob` pide un token `x-mas` a un host inalcanzable y **no cachea el fallo**: cada request perdía ~21s de timeout. `src/fotmob_api.py` parchea el cliente (fallo recordado + timeout de 25s + reintentos). Antes 21s por llamada, después 0.1–0.4s. Sin este fix ninguna corrida larga era viable.
- No usar stats actuales para backfill histórico: `playerStats` son acumulados de temporada a la fecha de hoy. En W40–W42 el desvío es de 1 a 3 semanas (aceptable, queda en `estadisticas_as_of_utc`); para ~30 semanas atrás sesgaría el ranking.
- VADER está entrenado en inglés: en español su aporte es limitado y el peso real lo carga el léxico propio de `nlp_engine.py`.
- Hang de W41 (corrida colgada ~13 min a los ~70s): **causa raíz no confirmada**. Se reprodujo un corte de ~1-2 min con el cliente viejo; con el cliente endurecido (timeouts 25s, reintentos) W40/W41/W42 completaron. No asumir que la causa era el token.
- No mezclar en un mismo diccionario `ligas_con_totw` (lista) y `n_ligas_con_totw` (conteo): el segundo pisa al primero.
- No convertir faltantes en cero, no puntuar perfiles con liga/club/temporada incompatibles. En tests, `monkeypatch.setattr(modulo, 'funcion')` no alcanza si el runner hizo `from x import funcion`.
- Nunca poner `display: flex` (o grid) sobre un `<td>`/`<th>`: meter un `div` adentro y flexear eso.

## 4. Fase 3 (validación del sentimiento) — en curso
- Hecho: textos crudos guardados (`data/sentimiento_textos_*.json`); muestra ciega de 300 (`src/etiquetado_sentimiento.py`); `etiquetado/index.html`; `src/evaluar_sentimiento.py` (exige ≥30 etiquetas). Rúbrica de tono en `data/etiquetado/rubrica.md`.
- Datasets públicos en español (TASS, InterTASS): piden firmar licencia de investigación no comercial y contraseña por email (paso del usuario); el modelo `robertuito-sentiment-analysis` se entrenó con TASS 2020 (no evaluarlo ahí) y no declara licencia. Pendiente de decisión del usuario.
- Corrección: `search.list` de YouTube cuesta 100 unidades (no ~4). La re-medición de W34–W39 pudo gastar ~7 000 unidades en un día. `buscar_videos` traga errores de cuota (un 0 puede ser cuota agotada; no verificado).
- Las cachés de la Fase 2 no tienen textos crudos; la muestra sale de una búsqueda nueva del 19/10.
- **Hallazgo 19/10**: solo 27% de los textos de prensa y 13% de YouTube mencionan el apellido (pool 1 432 → 361). No etiquetar sin filtrar: medirían relevancia, no tono. **Implementado 27/10 (código, sin re-medir ni cuota)**: `src/relevancia.py` exige mención del jugador, español y mínimo 3 textos por fuente (`MIN_TEXTOS`); nombre único exige club; se desescapa el HTML de Google News. Replay W43 con esas reglas: YouTube queda sin datos en casi todos (≤2 textos relevantes) y solo 5 de 9 jugadores tienen sentimiento. Decidir `MIN_TEXTOS` y presupuesto de búsqueda antes de re-medir. Ya aplicados a W43 (29/10). Bug corregido 29/10: `sentimiento_historico.py` contaba los `NaN` del CSV como dato (ahora `pd.notna`, con test). Tests: 166 pasan.

## 5. Próximos pasos
1. Decidir: filtro por mención (re-medición + cuota) y presupuesto de búsquedas YouTube; luego etiquetas por rúbrica (`data/etiquetado/rubrica.md`) y auditoría chica del usuario.
2. Correr `python src/evaluar_sentimiento.py` y decidir la mezcla con los números (no antes).
3. Tweet real (OAuth 1.0a, no instalado); Ecuador/Uruguay; programar la corrida semanal (hoy es manual, sin tarea en Windows).
4. Reconstruir historia profunda: contradice la regla de no backfill con stats actuales; pendiente de decisión.

## Estado Git observado
- Árbol limpio al 27/10/2026; último commit `6b416f8` (los cambios de Fase 2/3 ya están commiteados; la versión anterior de esta nota estaba obsoleta). `models/` y `data/` no se versionan.
