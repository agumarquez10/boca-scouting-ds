# MEMORY.md — Memoria temporal del proyecto

`AGENTS.md` exige leer esta memoria al inicio y actualizarla al cierre. Máximo 50 líneas; mantener hechos vigentes, en español y con fundamentos DS/programación.

## 1. Estado actual del proyecto
- Objetivo: ranking semanal de jugadores de los TOTW de varias ligas; publicar el tweet y ampliar el sentimiento siguen pendientes.
- Modelo principal actual: Logistic L1 (`penalty='l1'`, `solver='saga'`), esquema de 9 features: goles, asistencias, edad y dummies de posición.
- Etiquetas manuales; `rating` y derivados no son features. CV/OOF agrupado por jugador y test temporal.
- Score calibrado: `calibrador.pkl` (Platt sobre OOF por jugador) → columna `probabilidad_adn` = P(etiqueta manual | features) bajo el train. Test: Brier 0.1716→0.1595, ECE(5) 0.1071→0.0647; a=0.76>0 preserva el orden del ranking (se ordena por score bruto).
- `src/scouting_pipeline.py`: semana ISO UTC → fixtures/TOTW FotMob → suma de `playerStats` por torneo de CLUB de la temporada → L1 → ranking + no resueltos + avisos.
- Alcance verificado: el entrenamiento incluye copas/continental y `mainLeague` es solo liga, por eso la inferencia suma todos los torneos club.
- Ligas activas: Argentina (112), Brasil (268), Perú (131), Chile (273), Paraguay (199). Ecuador (246) y Uruguay (161) en stand by (`skip=True`: FotMob no publica TOTW, rounds=null); MLS (130) quitada; México salió antes.
- Validación live 21–28/09/2026: Argentina/Perú 2+2; Paraguay 2; Brasil y Chile en parón. Semanas W34–W39/2026 guardadas (22–29 jugadores); W40 (28/09–05/10) sin TOTW por fecha FIFA.
- Ranking histórico: `src/ranking_historico.py` agrega los CSV semanales por `player_id_fotmob` → `data/ranking_historico_acumulado.csv` (116 jugadores, 6 semanas; líder Matheus Pereira 3/5). Reporta `apariciones_top5`, `tasa_top5` (normaliza el volumen de Brasil), score max/medio.
- Tests: 89 pasaron, 0 warnings (fix sklearn 1.8: `C=np.inf` → `C=1e10` en `ajustar_platt`). EDA: 39 celdas, validado.
- Landing `web/`: `src/landing_data.py` → `web/data.js` (`window.RADAR_DATA`), estática sin servidor ni build (doble click). Muestra planilla semanal, borradores e histórico con orden/búsqueda/filtro. Offline: no consulta la API ni recalcula el modelo.
- La landing no muestra el score ni `probabilidad_adn` (el usuario lo pidió: "no aporta"), ni la sección de deudas, ni el texto del tweet: en su lugar muestra el corte por puesto (DEL/MED/DEF con sus 3 candidatos y G+A, más el sentimiento cacheado), que es la base real del tweet. Ojo: ese top 3 por puesto **no** sale del top 5 de la planilla, son dos cortes distintos sobre el mismo ranking. `data.js` ya no exporta score/probabilidad/rating.
- Corrida semanal: `src/corrida_semanal.py` es el entrypoint (gate → ranking → sentimiento → tweet → landing), con log en `outputs/logs/` y exit codes `0` ok / `2` sin salida / `1` error. `generar_ranking_semanal` llena un dict `detalle` opcional con `semana`, fechas y `ligas_con_totw` (no rompe la tupla de 3). `automatizacion.generar_borrador(ranking)` hace sentimiento + tweet sobre un ranking ya calculado.
- Gate: mínimo **3 ligas con TOTW publicado** (elegido por el usuario). Tener fixtures en la semana no cuenta, porque FotMob publica la fecha con días de atraso; así el gate se reintenta en la corrida siguiente sobre la misma semana. Si no se cumple no se escribe nada (ni CSV, ni tweet, ni `web/data.js`).
- `automatizacion.py` corre el radar TOTW → top 3 por puesto (DEL/MED/DEF; extremos→DEL, laterales→DEF) con club + G+A → top 3 por sentimiento (YouTube 40% + prensa multi-medio 60% vía `sentimiento_radar.py`, caché semanal) sobre esos 9 → borrador `data/tweet_top5.txt` (no publica). `hype_*`, `model_training.ipynb`, `scouting_mercado.py`, `semanal.py` y `ranking_acumulado.py` quedan legado.

