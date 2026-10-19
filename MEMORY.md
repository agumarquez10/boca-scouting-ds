# MEMORY.md — Memoria temporal del proyecto

`AGENTS.md` exige leer esta memoria al inicio y actualizarla al cierre. Máximo 50 líneas; mantener hechos vigentes, en español y con fundamentos DS/programación.

## 1. Estado actual del proyecto
- Objetivo: ranking semanal de jugadores de los TOTW de varias ligas; publicar el tweet y ampliar el sentimiento siguen pendientes.
- Modelo principal: Logistic L1 (`penalty='l1'`, `solver='saga'`, C=10, `class_weight='balanced'`), esquema de 9 features: goles, asistencias, edad y dummies de posición. Etiquetas manuales; `rating` no es feature. CV/OOF agrupado por jugador (GroupKFold) y test temporal.
- Score calibrado: `calibrador.pkl` (Platt sobre OOF por jugador) → `probabilidad_adn`. Test: Brier 0.1716→0.1595, ECE(5) 0.1071→0.0647, AUC-ROC 0.767, AUPRC 0.740; a=0.765>0 preserva el orden (se ordena por score bruto). `train_model.py` es reproducible (artefactos byte-idénticos al reentrenar) y escribe `models/evaluacion.json` (métricas, split, por clase) que la landing lee: no hay números a mano en el HTML.
- `src/scouting_pipeline.py`: semana ISO UTC → fixtures/TOTW FotMob → suma de `playerStats` por torneo de CLUB → L1 → ranking. Con `--semana YYYY-Www` reprocesa una semana cerrada (backfill).
- Ligas activas: Argentina, Brasil, Perú, Chile, Paraguay. Ecuador y Uruguay en stand by (`skip=True`); MLS quitada; México salió antes.
- **Serie completa W34–W42 (9 semanas)** gracias al backfill del 19/10/2026: W40 7 jugadores (2 ligas, con `--forzar` porque el gate de 3 no se puede cumplir hacia atrás), W41 38 jugadores (5 ligas), W42 21 jugadores (4 ligas). Histórico: 167 jugadores. Sentimiento: 74 mediciones / 64 jugadores, todas re-medidas con el motor nuevo.
- Caché local de FotMob (2502 entradas) tiene TOTW de ~30 semanas (Arg W04-W39, Bra W05-W38, Chi W05-W37, Per W05-W39, Par W04-W41).
- Sentimiento: `nlp_engine.py` renormaliza el ponderado sobre los componentes activos → con BERT apagado la escala real es ±50 (antes el techo era 27.5 y la landing anunciaba ±50). El léxico se indexa por token normalizado (claves con tilde ya coinciden; 'caño' estaba muerta) y se matchea por palabra completa (fin del doble conteo 'mufa'/'mufado'). BERT apagado por default. La caché guarda la columna `motor` (`vader_lexico_2`).
- Corrida semanal: `src/corrida_semanal.py` = gate (3 ligas) → ranking → sentimiento → tweet → **históricos → landing**. Es idempotente: marcador por semana en `data/estado/corrida_YYYY-Www.json` (`ranking` → `completa`); si está completa no vuelve a pegarle a FotMob, si tiene ranking retoma el tweet. Exit codes: 0 ok, 1 error, 2 sin salida, 3 parcial (`--sin-sentimiento`). Banderas: `--semana`, `--forzar`, `--sin-historicos`, `--log-dir`. Si se fuerza el gate, el marcador lleva `gate_forzado: true` (W40).
- Tests: **140 pasan** (2026-10-19), incluido un test de integración sin red del paso de históricos. Los tests ya no escriben en `outputs/logs/` (antes lo contaminaban con 198 líneas `Liga0`).
- Landing `web/`: `src/landing_data.py` → `web/data.js` (`window.RADAR_DATA`), estática sin servidor. Escala y pesos (60/40) salen del código, no del HTML. Score/probabilidad y borrador siguen ocultos.

