import json
import os
import sys
import warnings
from datetime import datetime, timezone

import joblib
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import seaborn as sns
from sklearn.ensemble import RandomForestClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import (average_precision_score, classification_report,
                             confusion_matrix, roc_auc_score)
from sklearn.model_selection import GridSearchCV, GroupKFold
from sklearn.preprocessing import StandardScaler
from sklearn.tree import DecisionTreeClassifier

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from calibracion import ajustar_platt, aplicar_platt, brier, ece
from posiciones import PositionEncoder

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(SCRIPT_DIR, '..', 'data')
MODEL_DIR = os.path.join(SCRIPT_DIR, '..', 'models')
OUTPUT_DIR = os.path.join(SCRIPT_DIR, '..', 'outputs')
os.makedirs(MODEL_DIR, exist_ok=True)
os.makedirs(OUTPUT_DIR, exist_ok=True)

warnings.filterwarnings('ignore')

# ============================================================
# Features del modelo (esquema 9): goles, asistencias, edad + dummies
# de posicion. La etiqueta es manual (sin formula), asi que
# goles/asistencias son features validas. rating queda fuera: no hay
# rating API-Football comparable para inferir en el mercado.
# ============================================================
BASE_FEATURES = ['goles', 'asistencias', 'edad']

GRUPOS = ['Defensor_central', 'Delantero', 'Extremo', 'Lateral',
          'Mediocampista_central', 'Mediocampista_ofensivo']
POS_COLUMNS = ['pos_' + g for g in GRUPOS]

UMBRAL_TEST = 2023
RANDOM_STATE = 42


def cargar_datos():
    df = pd.read_csv(os.path.join(DATA_DIR, 'adn_boca_real_features.csv'), encoding='utf-8-sig')
    df = df.dropna(subset=BASE_FEATURES + ['posicion'])
    # Excluir arqueros: no aportan info para predecir ADN Boca (perfil de cancha)
    antes = len(df)
    df = df[df['posicion'] != 'Goalkeeper'].copy()
    print(f'Excluidos {antes - len(df)} registros de arqueros (Goalkeeper)')
    return df


def construir_X(df, encoder):
    X_base = df[BASE_FEATURES].reset_index(drop=True)
    X_pos = encoder.transform(df['posicion']).reset_index(drop=True)
    return pd.concat([X_base, X_pos], axis=1)


def split_por_jugador(df):
    ultima_temp = df.groupby('nombre')['temporada'].max().rename('ultima_temporada')
    df_idx = df.reset_index(drop=True).merge(ultima_temp, on='nombre', how='left')
    test_mask = (df_idx['ultima_temporada'] >= UMBRAL_TEST).values
    return test_mask


