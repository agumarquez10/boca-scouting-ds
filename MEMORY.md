# MEMORY.md — Memoria temporal del proyecto

`AGENTS.md` exige leer esta memoria al inicio y actualizarla al cierre. Máximo 50 líneas; mantener hechos vigentes, en español y con fundamentos DS/programación.

## 1. Estado actual del proyecto
- Objetivo: ranking semanal de jugadores de los TOTW de varias ligas; sentimiento real y tweet siguen pendientes.
- Modelo principal actual: Logistic L1 (`penalty='l1'`, `solver='saga'`), esquema de 9 features: goles, asistencias, edad y dummies de posición.
- Etiquetas manuales; `rating` y derivados no son features. CV/OOF agrupado por jugador y test temporal.
- `src/scouting_pipeline.py`: semana ISO UTC → fixtures/TOTW FotMob → suma de `playerStats` por torneo de CLUB de la temporada → L1 → ranking + no resueltos.
- Alcance verificado: entrenamiento incluye copas/continental (partidos > 38 por temporada); `mainLeague` de FotMob es solo liga, por eso se suman todos los torneos club.
- Smoke de Argentina (live): Salvio 2G/6A en 5 torneos (36 PJ, Recopa sin Matches marcada); Ronaldo 8G/2A (Copa sumó 1 asistencia). 2/2 puntuados.
- Tests: 20 pasaron en la última corrida. EDA: 39 celdas, validado.
- `model_training.ipynb` es legado; no usar para producir artefactos. La automatización aún consume el formato antiguo.

## 2. Decisiones tomadas y por qué
- L1 se priorizó para ranking por resultados temporales recientes en AUPRC/top-N; puede cambiar con nueva evidencia.
- Alinear inferencia con entrenamiento sumando todos los torneos de club: con `mainLeague` solo-liga se subestimarían a los que juegan copas.
- Excluir selecciones de la suma por heurística de nombre (entrenamiento es por club); heurística temporal, no regla permanente.
- Torneo club sin goles/asistencias → jugador sin score (faltante ≠ cero); sin `Matches` solo marca auditoría (`torneos_sin_matches`).
- `playerStats` se llama con `requests` directo porque la librería `fotmob` devuelve `null` en ese endpoint (cache igual que el resto).
- El score ordena candidatos TOTW; no es probabilidad calibrada. FotMob como fuente es decisión práctica, no fijada en `AGENTS.md`.

## 3. Aprendizajes y errores a evitar
- Las features históricas son por jugador-temporada: no usar goles/asistencias de un solo partido.
- No confundir `mainLeague` con "temporada completa": en Argentina suma Apertura/Clausura/playoffs pero excluye copas.
- No convertir faltantes en cero, no puntuar perfiles con liga/club/temporada incompatibles.
- No usar stats actuales para backfill histórico: incluirían partidos futuros respecto del TOTW.
- No usar `rating` como feature, no mezclar temporadas del mismo jugador entre folds, no reportar P@10 de filas repetidas como 10 jugadores únicos.
- API-Football Free rechazó stats 2026; Highlightly y Promiedos no mostraron cobertura completa; siguen fuera del flujo.
- El uso live de FotMob refresca `api_cache` en SQLite; pedir aprobación antes de nuevas consultas/escrituras.

## 4. Próximos pasos
1. Validar en Brasil, México y MLS: cobertura, suma de torneos, selecciones, matching y no resueltos.
2. Revisar cuota/caché con un ranking semanal completo y decidir si conviene un solo CSV por semana.
3. Integrar sentimiento real solo después de estabilizar el ranking.
4. Adaptar automatización y tweet para leer el nuevo CSV semanal.

## Estado Git observado
- Último commit: `0eb58fc actualizacion AGENTS.md + agrego MEMORY.md`.
- Locales sin commit: `AGENTS.md`, `README.md`, `src/fotmob_api.py`, `src/scouting_pipeline.py`, `tests/test_scouting_pipeline.py`.
