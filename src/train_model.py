import os
import sys
import warnings

import joblib
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import seaborn as sns
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import classification_report, confusion_matrix, roc_auc_score
from sklearn.model_selection import GridSearchCV, StratifiedKFold
from sklearn.preprocessing import StandardScaler

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from posiciones import PositionEncoder

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(SCRIPT_DIR, '..', 'data')
MODEL_DIR = os.path.join(SCRIPT_DIR, '..', 'models')
OUTPUT_DIR = os.path.join(SCRIPT_DIR, '..', 'outputs')
os.makedirs(MODEL_DIR, exist_ok=True)
os.makedirs(OUTPUT_DIR, exist_ok=True)

warnings.filterwarnings('ignore')

# ============================================================
# Features FINALES: perfil puro, SIN reconstruccion del label.
# La etiqueta se define (rating>=7.0) & (goles+asistencias>=3);
# por eso NO se usan goles, asistencias, goles_por_partido,
# contribucion_gol ni derivados: serian copia directa del umbral.
# Tampoco se usan pares con |r|>0.8 (edad vs edad_primer_registro;
# experiencia == temporadas_en_dataset).
# ============================================================
BASE_FEATURES = [
    'pases_precisos',
    'edad',
    'temporadas_en_dataset',
    'partidos_por_temporada',
    'perfil_ofensivo',
]

GRUPOS = ['Defensor_central', 'Delantero', 'Extremo', 'Lateral',
          'Mediocampista_central', 'Mediocampista_ofensivo']
POS_COLUMNS = ['pos_' + g for g in GRUPOS]

UMBRAL_TEST = 2023
RANDOM_STATE = 42


def cargar_datos():
    df = pd.read_csv(os.path.join(DATA_DIR, 'adn_boca_real_features.csv'), encoding='utf-8-sig')
    df = df.dropna(subset=BASE_FEATURES + ['posicion'])
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


def entrenar_modelo_principal(X_train, X_test, y_train, y_test, features, df, test_mask):
    scaler = StandardScaler().fit(X_train)
    X_train_scaled = scaler.transform(X_train)
    X_test_scaled = scaler.transform(X_test)

    param_grid = {'C': [0.01, 0.1, 1, 10, 100]}
    lr = LogisticRegression(class_weight='balanced', max_iter=2000, random_state=RANDOM_STATE)
    grid = GridSearchCV(lr, param_grid, cv=5, scoring='roc_auc')
    grid.fit(X_train_scaled, y_train)
    modelo = grid.best_estimator_

    y_pred = modelo.predict(X_test_scaled)
    y_prob = modelo.predict_proba(X_test_scaled)[:, 1]
    auc = roc_auc_score(y_test, y_prob)

    print('=== MODELO PRINCIPAL: LogisticRegression balanceada (perfil puro) ===')
    print(f'Mejor C: {grid.best_params_["C"]} | Mejor AUC (CV): {grid.best_score_:.3f}')
    print(f'AUC-ROC test: {auc:.3f}')
    print(classification_report(y_test, y_pred, target_names=['No encaja', 'ADN Boca']))

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

    skf = StratifiedKFold(n_splits=5, shuffle=True, random_state=RANDOM_STATE)
    oof = np.zeros(len(X_train))
    for train_idx, val_idx in skf.split(X_train_scaled, y_train):
        lr_fold = LogisticRegression(class_weight='balanced', C=modelo.C,
                                     max_iter=2000, random_state=RANDOM_STATE)
        lr_fold.fit(X_train_scaled[train_idx], y_train.iloc[train_idx])
        oof[val_idx] = lr_fold.predict_proba(X_train_scaled[val_idx])[:, 1]
    print(f'OOF AUC: {roc_auc_score(y_train, oof):.3f}')

    return modelo, scaler, y_pred, y_prob, oof, auc


def guardar_scouting(df, features, test_mask, oof, y_prob):
    resultado = df[['nombre', 'temporada', 'posicion', 'edad', 'partidos',
                    'goles', 'asistencias', 'etiqueta']].copy()
    resultado['probabilidad'] = 0.0
    resultado['prediccion'] = 0
    resultado['fuente'] = ''
    resultado.loc[~test_mask, 'probabilidad'] = oof
    resultado.loc[~test_mask, 'prediccion'] = (oof >= 0.5).astype(int)
    resultado.loc[~test_mask, 'fuente'] = 'cv'
    resultado.loc[test_mask, 'probabilidad'] = y_prob
    resultado.loc[test_mask, 'prediccion'] = (y_prob >= 0.5).astype(int)
    resultado.loc[test_mask, 'fuente'] = 'test'
    resultado = resultado.sort_values('probabilidad', ascending=False)
    resultado.to_csv(os.path.join(DATA_DIR, 'scouting_resultado_historico.csv'),
                     index=False, encoding='utf-8-sig')
    print(f'\nscouting_resultado_historico.csv guardado ({len(resultado)} filas)')
    return resultado


def entrenar_modelo_l1(X_train, X_test, y_train, y_test):
    print('\n=== MODELO ALTERNATIVO: LogisticRegression L1 (saga) ===')
    param_grid = {'C': [0.01, 0.1, 1, 10]}
    lr = LogisticRegression(penalty='l1', solver='saga', class_weight='balanced',
                            max_iter=3000, random_state=RANDOM_STATE)
    grid = GridSearchCV(lr, param_grid, cv=5, scoring='roc_auc')
    grid.fit(X_train, y_train)
    modelo = grid.best_estimator_
    y_pred = modelo.predict(X_test)
    y_prob = modelo.predict_proba(X_test)[:, 1]
    print(f'Mejor C: {grid.best_params_["C"]} | AUC test: {roc_auc_score(y_test, y_prob):.3f}')
    print(classification_report(y_test, y_pred, target_names=['No encaja', 'ADN Boca']))
    return modelo


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
    print(f'Train: {len(X_train)} registros, {df[train_mask]["nombre"].nunique()} jugadores')
    print(f'Test:  {len(X_test)} registros, {df[test_mask]["nombre"].nunique()} jugadores')

    modelo, scaler, y_pred, y_prob, oof, auc = entrenar_modelo_principal(
        X_train, X_test, y_train, y_test, features, df, test_mask)

    guardar_scouting(df, features, test_mask, oof, y_prob)

    modelo_l1 = entrenar_modelo_l1(X_train, X_test, y_train, y_test)

    joblib.dump(modelo, os.path.join(MODEL_DIR, 'modelo_adn_boca.pkl'))
    joblib.dump(scaler, os.path.join(MODEL_DIR, 'scaler.pkl'))
    joblib.dump(features, os.path.join(MODEL_DIR, 'features_list.pkl'))
    joblib.dump(encoder, os.path.join(MODEL_DIR, 'position_encoder.pkl'))
    joblib.dump(modelo_l1, os.path.join(MODEL_DIR, 'modelo_logistic_l1.pkl'))
    joblib.dump({'features': BASE_FEATURES, 'pos_columns': POS_COLUMNS},
                os.path.join(MODEL_DIR, 'config.pkl'))

    for f in ['modelo_adn_boca.pkl', 'scaler.pkl', 'features_list.pkl',
              'position_encoder.pkl', 'modelo_logistic_l1.pkl', 'config.pkl']:
        print(f'  models/{f} guardado')
    print(f'AUC-ROC test: {auc:.3f}')


if __name__ == '__main__':
    main()