def entrenar_modelo_principal(X_train, X_test, y_train, y_test, features, df, test_mask, grupos):
    X_train = X_train.reset_index(drop=True)
    X_test = X_test.reset_index(drop=True)
    y_train = y_train.reset_index(drop=True)
    y_test = y_test.reset_index(drop=True)
    df_train = df.loc[~test_mask].reset_index(drop=True)
    grupos = np.asarray(grupos)

    # Se elige C por AUPRC en snapshots recientes de jugadores no vistos.
    # El escalador se ajusta dentro de cada fold para evitar fuga de preprocessing.
    resultados_cv = []
    for c in [0.01, 0.1, 1, 10]:
        scores = []
        gkf = GroupKFold(n_splits=5)
        for idx_train, idx_val in gkf.split(X_train, y_train, groups=grupos):
            scaler_fold = StandardScaler().fit(X_train.iloc[idx_train])
            X_fold_train = scaler_fold.transform(X_train.iloc[idx_train])
            modelo_fold = LogisticRegression(
                penalty='l1', solver='saga', C=c, class_weight='balanced',
                max_iter=5000, random_state=RANDOM_STATE)
            modelo_fold.fit(X_fold_train, y_train.iloc[idx_train])

            val_df = df_train.iloc[idx_val]
            idx_recientes = (val_df.sort_values(['nombre', 'temporada'])
                             .groupby('nombre', as_index=False).tail(1).index.to_numpy())
            X_val = scaler_fold.transform(X_train.iloc[idx_recientes])
            prob_val = modelo_fold.predict_proba(X_val)[:, 1]
            scores.append(average_precision_score(y_train.iloc[idx_recientes], prob_val))
        resultados_cv.append((float(np.mean(scores)), float(np.std(scores, ddof=1)), c))

    cv_ap, cv_sd, mejor_c = max(resultados_cv, key=lambda r: r[0])
    scaler = StandardScaler().fit(X_train)
    X_train_scaled = scaler.transform(X_train)
    X_test_scaled = scaler.transform(X_test)
    modelo = LogisticRegression(
        penalty='l1', solver='saga', C=mejor_c, class_weight='balanced',
        max_iter=5000, random_state=RANDOM_STATE)
    modelo.fit(X_train_scaled, y_train)

    y_pred = modelo.predict(X_test_scaled)
    y_prob = modelo.predict_proba(X_test_scaled)[:, 1]
    auc = roc_auc_score(y_test, y_prob)
    ap = average_precision_score(y_test, y_prob)

    print('=== MODELO PRINCIPAL: LogisticRegression L1 (saga) ===')
    print(f'Mejor C: {mejor_c} | AUPRC CV latest-player: {cv_ap:.3f} ± {cv_sd:.3f}')
    print(f'AUC-ROC test: {auc:.3f} | AUPRC test (filas): {ap:.3f}')
    reporte = classification_report(y_test, y_pred, target_names=['No encaja', 'ADN Boca'],
                                    output_dict=True, zero_division=0)
    print(classification_report(y_test, y_pred, target_names=['No encaja', 'ADN Boca'],
                                zero_division=0))

    cm = confusion_matrix(y_test, y_pred)
    fig, ax = plt.subplots(figsize=(6, 5))
    sns.heatmap(cm, annot=True, fmt='d', cmap='Blues', ax=ax,
                xticklabels=['No encaja', 'ADN Boca'], yticklabels=['No encaja', 'ADN Boca'])
    ax.set_title('Matriz de confusion (test - jugadores nuevos)')
    ax.set_ylabel('Real')
    ax.set_xlabel('Prediccion')
    plt.tight_layout()
    plt.savefig(os.path.join(OUTPUT_DIR, '20_matriz_confusion.png'), dpi=150, bbox_inches='tight')
    plt.close(fig)

    coeficientes = pd.Series(modelo.coef_[0], index=features).sort_values(ascending=True)
    fig, ax = plt.subplots(figsize=(9, 6))
    colors = ['#2ecc71' if v > 0 else '#e74c3c' for v in coeficientes.values]
    coeficientes.plot(kind='barh', ax=ax, color=colors, edgecolor='black')
    ax.set_title('Coeficientes del modelo (impacto en ADN Boca)', fontsize=13, fontweight='bold')
    ax.set_xlabel('Coeficiente')
    ax.axvline(x=0, color='black', linewidth=0.5)
    plt.tight_layout()
    plt.savefig(os.path.join(OUTPUT_DIR, '21_coeficientes_modelo.png'), dpi=150, bbox_inches='tight')
    plt.close(fig)

    gkf = GroupKFold(n_splits=5)
    oof = np.zeros(len(X_train))
    for train_idx, val_idx in gkf.split(X_train, y_train, groups=grupos):
        scaler_fold = StandardScaler().fit(X_train.iloc[train_idx])
        X_fold_train = scaler_fold.transform(X_train.iloc[train_idx])
        X_fold_val = scaler_fold.transform(X_train.iloc[val_idx])
        lr_fold = LogisticRegression(
            penalty='l1', solver='saga', C=mejor_c, class_weight='balanced',
            max_iter=5000, random_state=RANDOM_STATE)
        lr_fold.fit(X_fold_train, y_train.iloc[train_idx])
        oof[val_idx] = lr_fold.predict_proba(X_fold_val)[:, 1]
    print(f'OOF AUC (GroupKFold por jugador): {roc_auc_score(y_train, oof):.3f}')
    print(f'OOF AUPRC (filas): {average_precision_score(y_train, oof):.3f}')

    # Platt sobre OOF por jugador: convierte el score reponderado por
    # class_weight en P(etiqueta manual | features) bajo el train.
    calibrador = ajustar_platt(oof, y_train.to_numpy(), reporte='OOF train por jugador')
    prob_cal = aplicar_platt(y_prob, calibrador)
    brier_sin = brier(y_test, y_prob)
    brier_con = brier(y_test, prob_cal)
    ece_sin = ece(y_test, y_prob, bins=5)
    ece_con = ece(y_test, prob_cal, bins=5)
    print(f'Platt: a={calibrador["a"]:.4f} b={calibrador["b"]:.4f} | '
          f'Brier test {brier_sin:.4f} -> {brier_con:.4f} | '
          f'ECE(5) test {ece_sin:.4f} -> {ece_con:.4f}')

    metricas = {
        'cv_auprc': round(cv_ap, 4),
        'cv_auprc_std': round(cv_sd, 4),
        'cv_n_splits': 5,
        'cv_agrupacion': 'GroupKFold por jugador (n_splits=5)',
        'cv_criterio': 'AUPRC sobre el ultimo registro de cada jugador de cada fold',
        'C': mejor_c,
        'test_auc_roc': round(auc, 4),
        'test_auprc_filas': round(ap, 4),
        'brier_sin_calibrar': round(brier_sin, 4),
        'brier_calibrado': round(brier_con, 4),
        'ece_sin_calibrar': round(ece_sin, 4),
        'ece_calibrado': round(ece_con, 4),
        'ece_bins': 5,
        'platt_a': round(calibrador['a'], 4),
        'platt_b': round(calibrador['b'], 4),
        'por_clase': {
            'no_encaja': {
                'precision': round(reporte['No encaja']['precision'], 4),
                'recall': round(reporte['No encaja']['recall'], 4),
                'f1': round(reporte['No encaja']['f1-score'], 4),
                'soporte': int(reporte['No encaja']['support']),
            },
            'adn_boca': {
                'precision': round(reporte['ADN Boca']['precision'], 4),
                'recall': round(reporte['ADN Boca']['recall'], 4),
                'f1': round(reporte['ADN Boca']['f1-score'], 4),
                'soporte': int(reporte['ADN Boca']['support']),
            },
        },
    }

    return modelo, scaler, y_pred, y_prob, oof, auc, calibrador, metricas


