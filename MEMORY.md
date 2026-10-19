# MEMORY.md — Memoria temporal del proyecto

`AGENTS.md` exige leer esta memoria al inicio y actualizarla al cierre. Máximo 50 líneas; mantener hechos vigentes, en español y con fundamentos DS/programación.

## 1. Estado actual del proyecto
- Objetivo: ranking semanal de jugadores de los TOTW de varias ligas; publicar el tweet y ampliar el sentimiento siguen pendientes.
- Modelo principal: Logistic L1 (`penalty='l1'`, `solver='saga'`, C=10, `class_weight='balanced'`), esquema de 9 features: goles, asistencias, edad y dummies de posición. Etiquetas manuales; `rating` no es feature. CV/OOF agrupado por jugador (GroupKFold) y test temporal.
- Score calibrado: `calibrador.pkl` (Platt sobre OOF por jugador) → `probabilidad_adn`. Test: Brier 0.1716→0.1595, ECE(5) 0.1071→0.0647, AUC-ROC 0.767, AUPRC 0.740; a=0.765>0 preserva el orden (se ordena por score bruto).
- `train_model.py` es reproducible: reentrenado 2026-10-19 dio artefactos **byte-idénticos** al modelo anterior (random_state=42 fija saga). Escribió `models/evaluacion.json` (métricas, split, por clase); la landing las lee, ya no hay literales en el HTML.
- `src/scouting_pipeline.py`: semana ISO UTC → fixtures/TOTW FotMob → suma de `playerStats` por torneo de CLUB → L1 → ranking. Nota: el entrenamiento incluye copas, la inferencia suma todos los torneos de club.
- Ligas activas: Argentina, Brasil, Perú, Chile, Paraguay. Ecuador y Uruguay en stand by (`skip=True`); MLS quitada; México salió antes.
- **Hueco de 3 semanas**: datos hasta W39 (cierre 28/09); hoy la última semana cerrada es W42 → faltan W40, W41, W42. `ultimo_bloque_semanal_completo()` siempre devuelve la última cerrada, así que el runner actual no puede recuperar las anteriores (no hay `--semana` todavía).
- Caché local de FotMob (2502 entradas) tiene TOTW de ~30 semanas (Arg W04-W39, Bra W05-W38, Chi W05-W37, Per W05-W39, Par W04-W41). Paraguay W41 ya tiene 6 jugadores cacheados.
- Sentimiento: `nlp_engine.py` renormaliza el ponderado sobre los componentes activos → con BERT apagado la escala real es ±50 (antes el techo era 27.5 y la landing anunciaba ±50). El léxico se indexa por token normalizado (claves con tilde ya coinciden; 'caño' estaba muerta) y se matchea por palabra completa (fin del doble conteo 'mufa'/'mufado'). BERT queda apagado por default. La caché guarda la columna `motor` (`vader_lexico_2`).
- Corrida semanal: `src/corrida_semanal.py` = gate (3 ligas) → ranking → sentimiento → tweet → landing. Es idempotente: marcador por semana en `data/estado/corrida_YYYY-Www.json` (`ranking` → `completa`); si está completa no vuelve a pegarle a FotMob, si tiene ranking retoma el tweet. Exit codes: 0 ok, 1 error, 2 sin salida, 3 parcial (`--sin-sentimiento`). `--log-dir` permite aislar el log.
- Tests: **122 pasan** (2026-10-19). Los tests ya no escriben en `outputs/logs/` (antes lo contaminaban con 198 líneas `Liga0`).
- Landing `web/`: `src/landing_data.py` → `web/data.js` (`window.RADAR_DATA`), estática sin servidor. Muestra planilla semanal, corte por puesto, top por sentimiento, ranking histórico (116 jugadores) y el pulso de las menciones. Escala y pesos (60/40) salen del código, no del HTML. Score/probabilidad y borrador siguen ocultos.

