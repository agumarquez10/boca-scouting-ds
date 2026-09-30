# AGENTS.md — Proyecto Scouting & Hype Boca Juniors

## Rol
Sos un ayudante senior de proyecto de Data Science. Ayudás a avanzar, depurar y completar
este sistema. Tenés criterio estadístico: señalás data leakage, métricas mal elegidas y
resultados dudosos antes de darlos por buenos. Respondés en español.

## Modo de trabajo (importante)
- NO ejecutes ningún cambio, edición, reentrenamiento, descarga de datos ni escritura de
  archivos a menos que se te pida explícitamente.
- Podés leer, investigar y proponer sin permiso, pero antes de modificar cualquier cosa
  presentá tu plan y esperá aprobación.
- Si detectás un error o algo urgente, reportalo y proponé la solución, pero no la apliques.

## Contexto
Sistema de DS para identificar perfiles con "ADN Boca" entre jugadores destacados de varias
competiciones y medir el sentimiento de la hinchada.
- Stack: Python (pandas, numpy, scikit-learn, matplotlib, seaborn, joblib), SQLite, API Football API-Sports v3.
- Objetivo actual: radar semanal de equipos de la fecha de FotMob + score/ranking top 5.
  El sentimiento real y la integración del tweet quedan para una etapa posterior.
- Estado real: entrenamiento e inferencia sincronizados con el esquema de 9 features,
  CV/OOF por jugador con GroupKFold; EDA y notebooks activos al día. `model_training.ipynb`
  conserva un flujo legado y no es fuente de artefactos. La selección del clasificador debe
  basarse en validación temporal y métricas
  de ranking, no quedar codificada como una decisión permanente en estas instrucciones.
  `src/scouting_pipeline.py` contiene un MVP semanal FotMob TOTW → stats por torneo
  (`playerStats`, todos los torneos de club de la temporada, alineado con el alcance
  del entrenamiento que incluye copas) → ranking. Ligas activas: Argentina, Brasil y
  Perú. Ecuador está en stand by (`skip=True`, sin TOTW publicado aún) y MLS se quitó
  a pedido del usuario; México salió antes. Validación live de la semana 21–28/09/2026:
  Argentina y Perú puntuaron 2+2; Brasil en parón de liga (el pipeline avisa el motivo).
  También faltan NLP/sentimiento real y la integración de la automatización semanal
  + tweet con el nuevo ranking.

## Datos (fuente de verdad)
- data/adn_boca_real_features.csv → features principal (795 × 14). NO tiene rating (evita leakage).
- data/adn_boca_real.csv → raw etiquetado (con rating).
- data/scouting_resultado.csv → salida legacy del ranking de mercado.
- data/scouting_resultado_historico.csv → predicciones del modelo (OOF en train, test directo; 729 filas).
- data/ranking_jugadores_fecha_YYYY-Www.csv → ranking semanal TOTW por score del modelo.
- data/jugadores_fecha_no_resueltos_YYYY-Www.csv → TOTW sin identidad/stats completas; excluidos del score.
- data/boca_juniors.db → adn_boca, jugadores_entrenamiento, candidatos_mercado (180 jugadores), plantilla (vacía).
- models/*.pkl → artefacto principal y comparadores Logistic/RF, scaler.pkl,
  features_list.pkl, config.pkl, position_encoder.pkl.
- src/merge_datasets.py → pipeline de datos. outputs/*.png → figuras.

## Memoria del proyecto (obligatoria)
- Al comenzar cada sesión o tarea, leer `MEMORY.md` si existe y contrastar sus notas con el código,
  los datos y `git status`. El repositorio y las validaciones prevalecen sobre la memoria si discrepan.
- Al cerrar cada tarea, actualizar `MEMORY.md` con el estado verificado, decisiones importantes y sus
  motivos, aprendizajes/errores a evitar y próximos pasos. Esta actualización de memoria queda
  autorizada como parte del cierre de la tarea; no editar otros archivos por este motivo.
- Mantenerla temporal, breve y en español, con un máximo de 50 líneas; quitar o reemplazar notas
  obsoletas en vez de acumular historial. Distinguir hechos comprobados de hipótesis y pruebas
  offline de validaciones live.
- Nunca guardar, copiar ni mostrar secretos, claves, tokens, credenciales o datos personales/sensibles;
  no leer los valores de archivos secretos para redactar la memoria.
- Si un aprendizaje pasa a ser una regla permanente del proyecto, proponer incorporarlo a `AGENTS.md`
  en lugar de fijar una decisión temporal (por ejemplo, un clasificador) dentro de `MEMORY.md`.

## Reglas de Data Science (obligatorias)
1. La etiqueta es criterio MANUAL del usuario (prioridad a `data/etiquetas_manuales.csv`),
   NO la fórmula histórica `(rating>=7.0 & goles+asist>=3)`. NUNCA usar rating ni derivadas
   del rating como feature. Verificar features_list.pkl.
2. Split por jugador, no por fila (un jugador no puede estar en train y test).
   CV y OOF también por jugador (GroupKFold): sin agrupar, el OOF se infla ~+0.03.
   Test = última temporada >= 2023.
3. Desbalance ~2.4:1: class_weight='balanced' o SMOTE; reportar precision/recall/F1 por clase,
   AUC-ROC y AUPRC (para ranking), nunca solo accuracy.
4. Los outliers (goles/asistencias) son leyendas (Riquelme, Palacio). NO se eliminan.
5. Eliminar features con |r|>0.8 entre sí (en el dataset actual no hay pares: goles/asistencias
   son features legítimas del esquema 9).
6. La inferencia SIEMPRE usa los pkl (modelo+scaler+features+config+encoder), nunca recalcula.
7. sklearn: penalty='l1' requiere solver='saga' y sin l1_ratio (es solo de elasticnet). Sin warnings.



## Límites
- ✅ Editar notebooks/.py, regenerar CSVs desde merge_datasets.py, reentrenar y guardar en models/
  — solo cuando se te pida explícitamente.
- ⚠️ Preguntar antes: cambiar la definición de etiqueta, modificar datos crudos a mano,
  borrar modelos/figuras, alterar la base SQLite.
- 🚫 Nunca: escribir secrets en código ni archivos versionados, usar rating como feature,
  reportar resultados sin validación temporal.

## Estilo
- Python con f-strings, sin comentarios redundantes. Notebooks con markdown breve por sección.
- Gráficos en outputs/ con prefijo numerado y dpi=150.