## 2. Decisiones tomadas y por qué
- L1 se priorizó para ranking por resultados temporales recientes en AUPRC/top-N; puede cambiar con nueva evidencia.
- Calibrar con Platt sobre OOF por jugador: corrige a la vez el sesgo de `class_weight='balanced'` (prior reponderado) y la falta de calibración; isotónica descartada por pocos datos (240 jugadores).
- Mantener dos columnas: `score`/`probabilidad` ordinal para ordenar y `probabilidad_adn` para interpretar; AUPRC mide orden y Brier/ECE miden calibración (ejes distintos).
- Alinear inferencia con entrenamiento sumando todos los torneos de club: con `mainLeague` solo-liga se subestimarían a los que juegan copas. Matching de temporada tolerante al sufijo de fase (`2026/2027 - Apertura` == `2026/2027`).
- Alinear inferencia con entrenamiento sumando todos los torneos de club: con `mainLeague` solo-liga se subestimarían a los que juegan copas.
- Agregar Uruguay/Chile/Paraguay (pedido del usuario); Ecuador queda en stand by y MLS fuera: salir de las ligas sin TOTW usable evita sembrar el radar con avisos repetidos y deja el motivo documentado en la config.
- Torneo club sin goles/asistencias → jugador sin score (faltante ≠ cero); sin `Matches` solo marca auditoría (`torneos_sin_matches`).
- `playerStats` se llama con `requests` directo porque la librería `fotmob` devuelve `null` en ese endpoint (cache igual que el resto).
- El score ordena candidatos TOTW; no es probabilidad verificada sobre TOTW. FotMob como fuente es decisión práctica, no fijada en `AGENTS.md`.
- `automatizacion.py` sobreescribe `data/tweet_top5.txt`: no hay archivo de tweets por semana. Para verlos por semana hay que recomponer el borrador offline desde los CSV (`componer_tweet` + `seleccionar_por_puesto`), como hace `landing_data.py`.
- Una corrida programada no puede depender de que nada falle: `buscar_videos` de YouTube ahora tiene `try/except` (un 403 por cuota cae a prensa sola, que `combinar_fuentes` ya tolera) y la caché de sentimiento se escribe incrementalmente, para que una interrupción no pierda la cuota ya consumida.
- El gate va antes de `guardar_resultados`, no después: pedir "no escribir nada si el gate falla" obliga a que el runner orqueste el radar en vez de llamar a `scouting_pipeline.main()` (que ya guarda).

## 3. Aprendizajes y errores a evitar
- FotMob publica el TOTW con días de retraso tras el cierre de fecha: puede haber fixtures en la semana sin TOTW y el pipeline lo avisa (no es error de parsing). Distinguir: "0 fixtures" = parón real; "fixtures sin TOTW" = publicación pendiente; "temporada no coincide" = formato/sufijo.
- ECE mide la brecha confianza-frecuencia, no el spread de las predicciones; con p=C y frecuencia=C el ECE es 0 aunque el Brier sea malo.
- En sklearn>=1.8 `C=np.inf` se convierte en `penalty=None` y emite warning; usar `C=1e10` para el Platt sin regularización (regla AGENTS: sin warnings).
- No convertir faltantes en cero, no puntuar perfiles con liga/club/temporada incompatibles. Las features históricas son por jugador-temporada: no usar goles/asistencias de un solo partido.
- No usar stats actuales para backfill histórico; no usar `rating` como feature; no reportar P@10 de filas repetidas como 10 jugadores únicos.
- API-Football Free rechazó stats 2026; Highlightly y Promiedos sin cobertura completa; siguen fuera del flujo. El uso live de FotMob refresca `api_cache` en SQLite: pedir aprobación antes de nuevas consultas (ya se coló una vez al escribir un test que parcheaba el módulo equivocado y llegó a la API real).
- Chrome headless en Windows no baja de 500 px de viewport: un screenshot de 390 px sale recortado y parece overflow. Para probar mobile de verdad, cargar la página en un `<iframe>` de 390 px.
- `strftime('%B')` devuelve el mes en inglés en Windows; el formato de fecha de la landing se arma a mano en `web/app.js` (`MESES`).

## 4. Próximos pasos
1. Publicar tweet real: faltan credenciales OAuth 1.0a y `requests-oauthlib`; hoy solo borrador (y la landing lo muestra como tal).
2. Probar la primera corrida real de `corrida_semanal.py` (hoy solo verificada con dobles de prueba, sin pegarle a FotMob).
3. Validar cobertura del sentimiento por jugador (la prensa promedia cerca de 0 porque VADER es inglés: la señal de medios es la más débil y pesa 0.6); se evaluó activar BERT español o rebalancear pesos.
4. Re-activar Ecuador/Uruguay cuando FotMob publique TOTW; decidir si programar la corrida en el Programador de tareas (hoy se corre a mano).

## Estado Git observado
- Sin commit: `src/landing_data.py`, `tests/test_landing_data.py`, `web/` (index.html, styles.css, app.js, data.js), `src/corrida_semanal.py`, `tests/test_corrida_semanal.py`.
- Modificados sin commit: `src/automatizacion.py`, `src/sentimiento_jugadores_youtube.py`, `src/sentimiento_radar.py`, `src/scouting_pipeline.py`, `README.md`, `MEMORY.md`.
- Último commit: `7cf2172 tweet sentimiento`.