def guardar_scouting(df, features, test_mask, oof, y_prob, calibrador):
    # goles/asistencias vienen del CSV de features (df); ya no hace falta
    # mergear contra el raw etiquetado.
    resultado = df[['nombre', 'temporada', 'posicion', 'edad', 'partidos',
                    'goles', 'asistencias', 'etiqueta']].copy()
    resultado['probabilidad'] = 0.0
    resultado['probabilidad_adn'] = 0.0
    resultado['prediccion'] = 0
    resultado['fuente'] = ''
    resultado.loc[~test_mask, 'probabilidad'] = oof
    resultado.loc[~test_mask, 'probabilidad_adn'] = aplicar_platt(oof, calibrador)
    resultado.loc[~test_mask, 'prediccion'] = (oof >= 0.5).astype(int)
    resultado.loc[~test_mask, 'fuente'] = 'cv'
    resultado.loc[test_mask, 'probabilidad'] = y_prob
    resultado.loc[test_mask, 'probabilidad_adn'] = aplicar_platt(y_prob, calibrador)
    resultado.loc[test_mask, 'prediccion'] = (y_prob >= 0.5).astype(int)
    resultado.loc[test_mask, 'fuente'] = 'test'
    resultado = resultado.sort_values('probabilidad', ascending=False)
    resultado.to_csv(os.path.join(DATA_DIR, 'scouting_resultado_historico.csv'),
                     index=False, encoding='utf-8-sig')
    print(f'\nscouting_resultado_historico.csv guardado ({len(resultado)} filas)')
    return resultado


