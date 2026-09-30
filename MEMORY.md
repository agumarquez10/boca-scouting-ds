# MEMORY.md — Memoria temporal del proyecto

`AGENTS.md` exige leer esta memoria al inicio y actualizarla al cierre. Máximo 50 líneas; mantener hechos vigentes, en español y con fundamentos DS/programación.

## 1. Estado actual del proyecto
- Objetivo: ranking semanal de jugadores de los TOTW de varias ligas; sentimiento real y tweet siguen pendientes.
- Modelo principal actual: Logistic L1 (`penalty='l1'`, `solver='saga'`), esquema de 9 features: goles, asistencias, edad y dummies de posición.
- Etiquetas manuales; `rating` y derivados no son features. CV/OOF agrupado por jugador y test temporal.
- `src/scouting_pipeline.py`: semana ISO UTC → fixtures/TOTW FotMob → suma de `playerStats` por torneo de CLUB de la temporada → L1 → ranking + no resueltos + avisos.
- Alcance verificado: entrenamiento incluye copas/continental; `mainLeague` es solo liga, por eso se suman todos los torneos club.
- Ligas activas: Argentina, Brasil, Ecuador (246), Perú (131), MLS (130); México quitado a pedido del usuario.
- Validación live semana 21–28/09/2026: Argentina 2 y Perú 2 puntuados (0 no resueltos); Brasil en parón de liga (sin fechas 21/09–02/10); Ecuador y MLS avisan "fixtures sin TOTW publicado aún".
- Tests: 22 pasaron en la última corrida. EDA: 39 celdas, validado.
- `model_training.ipynb` es legado; no usar para producir artefactos. La automatización aún consume el formato antiguo.

## 2. Decisiones tomadas y por qué
- L1 se priorizó para ranking por resultados temporales recientes en AUPRC/top-N; puede cambiar con nueva evidencia.
- Alinear inferencia con entrenamiento sumando todos los torneos de club: con `mainLeague` solo-liga se subestimarían a los que juegan copas.
- Excluir selecciones de la suma por heurística de nombre (entrenamiento es por club); heurística temporal, no regla permanente.
- Matching de temporada tolerante al sufijo de fase (`2026/2027 - Apertura` == `2026/2027`): el sufijo rompió a los 16 de México.
- Torneo club sin goles/asistencias → jugador sin score (faltante ≠ cero); sin `Matches` solo marca auditoría (`torneos_sin_matches`).
- `playerStats` se llama con `requests` directo porque la librería `fotmob` devuelve `null` en ese endpoint (cache igual que el resto).
- El score ordena candidatos TOTW; no es probabilidad calibrada. FotMob como fuente es decisión práctica, no fijada en `AGENTS.md`.

## 3. Aprendizajes y errores a evitar
- FotMob publica el TOTW con días de retraso tras el cierre de fecha: puede haber fixtures en la semana sin TOTW; el pipeline ahora lo avisa (no es error de parsing).
- Distinguir casos: "0 fixtures en la semana" = parón real de liga; "fixtures sin TOTW" = publicación pendiente; "temporada no coincide" = revisar formato/sufijo.
- Las features históricas son por jugador-temporada: no usar goles/asistencias de un solo partido.
- No convertir faltantes en cero, no puntuar perfiles con liga/club/temporada incompatibles.
- No usar stats actuales para backfill histórico; no usar `rating` como feature; no reportar P@10 de filas repetidas como 10 jugadores únicos.
- API-Football Free rechazó stats 2026; Highlightly y Promiedos sin cobertura completa; siguen fuera del flujo.
- El uso live de FotMob refresca `api_cache` en SQLite; pedir aprobación antes de nuevas consultas/escrituras.

## 4. Próximos pasos
1. Re-validar Ecuador y MLS cuando FotMob publique el TOTW de la fecha jugada (21–28/09).
2. Revisar cuota/caché con un ranking semanal completo de las 5 ligas y decidir si conviene un solo CSV por semana.
3. Integrar sentimiento real solo después de estabilizar el ranking.
4. Adaptar automatización y tweet para leer el nuevo CSV semanal.

## Estado Git observado
- Último commit: `9dd1367 pruebas fotmob_api eliminando selecciones`.
- Locales sin commit: `AGENTS.md`, `README.md`, `src/ligas.py`, `src/scouting_pipeline.py`, `tests/test_scouting_pipeline.py`, `MEMORY.md`.
