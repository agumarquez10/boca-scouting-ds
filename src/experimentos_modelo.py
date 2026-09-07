import os
import sys
import warnings

import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingClassifier, RandomForestClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import classification_report, roc_auc_score
from sklearn.model_selection import GridSearchCV, StratifiedKFold
from sklearn.preprocessing import StandardScaler

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from posiciones import PositionEncoder
from train_model import (BASE_FEATURES, POS_COLUMNS, RANDOM_STATE, UMBRAL_TEST,
                         cargar_datos, construir_X, split_por_jugador)

warnings.filterwarnings('ignore')

TREE_EXTRA = ['edad_primer_registro', 'primera_temporada']


def preparar_datos():
    df = cargar_datos().reset_index(drop=True)
    encoder = PositionEncoder(POS_COLUMNS)
    test_mask = split_por_jugador(df)

    mask_extra = df[TREE_EXTRA].notna().all(axis=1).values
    df_tree = df[mask_extra].reset_index(drop=True)
    test_mask_tree = test_mask[mask_extra]
    print(f'Filas con extras disponibles: {mask_extra.sum()}/{len(df)}')

    return (df, df_tree, encoder, test_mask, test_mask_tree)


def oof_probas(estimador, X_train, y_train):
    skf = StratifiedKFold(n_splits=5, shuffle=True, random_state=RANDOM_STATE)
    oof = np.zeros(len(X_train))
    for train_idx, val_idx in skf.split(X_train, y_train):
        clf = estimador()
        X_tr = X_train.iloc[train_idx] if isinstance(X_train, pd.DataFrame) else X_train[train_idx]
        X_va = X_train.iloc[val_idx] if isinstance(X_train, pd.DataFrame) else X_train[val_idx]
        y_tr = y_train.iloc[train_idx] if isinstance(y_train, pd.Series) else y_train[train_idx]
        clf.fit(X_tr, y_tr)
        oof[val_idx] = clf.predict_proba(X_va)[:, 1]
    return oof


def mejor_umbral(y_true, y_prob):
    umbrales = np.unique(np.round(y_prob, 3))
    mejor_t = 0.5
    mejor_j = -np.inf
    for t in umbrales:
        pred = (y_prob >= t).astype(int)
        tn = ((y_true == 0) & (pred == 0)).sum()
        fp = ((y_true == 0) & (pred == 1)).sum()
        fn = ((y_true == 1) & (pred == 0)).sum()
        tp = ((y_true == 1) & (pred == 1)).sum()
        tpr = tp / (tp + fn) if (tp + fn) else 0
        fpr = fp / (fp + tn) if (fp + tn) else 0
        j = tpr - fpr
        if j > mejor_j:
            mejor_j = j
            mejor_t = t
    return float(mejor_t), mejor_j


def evaluar(nombre, y_test, y_prob, umbral):
    auc = roc_auc_score(y_test, y_prob)
    pred = (y_prob >= umbral).astype(int)
    rep = classification_report(y_test, pred, target_names=['No encaja', 'ADN Boca'], output_dict=True)
    print(f'  AUC test: {auc:.3f} | umbral {umbral:.2f} | precision ADN {rep["ADN Boca"]["precision"]:.2f} '
          f'| recall ADN {rep["ADN Boca"]["recall"]:.2f} | F1 ADN {rep["ADN Boca"]["f1-score"]:.2f}')
    return auc


