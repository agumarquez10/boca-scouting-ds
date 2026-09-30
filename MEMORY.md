# MEMORY.md — Memoria temporal del proyecto

`AGENTS.md` exige leer esta memoria al inicio y actualizarla al cierre. Máximo 50 líneas; mantener hechos vigentes, en español y con fundamentos DS/programación.

## 1. Estado actual del proyecto
- Objetivo: ranking semanal de jugadores de los TOTW de varias ligas; sentimiento real y tweet siguen pendientes.
- Modelo principal actual: Logistic L1 (`penalty='l1'`, `solver='saga'`), esquema de 9 features: goles, asistencias, edad y dummies de posición.
- Etiquetas manuales; `rating` y derivados no son features. CV/OOF agrupado por jugador y test temporal.
- Score calibrado: `calibrador.pkl` (Platt sobre OOF por jugador) → columna `probabilidad_adn` = P(etiqueta manual | features) bajo el train. Test: Brier 0.1716→0.1595, ECE(5) 0.1071→0.0645; a=0.76>0 preserva el orden del ranking (se ordena por score bruto).
- `src/scouting_pipeline.py`: semana ISO UTC → fixtures/TOTW FotMob → suma de `playerStats` por torneo de CLUB de la temporada → L1 → ranking + no resueltos + avisos.
- Alcance verificado: entrenamiento incluye copas/continental; `mainLeague` es solo liga, por eso se suman todos los torneos club.
- Ligas activas: Argentina (112), Brasil (268), Perú (131). Ecuador (246) en stand by (`skip=True`, sin TOTW publicado) y MLS (130) quitada a pedido del usuario; México salió antes.
- Primer ranking real: `data/ranking_jugadores_fecha_2026-W39.csv` (semana 21–28/09/2026, 4 jugadores, 32 columnas, 0 no resueltos; Argentina 2 + Perú 2, Brasil en parón). Sin columna `probabilidad_adn` (se agregará en la próxima corrida). Demo con la L1 calibrada: .975→86.5%, .832→57.3%, .519→29.5%, .383→21.5%.
- Tests: 28 pasaron en la última corrida. EDA: 39 celdas, validado.
- `model_training.ipynb` es legado; no usar para producir artefactos. La automatización aún consume el formato antiguo.

## 2. Decisiones tomadas y por qué
- L1 se priorizó para ranking por resultados temporales recientes en AUPRC/top-N; puede cambiar con nueva evidencia.
- Calibrar con Platt sobre OOF por jugador: corrige a la vez el sesgo de `class_weight='balanced'` (prior reponderado) y la falta de calibración; isotónica descartada por pocos datos (240 jugadores).
- Mantener dos columnas: `score`/`probabilidad` ordinal para ordenar y `probabilidad_adn` para interpretar; AUPRC mide orden y Brier/ECE miden calibración (ejes distintos).
- Alinear inferencia con entrenamiento sumando todos los torneos de club: con `mainLeague` solo-liga se subestimarían a los que juegan copas.
- Excluir selecciones de la suma por heurística de nombre (entrenamiento es por club); heurística temporal, no regla permanente.
- Matching de temporada tolerante al sufijo de fase (`2026/2027 - Apertura` == `2026/2027`): el sufijo rompió a los 16 de México.
- Salir de las ligas sin TOTW usable (MLS quitada, Ecuador en stand by con `skip`+razón): evita sembrar el radar con avisos repetidos; documenta por qué en la config.
- Torneo club sin goles/asistencias → jugador sin score (faltante ≠ cero); sin `Matches` solo marca auditoría (`torneos_sin_matches`).
- `playerStats` se llama con `requests` directo porque la librería `fotmob` devuelve `null` en ese endpoint (cache igual que el resto).
- El score ordena candidatos TOTW; no es probabilidad verificada sobre TOTW. FotMob como fuente es decisión práctica, no fijada en `AGENTS.md`.

## 3. Aprendizajes y errores a evitar
- FotMob publica el TOTW con días de retraso tras el cierre de fecha: puede haber fixtures en la semana sin TOTW; el pipeline ahora lo avisa (no es error de parsing).
- Distinguir casos: "0 fixtures en la semana" = parón real de liga; "fixtures sin TOTW" = publicación pendiente; "temporada no coincide" = revisar formato/sufijo.
- ECE mide la brecha confianza-frecuencia, no el spread de las predicciones; con p=C y frecuencia=C el ECE es 0 aunque el Brier sea malo.
- En sklearn>=1.8 pasar `penalty=None` con `C!=1.0` emite warnings; usar `LogisticRegression(solver='lbfgs')` con defaults (regla AGENTS: sin warnings).
- Las features históricas son por jugador-temporada: no usar goles/asistencias de un solo partido.
- No convertir faltantes en cero, no puntuar perfiles con liga/club/temporada incompatibles.
- No usar stats actuales para backfill histórico; no usar `rating` como feature; no reportar P@10 de filas repetidas como 10 jugadores únicos.
- API-Football Free rechazó stats 2026; Highlightly y Promiedos sin cobertura completa; siguen fuera del flujo.
- El uso live de FotMob refresca `api_cache` en SQLite; pedir aprobación antes de nuevas consultas/escrituras.

## 4. Próximos pasos
1. Integrar sentimiento real (RSS/YouTube existen; Reddit sigue con placeholders 401).
2. Próxima corrida semanal: confirmar `probabilidad_adn` en el CSV; re-activar Ecuador cuando publique TOTW; Brasil retoma liga el 02/10.
3. Adaptar automatización/tweet al nuevo CSV semanal (hoy `automatizacion.py` lee el formato antiguo).

## Estado Git observado
- Último commit: `9dd1367 pruebas fotmob_api eliminando selecciones`.
- Locales sin commit: `AGENTS.md`, `MEMORY.md`, `README.md`, `src/calibracion.py`, `src/construir_features.py`, `src/ligas.py`, `src/scouting_pipeline.py`, `src/train_model.py`, `tests/test_calibracion.py`, `tests/test_reglas.py`, `tests/test_scouting_pipeline.py`.