## 2. Decisiones tomadas y por qué
- L1 se priorizó para ranking por resultados temporales en AUPRC/top-N (puede cambiar con nueva evidencia). Platt sobre OOF por jugador corrige a la vez el sesgo de `class_weight='balanced'` y la falta de calibración; isotónica descartada por pocos datos (240 jugadores).
- Escala ±50: **renormalizar** sobre los componentes activos en vez de encender BERT (evita descargar ~500MB y multiplicar la latencia de CPU).
- Métricas de la web desde `models/evaluacion.json`: reentrenar no puede dejar la página publicando números viejos.
- Marcador por semana en vez de "re-ejecutar siempre": una tarea programada diaria no debe re-consumir cuota ni pisar una semana publicada.
- Re-medir W34–W39 con el motor nuevo en vez de reescalar: la mezcla final 60/40 entre fuentes hace que un reescale lineal no sea exacto. Costo ≈324 unidades de cuota de YouTube.
- Alinear inferencia con entrenamiento sumando todos los torneos de club: con `mainLeague` solo-liga se subestimarían a los que juegan copas. Matching de temporada tolerante al sufijo de fase.

## 3. Aprendizajes y errores a evitar
- FotMob publica el TOTW **por ronda** (~11 jugadores por ronda) y los fixtures **no traen round token** (0 de 495 en Argentina): el filtro real del pipeline es el `matchId` contra los fixtures de la semana. Una semana pasada solo tiene TOTW si alguna ronda publicada tiene partidos en ella → el gate de 3 ligas no siempre se puede cumplir hacia atrás (W40 quedó en 2).
- La librería `fotmob` pide un token `x-mas` a un host inalcanzable y **no cachea el fallo**: cada request perdía ~21s de timeout. `src/fotmob_api.py` parchea el cliente (fallo recordado + timeout de 25s + reintentos). Antes 21s por llamada, después 0.1–0.4s. Sin este fix ninguna corrida larga era viable.
- No usar stats actuales para backfill histórico: `playerStats` son acumulados de temporada a la fecha de hoy. En W40–W42 el desvío es de 1 a 3 semanas (aceptable, queda en `estadisticas_as_of_utc`); para ~30 semanas atrás sesgaría el ranking.
- VADER está entrenado en inglés: en español su aporte es limitado y el peso real lo carga el léxico propio de `nlp_engine.py`.
- Hang de W41 (corrida colgada ~13 min a los ~70s): **causa raíz no confirmada**. Se reprodujo un corte de ~1-2 min con el cliente viejo; con el cliente endurecido (timeouts 25s, reintentos) W40/W41/W42 completaron. No asumir que la causa era el token.
- No mezclar en un mismo diccionario `ligas_con_totw` (lista) y `n_ligas_con_totw` (conteo): el segundo pisa al primero.
- No convertir faltantes en cero, no puntuar perfiles con liga/club/temporada incompatibles. En tests, `monkeypatch.setattr(modulo, 'funcion')` no alcanza si el runner hizo `from x import funcion`.
- Nunca poner `display: flex` (o grid) sobre un `<td>`/`<th>`: meter un `div` adentro y flexear eso.

## 4. Próximos pasos
1. **Fase 3 (aprobada)**: validar el sentimiento con etiquetas. Guardar los textos crudos por fuente (hoy la caché solo guarda el score final: cambiar el motor obliga a volver a la red); muestra de ~250-400 textos etiquetados a mano; medir VADER / léxico / BERT y las mezclas de fuente; recién ahí fijar los pesos 60/40.
2. Publicar tweet real (cada semana tiene su `data/tweet_YYYY-Www.txt`; `tweet_top5.txt` es solo la última corrida): faltan credenciales OAuth 1.0a y `requests-oauthlib` (no instalado). 
3. Re-activar Ecuador/Uruguay cuando FotMob publique TOTW; preparar la tarea programada de Windows (ya soportada por el marcador).
4. Decidir si reconstruir ~30 semanas de ranking histórico desde la caché: contradice la regla de no backfill con stats actuales.

## Estado Git observado
- El usuario commiteó la Fase 1 como `3b9a305` ("bug de sentimiento"). Sin commitear: `src/{corrida_semanal,fotmob_api,ranking_historico,scouting_pipeline,sentimiento_historico}.py`, `README.md`, `tests/test_corrida_semanal.py`, `web/data.js` y el nuevo `tests/test_fotmob_api.py`.
- `models/evaluacion.json` y `data/estado/` no se versionan (`models/` y `data/` están en `.gitignore`).
