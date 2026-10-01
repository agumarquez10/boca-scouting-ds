# MEMORY.md — Memoria temporal del proyecto

`AGENTS.md` exige leer esta memoria al inicio y actualizarla al cierre. Máximo 50 líneas; mantener hechos vigentes, en español y con fundamentos DS/programación.

## 1. Estado actual del proyecto
- Objetivo: ranking semanal de jugadores de los TOTW de varias ligas; sentimiento real y tweet siguen pendientes.
- Modelo principal actual: Logistic L1 (`penalty='l1'`, `solver='saga'`), esquema de 9 features: goles, asistencias, edad y dummies de posición.
- Etiquetas manuales; `rating` y derivados no son features. CV/OOF agrupado por jugador y test temporal.
- Score calibrado: `calibrador.pkl` (Platt sobre OOF por jugador) → columna `probabilidad_adn` = P(etiqueta manual | features) bajo el train. Test: Brier 0.1716→0.1595, ECE(5) 0.1071→0.0647; a=0.76>0 preserva el orden del ranking (se ordena por score bruto).
- `src/scouting_pipeline.py`: semana ISO UTC → fixtures/TOTW FotMob → suma de `playerStats` por torneo de CLUB de la temporada → L1 → ranking + no resueltos + avisos.
- Alcance verificado: entrenamiento incluye copas/continental; `mainLeague` es solo liga, por eso se suman todos los torneos club.
- Ligas activas: Argentina (112), Brasil (268), Perú (131), Chile (273), Paraguay (199). Ecuador (246) y Uruguay (161) en stand by (`skip=True`: FotMob no publica TOTW, rounds=null); MLS (130) quitada; México salió antes.
- Validación live 21–28/09/2026: Argentina/Perú 2+2; Paraguay 2; Brasil y Chile en parón. Semanas W34–W39/2026 guardadas (22–29 jugadores); W40 (28/09–05/10) sin TOTW por fecha FIFA.
- Ranking histórico: `src/ranking_historico.py` agrega los CSV semanales por `player_id_fotmob` → `data/ranking_historico_acumulado.csv` (116 jugadores, 6 semanas; líder Matheus Pereira 3/5). Reporta `apariciones_top5`, `tasa_top5` (normaliza el volumen de Brasil), score max/medio.
- Tests: 44 pasaron, 0 warnings (fix sklearn 1.8: `C=np.inf` → `C=1e10` en `ajustar_platt`). EDA: 39 celdas, validado.
- `automatizacion.py` ya corre el radar TOTW → top 3 por puesto (DEL/MED/DEF; extremos→DEL, laterales→DEF) con club + goles+asistencias → borrador `data/tweet_top5.txt` (no publica; sin límite de 280 chars). El hype global se quitó del tweet (era constante +0.02 y no aportaba); `hype_actual`/`clasificar_hype`/`cargar_hype` quedan para sentimiento real por jugador. `model_training.ipynb`, `scouting_mercado.py`, `semanal.py` y `ranking_acumulado.py` quedan legado.

## 2. Decisiones tomadas y por qué
- L1 se priorizó para ranking por resultados temporales recientes en AUPRC/top-N; puede cambiar con nueva evidencia.
- Calibrar con Platt sobre OOF por jugador: corrige a la vez el sesgo de `class_weight='balanced'` (prior reponderado) y la falta de calibración; isotónica descartada por pocos datos (240 jugadores).
- Mantener dos columnas: `score`/`probabilidad` ordinal para ordenar y `probabilidad_adn` para interpretar; AUPRC mide orden y Brier/ECE miden calibración (ejes distintos).
- Alinear inferencia con entrenamiento sumando todos los torneos de club: con `mainLeague` solo-liga se subestimarían a los que juegan copas.
- Excluir selecciones de la suma por heurística de nombre (entrenamiento es por club); heurística temporal, no regla permanente.
- Matching de temporada tolerante al sufijo de fase (`2026/2027 - Apertura` == `2026/2027`): el sufijo rompió a los 16 de México.
- Agregar Uruguay/Chile/Paraguay (pedido del usuario); Ecuador queda en stand by y MLS fuera.
- Salir de las ligas sin TOTW usable (MLS quitada, Ecuador en stand by con `skip`+razón): evita sembrar el radar con avisos repetidos; documenta por qué en la config.
- Torneo club sin goles/asistencias → jugador sin score (faltante ≠ cero); sin `Matches` solo marca auditoría (`torneos_sin_matches`).
- `playerStats` se llama con `requests` directo porque la librería `fotmob` devuelve `null` en ese endpoint (cache igual que el resto).
- El score ordena candidatos TOTW; no es probabilidad verificada sobre TOTW. FotMob como fuente es decisión práctica, no fijada en `AGENTS.md`.

## 3. Aprendizajes y errores a evitar
- FotMob publica el TOTW con días de retraso tras el cierre de fecha: puede haber fixtures en la semana sin TOTW; el pipeline ahora lo avisa (no es error de parsing).
- Distinguir casos: "0 fixtures en la semana" = parón real de liga; "fixtures sin TOTW" = publicación pendiente; "temporada no coincide" = revisar formato/sufijo.
- ECE mide la brecha confianza-frecuencia, no el spread de las predicciones; con p=C y frecuencia=C el ECE es 0 aunque el Brier sea malo.
- En sklearn>=1.8 `C=np.inf` se convierte en `penalty=None` y emite warning; usar `C=1e10` para el Platt sin regularización (regla AGENTS: sin warnings).
- Las features históricas son por jugador-temporada: no usar goles/asistencias de un solo partido.
- No convertir faltantes en cero, no puntuar perfiles con liga/club/temporada incompatibles.
- No usar stats actuales para backfill histórico; no usar `rating` como feature; no reportar P@10 de filas repetidas como 10 jugadores únicos.
- API-Football Free rechazó stats 2026; Highlightly y Promiedos sin cobertura completa; siguen fuera del flujo.
- El uso live de FotMob refresca `api_cache` en SQLite; pedir aprobación antes de nuevas consultas/escrituras.

## 4. Próximos pasos
1. Publicar tweet real: faltan credenciales OAuth 1.0a y `requests-oauthlib`; hoy solo borrador.
2. Sentimiento real por jugador del TOTW (RSS/YouTube existen; Reddit con placeholders 401); hoy solo hype global.
3. Re-activar Ecuador/Uruguay cuando FotMob publique TOTW; programar la corrida semanal.

## Estado Git observado
- Último commit: `9dd1367 pruebas fotmob_api eliminando selecciones`.
- Locales sin commit: `AGENTS.md`, `MEMORY.md`, `README.md`, `src/automatizacion.py`, `src/calibracion.py`, `src/construir_features.py`, `src/ligas.py`, `src/ranking_historico.py`, `src/scouting_pipeline.py`, `src/train_model.py`, `tests/test_automatizacion.py`, `tests/test_calibracion.py`, `tests/test_ranking_historico.py`, `tests/test_reglas.py`, `tests/test_scouting_pipeline.py`.
