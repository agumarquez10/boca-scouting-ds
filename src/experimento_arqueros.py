import os
import sys
import warnings

import joblib
import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import classification_report, roc_auc_score
from sklearn.model_selection import GridSearchCV, StratifiedKFold
from sklearn.preprocessing import StandardScaler

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from posiciones import PositionEncoder
from train_model import (BASE_FEATURES, POS_COLUMNS, RANDOM_STATE, UMBRAL_TEST)

warnings.filterwarnings('ignore')

DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'data')


def cargar_datos(incluir_arqueros):
    df = pd.read_csv(os.path.join(DATA_DIR, 'adn_boca_real_features.csv'), encoding='utf-8-sig')
    df = df.dropna(subset=BASE_FEATURES + ['posicion']).reset_index(drop=True)
    if not incluir_arqueros:
        df = df[df['posicion'] != 'Goalkeeper'].reset_index(drop=True)
    return df


def split_por_jugador(df):
    ultima_temp = df.groupby('nombre')['temporada'].max().rename('ultima_temporada')
    df_idx = df.reset_index(drop=True).merge(ultima_temp, on='nombre', how='left')
    return (df_idx['ultima_temporada'] >= UMBRAL_TEST).values


def entrenar(df):
    encoder = PositionEncoder(POS_COLUMNS)
    X_base = df[BASE_FEATURES].reset_index(drop=True)
    X_pos = encoder.transform(df['posicion']).reset_index(drop=True)
    X = pd.concat([X_base, X_pos], axis=1)
    y = df['etiqueta'].astype(int).reset_index(drop=True)
    test_mask = split_por_jugador(df)
    train_mask = ~test_mask

    X_tr, X_te = X[train_mask], X[test_mask]
    y_tr, y_te = y[train_mask], y[test_mask]

    scaler = StandardScaler().fit(X_tr)
    lr = LogisticRegression(class_weight='balanced', max_iter=2000, random_state=RANDOM_STATE)
    grid = GridSearchCV(lr, {'C': [0.01, 0.1, 1, 10, 100]}, cv=5, scoring='roc_auc')
    grid.fit(scaler.transform(X_tr), y_tr)
    modelo = grid.best_estimator_
    y_prob = modelo.predict_proba(scaler.transform(X_te))[:, 1]
    y_pred = modelo.predict(scaler.transform(X_te))
    auc = roc_auc_score(y_te, y_prob)

    skf = StratifiedKFold(n_splits=5, shuffle=True, random_state=RANDOM_STATE)
    oof = np.zeros(len(X_tr))
    for tr_idx, val_idx in skf.split(scaler.transform(X_tr), y_tr):
        lr_fold = LogisticRegression(class_weight='balanced', C=modelo.C,
                                     max_iter=2000, random_state=RANDOM_STATE)
        lr_fold.fit(scaler.transform(X_tr)[tr_idx], y_tr.iloc[tr_idx])
        oof[val_idx] = lr_fold.predict_proba(scaler.transform(X_tr)[val_idx])[:, 1]
    oof_auc = roc_auc_score(y_tr, oof)

    rep = classification_report(y_te, y_pred, target_names=['No encaja', 'ADN Boca'])
    n_adn_test = int(y_te.sum())
    n_total_test = len(y_te)
    n_jug_train = df[train_mask]['nombre'].nunique()
    n_jug_test = df[test_mask]['nombre'].nunique()
    return {
        'auc': auc, 'oof': oof_auc, 'report': rep,
        'n_train': len(X_tr), 'n_test': len(X_te), 'n_adn_test': n_adn_test,
        'n_total_test': n_total_test, 'jug_train': n_jug_train, 'jug_test': n_jug_test,
        'mejor_c': grid.best_params_['C'], 'adn_ratio_train': float(y_tr.mean()),
    }


def main():
    for incluir in [True, False]:
        tag = 'CON arqueros' if incluir else 'SIN arqueros'
        df = cargar_datos(incluir)
        r = entrenar(df)
        print('=' * 70)
        print(f'MODELO {tag}  ({len(df)} registros, {df["nombre"].nunique()} jugadores)')
        print(f'Train: {r["n_train"]} registros ({r["jug_train"]} jug, ratio ADN {r["adn_ratio_train"]:.2f})')
        print(f'Test:  {r["n_test"]} registros ({r["jug_test"]} jug, {r["n_adn_test"]} ADN/{r["n_total_test"]})')
        print(f'Mejor C: {r["mejor_c"]} | OOF AUC: {r["oof"]:.3f} | AUC test: {r["auc"]:.3f}')
        print(r['report'])


if __name__ == '__main__':
    main()