def entrenar_modelo_arbol(X_train, X_test, y_train, y_test, grupos):
    print('\n=== MODELO ALTERNATIVO: Arbol de decision (class_weight balanced) ===')
    param_grid = {'max_depth': [3, 4, 5, 6], 'min_samples_leaf': [5, 10, 20]}
    dt = DecisionTreeClassifier(class_weight='balanced', random_state=RANDOM_STATE,
                                max_features='sqrt')
    grid = GridSearchCV(dt, param_grid, cv=GroupKFold(n_splits=5), scoring='roc_auc')
    grid.fit(X_train, y_train, groups=grupos)
    modelo = grid.best_estimator_
    y_pred = modelo.predict(X_test)
    y_prob = modelo.predict_proba(X_test)[:, 1]
    print(f'Mejor params: {grid.best_params_} | AUC test: {roc_auc_score(y_test, y_prob):.3f}')
    print(classification_report(y_test, y_pred, target_names=['No encaja', 'ADN Boca']))
    return modelo


def entrenar_modelo_bosque(X_train, X_test, y_train, y_test, grupos):
    print('\n=== MODELO ALTERNATIVO: Random Forest (class_weight balanced) ===')
    param_grid = {'n_estimators': [200], 'max_depth': [4, 6, 8], 'min_samples_leaf': [5, 10]}
    rf = RandomForestClassifier(class_weight='balanced', random_state=RANDOM_STATE,
                                max_features='sqrt', n_jobs=-1)
    grid = GridSearchCV(rf, param_grid, cv=GroupKFold(n_splits=5), scoring='roc_auc')
    grid.fit(X_train, y_train, groups=grupos)
    modelo = grid.best_estimator_
    y_pred = modelo.predict(X_test)
    y_prob = modelo.predict_proba(X_test)[:, 1]
    print(f'Mejor params: {grid.best_params_} | AUC test: {roc_auc_score(y_test, y_prob):.3f}')
    print(classification_report(y_test, y_pred, target_names=['No encaja', 'ADN Boca']))
    return modelo


def guardar_evaluacion(metricas, df, test_mask, features, calibrador, modelo_dir=None):
    """Persiste las metricas del entrenamiento en `models/evaluacion.json`.

    La landing lee este archivo: asi las metricas que publica salen del
    entrenamiento real y no de numeros escritos a mano en la pagina.
    """
    modelo_dir = modelo_dir or MODEL_DIR
    df_test = df.loc[test_mask]
    evaluacion = {
        'generado': datetime.now(timezone.utc).isoformat(timespec='seconds'),
        'modelo': {
            'tipo': 'LogisticRegression',
            'penalty': 'l1',
            'solver': 'saga',
            'C': metricas['C'],
            'class_weight': 'balanced',
            'features': list(features),
        },
        'split': {
            'regla': 'los jugadores cuya ultima temporada es >= 2023 van a test; '
                     'el resto entrena. El split es por jugador, nunca por fila.',
            'umbral_test': UMBRAL_TEST,
            'n_train_filas': int((~test_mask).sum()),
            'n_train_jugadores': int(df.loc[~test_mask, 'nombre'].nunique()),
            'n_test_filas': int(test_mask.sum()),
            'n_test_jugadores': int(df_test['nombre'].nunique()),
            'temporadas_test': sorted(int(t) for t in df_test['temporada'].unique()),
            'n_test_filas_temporada_umbral': int((df_test['temporada'] >= UMBRAL_TEST).sum()),
        },
        'cv': {
            'auprc': metricas['cv_auprc'],
            'auprc_std': metricas['cv_auprc_std'],
            'n_splits': metricas['cv_n_splits'],
            'agrupacion': metricas['cv_agrupacion'],
            'criterio': metricas['cv_criterio'],
        },
        'test': {
            'auc_roc': metricas['test_auc_roc'],
            'auprc_filas': metricas['test_auprc_filas'],
        },
        'calibracion': {
            'metodo': calibrador.get('metodo', 'platt_sigmoid'),
            'a': metricas['platt_a'],
            'b': metricas['platt_b'],
            'brier_sin_calibrar': metricas['brier_sin_calibrar'],
            'brier_calibrado': metricas['brier_calibrado'],
            'ece_sin_calibrar': metricas['ece_sin_calibrar'],
            'ece_calibrado': metricas['ece_calibrado'],
            'ece_bins': metricas['ece_bins'],
        },
        'por_clase': metricas['por_clase'],
    }
    ruta = os.path.join(modelo_dir, 'evaluacion.json')
    os.makedirs(modelo_dir, exist_ok=True)
    with open(ruta, 'w', encoding='utf-8') as f:
        json.dump(evaluacion, f, ensure_ascii=False, indent=2)
    print(f'\nmodels/evaluacion.json guardado ({ruta})')
    return ruta