def main():
    df, df_tree, encoder, test_mask, test_mask_tree = preparar_datos()
    y = df['etiqueta'].copy()
    train_mask = ~test_mask

    X_lr = construir_X(df, encoder)
    X_train, X_test = X_lr[train_mask], X_lr[test_mask]
    y_train, y_test = y[train_mask], y[test_mask]

    X_tree = construir_X(df_tree, encoder)
    y_tree = df_tree['etiqueta'].copy()
    tr_mask, te_mask = ~test_mask_tree, test_mask_tree
    Xt_train, Xt_test = X_tree[tr_mask], X_tree[te_mask]
    yt_train, yt_test = y_tree[tr_mask], y_tree[te_mask]

    resultados = {}

    print('\n[1] Baseline logistic (perfil puro + pos) — AUC OOF para umbral')
    scaler = StandardScaler().fit(X_train)
    lr = LogisticRegression(class_weight='balanced', C=1, max_iter=2000, random_state=RANDOM_STATE)
    oof_lr = oof_probas(lambda: LogisticRegression(class_weight='balanced', C=1, max_iter=2000, random_state=RANDOM_STATE), X_train, y_train)
    t_lr, _ = mejor_umbral(y_train, oof_lr)
    lr.fit(scaler.transform(X_train), y_train)
    resultados['logistic (ref)'] = evaluar('logistic', y_test, lr.predict_proba(scaler.transform(X_test))[:, 1], 0.5)

    print('\n[2] Random Forest perfil puro (baseline tree)')
    rf_puro = RandomForestClassifier(class_weight='balanced', n_estimators=200, max_depth=6,
                                     min_samples_leaf=5, max_features='sqrt', n_jobs=-1, random_state=RANDOM_STATE)
    oof_rf = oof_probas(lambda: RandomForestClassifier(class_weight='balanced', n_estimators=200, max_depth=6,
                                                       min_samples_leaf=5, max_features='sqrt', n_jobs=-1, random_state=RANDOM_STATE), X_train, y_train)
    rf_puro.fit(X_train, y_train)
    resultados['RF puro'] = evaluar('rf', y_test, rf_puro.predict_proba(X_test)[:, 1], 0.5)

    print('\n[3] EXPERIMENTO A: RF con extras (edad_primer_registro + primera_temporada)')
    rf_extra = RandomForestClassifier(class_weight='balanced', n_estimators=200, max_depth=6,
                                      min_samples_leaf=5, max_features='sqrt', n_jobs=-1, random_state=RANDOM_STATE)
    oof_extra = oof_probas(lambda: RandomForestClassifier(class_weight='balanced', n_estimators=200, max_depth=6,
                                                          min_samples_leaf=5, max_features='sqrt', n_jobs=-1, random_state=RANDOM_STATE), Xt_train, yt_train)
    rf_extra.fit(Xt_train, yt_train)
    auc3 = evaluar('rf_extra', yt_test, rf_extra.predict_proba(Xt_test)[:, 1], 0.5)
    resultados['RF + extras'] = auc3

    print('\n[4] EXPERIMENTO C: RF grid amplio + balanced_subsample (extras)')
    grid = GridSearchCV(RandomForestClassifier(n_estimators=200, random_state=RANDOM_STATE, n_jobs=-1),
                        {'max_depth': [4, 6, None], 'min_samples_leaf': [2, 5, 10],
                         'class_weight': ['balanced', 'balanced_subsample']},
                        cv=5, scoring='roc_auc')
    grid.fit(Xt_train, yt_train)
    mejor_rf = grid.best_estimator_
    oof_grid = oof_probas(lambda: RandomForestClassifier(n_estimators=200, random_state=RANDOM_STATE, n_jobs=-1).set_params(**grid.best_params_), Xt_train, yt_train)
    t_c, _ = mejor_umbral(yt_train, oof_grid)
    yc_prob = mejor_rf.predict_proba(Xt_test)[:, 1]
    print(f'  Mejores params: {grid.best_params_}')
    auc4 = evaluar('rf_grid', yt_test, yc_prob, 0.5)
    resultados['RF grid + subsample'] = auc4

    print('\n[5] EXPERIMENTO C: HistGradientBoosting (sample_weight balanceado)')
    n_clases = np.bincount(yt_train)
    sample_w = np.where(yt_train == 1, len(yt_train) / (2 * n_clases[1]), len(yt_train) / (2 * n_clases[0]))
    hgb = HistGradientBoostingClassifier(max_iter=200, learning_rate=0.05,
                                         max_depth=4, random_state=RANDOM_STATE)
    grid_hgb = GridSearchCV(HistGradientBoostingClassifier(random_state=RANDOM_STATE),
                            {'learning_rate': [0.03, 0.05, 0.1], 'max_depth': [3, 4, 6],
                             'max_iter': [100, 200]},
                            cv=5, scoring='roc_auc')
    grid_hgb.fit(Xt_train, yt_train, sample_weight=sample_w)
    mejor_hgb = grid_hgb.best_estimator_
    print(f'  Mejores params: {grid_hgb.best_params_}')
    auc5 = evaluar('hgb', yt_test, mejor_hgb.predict_proba(Xt_test)[:, 1], 0.5)
    resultados['HistGB'] = auc5

    print('\n[6] EXPERIMENTO B: umbral optimo (Youden J via OOF)')
    oof_hgb = oof_probas(lambda: HistGradientBoostingClassifier(**grid_hgb.best_params_, random_state=RANDOM_STATE),
                         Xt_train, yt_train)
    for nombre, oof, yp, yt, ftrain in [
        ('RF + extras', oof_extra, rf_extra.predict_proba(Xt_test)[:, 1], yt_test, yt_train),
        ('RF grid', oof_grid, yc_prob, yt_test, yt_train),
        ('HistGB', oof_hgb, mejor_hgb.predict_proba(Xt_test)[:, 1], yt_test, yt_train),
    ]:
        oof_aj = oof if len(oof) == len(ftrain) else ftrain
        t_opt, j = mejor_umbral(ftrain, oof_aj)
        print(f'  {nombre}: umbral optimo {t_opt:.2f} (J={j:.3f})')
        evaluar(nombre, yt, yp, t_opt)

    print('\n=== RESUMEN (umbral 0.5, AUC test) ===')
    for k, v in resultados.items():
        print(f'  {k}: {v:.3f}')


if __name__ == '__main__':
    main()