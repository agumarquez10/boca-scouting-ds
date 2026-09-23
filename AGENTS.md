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
Sistema de DS para identificar fichajes con "ADN Boca" y medir el sentimiento de la hinchada.
- Stack: Python (pandas, numpy, scikit-learn, matplotlib, seaborn, joblib), SQLite, API Football API-Sports v3.
- Objetivo: ranking semanal de candidatos + tweet con top 5.
- Estado real: modelo vigente entrenado y sincronizado (esquema 9 features, CV/OOF por
  jugador con GroupKFold); EDA y notebooks de modelo al día (re-ejecutados, 0 errores).
  Faltan: el pipeline de scoring de candidatos del mercado (src/scouting_pipeline.py
  no existe), NLP/sentimiento real y la automatización semanal + tweet.

## Datos (fuente de verdad)
- data/adn_boca_real_features.csv → features principal (795 × 14). NO tiene rating (evita leakage).
- data/adn_boca_real.csv → raw etiquetado (con rating).
- data/scouting_resultado.csv → salida del ranking.
- data/scouting_resultado_historico.csv → predicciones del modelo (OOF en train, test directo; 729 filas).
- data/boca_juniors.db → adn_boca, jugadores_entrenamiento, candidatos_mercado (180 jugadores), plantilla (vacía).
- models/*.pkl → modelo_adn_boca.pkl, modelo_logistic_l1.pkl, modelo_bosque.pkl, scaler.pkl,
  features_list.pkl, config.pkl, position_encoder.pkl.
- src/merge_datasets.py → pipeline de datos. outputs/*.png → figuras.

⚠️ Esquema NUEVO (real_features): contribucion_gol, edad_primer_registro, primera_temporada,
temporadas_en_dataset. NO usar participacion_gol, pases_norm, rendimiento, edad_estimada_debut
(esquema viejo de notebooks). El modelo vigente usa 9 features: goles, asistencias, edad
+ dummies de posición (esquema decidido por experimento AUPRC).

## Comandos
- Tests: `python -m pytest tests -q` (8 tests de reglas de DS).
- Ejecutar notebooks con kernel Python 3.12 (python312, el único con nbclient + seaborn).
- Regenerar datos: `python src/merge_datasets.py` desde la raíz.
- Validar cambios: re-ejecutar la celda/notebook afectado y comparar outputs.

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

## Deudas técnicas conocidas (prioridad alta)
1. (resuelto) Notebooks de modelo: re-ejecutados con esquema 9 (sin arqueros, 729 filas).
2. (resuelto) L1 corregida: penalty='l1' + solver='saga' en train_model.py.
3. (resuelto) eda.ipynb: re-ejecutado completo (39 celdas, 0 errores).
4. src/scouting_pipeline.py NO existe (README lo referencia; queda un __pycache__ huérfano).
   Es la deuda principal: el pipeline de scouting está por construir.

## Completar el proyecto (orden sugerido)
1. (hecho) Re-ejecutar EDA con el esquema nuevo (incl. celdas 28–30).
2. (hecho) Unificar esquema en los notebooks de modelo (9 features) y corregir L1.
3. Pipeline de scouting: crear src/scouting_pipeline.py (aplicar modelo a candidatos_mercado
   → ranking → scouting_resultado.csv). Solucionar primero el cacheo de goles/asistencias
   de candidatos (hoy 0/None en FotMob): son features del esquema 9.
4. NLP: sentimiento de la hinchada (placeholders Reddit en .env).
5. Automatización semanal + publicación de tweet top-5.
6. Tests mínimos ya en pytest (8 reglas); documentar README al resto de cambios.

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