def main():
    df = cargar_datos()
    encoder = PositionEncoder(POS_COLUMNS)
    features = BASE_FEATURES + POS_COLUMNS

    X = construir_X(df, encoder)
    y = df['etiqueta'].copy()
    test_mask = split_por_jugador(df)
    train_mask = ~test_mask

    X_train, X_test = X[train_mask], X[test_mask]
    y_train, y_test = y[train_mask], y[test_mask]
    grupos = df['nombre'].values[train_mask]
    print(f'Train: {len(X_train)} registros, {df[train_mask]["nombre"].nunique()} jugadores')
    print(f'Test:  {len(X_test)} registros, {df[test_mask]["nombre"].nunique()} jugadores')

    (modelo, scaler, y_pred, y_prob, oof, auc,
     calibrador, metricas) = entrenar_modelo_principal(
        X_train, X_test, y_train, y_test, features, df, test_mask, grupos)

    guardar_scouting(df, features, test_mask, oof, y_prob, calibrador)
    guardar_evaluacion(metricas, df, test_mask, features, calibrador)

    modelo_arbol = entrenar_modelo_arbol(X_train, X_test, y_train, y_test, grupos)
    modelo_bosque = entrenar_modelo_bosque(X_train, X_test, y_train, y_test, grupos)

    joblib.dump(modelo, os.path.join(MODEL_DIR, 'modelo_adn_boca.pkl'))
    joblib.dump(scaler, os.path.join(MODEL_DIR, 'scaler.pkl'))
    joblib.dump(features, os.path.join(MODEL_DIR, 'features_list.pkl'))
    joblib.dump(encoder, os.path.join(MODEL_DIR, 'position_encoder.pkl'))
    joblib.dump(modelo, os.path.join(MODEL_DIR, 'modelo_logistic_l1.pkl'))
    joblib.dump(modelo_arbol, os.path.join(MODEL_DIR, 'modelo_arbol.pkl'))
    joblib.dump(modelo_bosque, os.path.join(MODEL_DIR, 'modelo_bosque.pkl'))
    joblib.dump({'features': BASE_FEATURES, 'pos_columns': POS_COLUMNS},
                os.path.join(MODEL_DIR, 'config.pkl'))
    joblib.dump(calibrador, os.path.join(MODEL_DIR, 'calibrador.pkl'))

    for f in ['modelo_adn_boca.pkl', 'scaler.pkl', 'features_list.pkl',
              'position_encoder.pkl', 'modelo_logistic_l1.pkl', 'modelo_arbol.pkl',
              'modelo_bosque.pkl', 'config.pkl', 'calibrador.pkl']:
        print(f'  models/{f} guardado')
    print(f'AUC-ROC test: {auc:.3f}')


if __name__ == '__main__':
    main()
