# MEMORY.md — Memoria temporal del proyecto

`AGENTS.md` exige leer esta memoria al inicio y actualizarla al cierre. Máximo 50 líneas; mantener hechos vigentes, en español y con fundamentos DS/programación.

## 1. Estado actual del proyecto
- Objetivo: ranking semanal de jugadores de los TOTW de varias ligas; sentimiento real y tweet siguen pendientes.
- Modelo principal actual: Logistic L1 (`penalty='l1'`, `solver='saga'`), esquema de 9 features: goles, asistencias, edad y dummies de posición.
- Etiquetas manuales; `rating` y derivados no son features. CV/OOF agrupado por jugador y test temporal.
- `src/scouting_pipeline.py` usa TOTW/fixtures y perfiles FotMob (`mainLeague.stats`); genera ranking y archivo de no resueltos por semana ISO UTC.
- FotMob se probó en Argentina con Salvio y Ronaldo Martínez; ambos perfiles tenían stats 2026 y pasaron una inferencia offline L1.
- Esa prueba no valida cobertura de todas las ligas ni reemplaza una validación completa del ranking semanal.
- Tests: 17 pasaron en la última corrida. EDA: 39 celdas, validado.
- `model_training.ipynb` es legado; no usar para producir artefactos. La automatización aún consume el formato antiguo.

## 2. Decisiones tomadas y por qué
- L1 se priorizó para ranking por resultados temporales recientes en AUPRC/top-N; la elección puede cambiar con nueva evidencia.
- Usar stats FotMob junto al TOTW evita el límite de API-Football Free en temporadas 2026 y permite reutilizar IDs del mismo proveedor.
- Enriquecer con `mainLeague.stats`, validando ID, club, liga y temporada; no cruzar proveedores por nombre solamente.
- Mantener FotMob como fuente actual es una decisión práctica para el MVP, no una regla permanente de `AGENTS.md`.
- El score ordena candidatos TOTW; no es una probabilidad calibrada para todo el mercado.

## 3. Aprendizajes y errores a evitar
- Las features históricas son por jugador-temporada: no usar goles/asistencias de un solo partido.
- Confirmar si los datos de entrenamiento incluyen solo liga o también copas/fases; no mezclar alcances.
- No convertir estadísticas faltantes en cero ni puntuar perfiles con liga/club/temporada incompatibles.
- No usar stats finales actuales para backfill histórico: incluirían partidos futuros respecto del TOTW.
- No usar `rating` como feature, no mezclar temporadas del mismo jugador entre folds y no reportar P@10 de filas repetidas como 10 jugadores únicos.
- API-Football Free rechazó stats 2026; Highlightly no devolvió stats por competición para Ronaldo; Promiedos no está verificado para cobertura completa por jugador.
- El uso live de FotMob refresca `api_cache` en SQLite; pedir aprobación antes de nuevas consultas/escrituras.

## 4. Próximos pasos
1. Alinear el alcance de `mainLeague.stats` con las estadísticas de entrenamiento.
2. Validar en Brasil, México y MLS: cobertura, matching, no resueltos y cuota/caché.
3. Integrar sentimiento real solo después de estabilizar el ranking.
4. Adaptar automatización y tweet para leer el nuevo CSV semanal.