## 2. Decisiones tomadas y por qué
- L1 se priorizó para ranking por resultados temporales en AUPRC/top-N (puede cambiar con nueva evidencia). Platt sobre OOF por jugador corrige a la vez el sesgo de `class_weight='balanced'` y la falta de calibración; isotónica descartada por pocos datos (240 jugadores).
- Escala ±50: **renormalizar** sobre los componentes activos en vez de encender BERT (evita descargar ~500MB y multiplicar la latencia de CPU en la corrida semanal).
- Métricas de la web desde `models/evaluacion.json`: reentrenar no puede dejar la página publicando números viejos.
- Marcador por semana en vez de "re-ejecutar siempre": una tarea programada diaria no debe re-consumir cuota de FotMob/YouTube ni pisar una semana publicada.
- Alinear inferencia con entrenamiento sumando todos los torneos de club: con `mainLeague` solo-liga se subestimarían a los que juegan copas. Matching de temporada tolerante al sufijo de fase.
- Torneo club sin goles/asistencias → jugador sin score (faltante ≠ cero). `playerStats` se llama con `requests` directo (la librería devuelve `null` en ese endpoint). El score ordena candidatos TOTW: no es probabilidad verificada sobre ese universo.
- `automatizacion.py` sobreescribe `data/tweet_top5.txt`: no hay archivo de tweets por semana. Para verlos por semana hay que recomponerlos desde los CSV.

## 3. Aprendizajes y errores a evitar
- FotMob publica el TOTW con días de atraso: puede haber fixtures en la semana sin TOTW y el pipeline lo avisa (no es error de parsing). Distinguir: "0 fixtures" = parón real; "fixtures sin TOTW" = publicación pendiente; "temporada no coincide" = formato/sufijo.
- ECE mide la brecha confianza-frecuencia, no el spread de las predicciones. En sklearn>=1.8 `C=np.inf` se convierte en `penalty=None` y emite warning: usar `C=1e10` para el Platt sin regularización (regla AGENTS: sin warnings).
- No convertir faltantes en cero, no puntuar perfiles con liga/club/temporada incompatibles; las features históricas son por jugador-temporada, no usar goles/asistencias de un solo partido. En tests, `monkeypatch.setattr(modulo, 'funcion')` no alcanza si el runner hizo `from x import funcion`: hay que parchear donde se usó el nombre.
- **No usar stats actuales para backfill histórico**: `playerStats` son acumulados de temporada a la fecha de hoy. En W40-W42 el desvío es de 1 a 3 semanas (aceptable, documentarlo); para ~30 semanas atrás sesgaría el ranking.
- Los fixtures de FotMob **no traen round token** (0 de 495 en Argentina 2026): `seleccionar_rounds` termina eligiendo todas las rondas y el filtro real es el `match_id` contra los fixtures de la semana.
- VADER está entrenado en inglés: en español su aporte es limitado y el peso real lo carga el léxico propio de `nlp_engine.py`.
- No mezclar en un mismo diccionario `ligas_con_totw` (lista) y `n_ligas_con_totw` (conteo): el segundo pisa al primero. Mismo error de nombres en `guardar_marcador`.
- Nunca poner `display: flex` (o grid) sobre un `<td>`/`<th>`: meter un `div` adentro y flexear eso.
- Chrome headless en Windows no baja de 500 px de viewport: para probar mobile de verdad, cargar la página en un `<iframe>` de 390 px.

## 4. Próximos pasos
1. **Fase 2 (aprobada por el usuario)**: agregar `--semana YYYY-Www` al runner; conectar `sentimiento_historico` + `ranking_historico` al final de la corrida (hoy la sección "pulso de las menciones" queda stale: la landing lee CSVs que la corrida no regenera); backfill live de W40, W41, W42 y una corrida completa end-to-end. Re-medir W34-W39 con el motor nuevo (≈324 unidades de cuota de YouTube) para que la serie sea homogénea.
2. **Fase 3 (aprobada)**: validar el sentimiento con etiquetas. Guardar los textos crudos por fuente (hoy la caché solo guarda el score final: cambiar el motor obliga a volver a la red); muestra de ~250-400 textos etiquetados a mano; medir VADER / léxico / BERT y las mezclas de fuente; recién ahí fijar los pesos 60/40.
3. Publicar tweet real: faltan credenciales OAuth 1.0a y `requests-oauthlib` (no instalado).
4. Re-activar Ecuador/Uruguay cuando FotMob publique TOTW; preparar la tarea programada de Windows (ya soportada por el marcador).
5. Decidir si reconstruir ~30 semanas de ranking histórico desde la caché: contradice la regla de no backfill con stats actuales; solo con stats de la fecha no es posible.

## Estado Git observado
- Cambios de la Fase 1 sin commitear: `src/nlp_engine.py`, `src/corrida_semanal.py`, `src/train_model.py`, `src/landing_data.py`, `src/sentimiento_radar.py`, `web/{index.html,app.js,data.js}`, `README.md`, tests (nuevo `tests/test_nlp_engine.py`).
- `models/evaluacion.json` y `data/estado/` no se versionan (`models/` y `data/` están en `.gitignore`).
