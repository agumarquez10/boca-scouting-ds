import os
import sys
import warnings

import joblib
import numpy as np
import pandas as pd
from sklearn.calibration import CalibratedClassifierCV
from sklearn.ensemble import (ExtraTreesClassifier, HistGradientBoostingClassifier,
                              RandomForestClassifier, VotingClassifier)
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import roc_auc_score
from sklearn.model_selection import GridSearchCV, StratifiedKFold
from sklearn.naive_bayes import GaussianNB
from sklearn.neighbors import KNeighborsClassifier
from sklearn.neural_network import MLPClassifier
from sklearn.preprocessing import StandardScaler
from sklearn.svm import SVC
from sklearn.tree import DecisionTreeClassifier

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from posiciones import PositionEncoder
from train_model import BASE_FEATURES, POS_COLUMNS, RANDOM_STATE

warnings.filterwarnings('ignore')

DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'data')


def cargar_datos():
    df = pd.read_csv(os.path.join(DATA_DIR, 'adn_boca_real_features.csv'), encoding='utf-8-sig')
    df = df.dropna(subset=BASE_FEATURES + ['posicion']).reset_index(drop=True)
    df = df[df['posicion'] != 'Goalkeeper'].reset_index(drop=True)
    return df


def split_por_jugador(df):
    ultima_temp = df.groupby('nombre')['temporada'].max().rename('ultima_temporada')
    df_idx = df.reset_index(drop=True).merge(ultima_temp, on='nombre', how='left')
    return (df_idx['ultima_temporada'] >= 2023).values


def balanced_weights(y):
    n = len(y)
    c0 = int(np.sum(y == 0))
    c1 = int(np.sum(y == 1))
    return np.where(y == 1, n / (2 * c1), n / (2 * c0))


def oof_probas(estimador, X, y, sample_weight=None):
    skf = StratifiedKFold(n_splits=5, shuffle=True, random_state=RANDOM_STATE)
    oof = np.zeros(len(X))
    for tr_idx, val_idx in skf.split(X, y):
        clf = estimador()
        if hasattr(clf, 'sample_weight'):
            clf.fit(X.iloc[tr_idx], y.iloc[tr_idx], sample_weight=None)
        elif sample_weight is not None:
            clf.fit(X.iloc[tr_idx], y.iloc[tr_idx], sample_weight=sample_weight[tr_idx])
        else:
            clf.fit(X.iloc[tr_idx], y.iloc[tr_idx])
        oof[val_idx] = clf.predict_proba(X.iloc[val_idx])[:, 1]
    return oof


MODELOS = []

MODELOS.append({
    'nombre': 'Logistic (baseline)',
    'factory': lambda: LogisticRegression(class_weight='balanced', max_iter=2000, random_state=RANDOM_STATE),
    'grid': {'C': [0.01, 0.1, 1, 10, 100]},
    'scale': True,
    'weights': None,
})

MODELOS.append({
    'nombre': 'Logistic L1',
    'factory': lambda: LogisticRegression(penalty='l1', solver='saga', class_weight='balanced',
                                          max_iter=3000, random_state=RANDOM_STATE),
    'grid': {'C': [0.01, 0.1, 1, 10]},
    'scale': True,
    'weights': None,
})

MODELOS.append({
    'nombre': 'Decision Tree',
    'factory': lambda: DecisionTreeClassifier(class_weight='balanced', random_state=RANDOM_STATE,
                                              max_features='sqrt'),
    'grid': {'max_depth': [3, 4, 5, 6], 'min_samples_leaf': [5, 10, 20]},
    'scale': False,
    'weights': None,
})

MODELOS.append({
    'nombre': 'Random Forest',
    'factory': lambda: RandomForestClassifier(n_estimators=300, random_state=RANDOM_STATE,
                                              n_jobs=-1, class_weight='balanced'),
    'grid': {'max_depth': [4, 6, None], 'min_samples_leaf': [2, 5, 10]},
    'scale': False,
    'weights': None,
})

MODELOS.append({
    'nombre': 'Extra Trees',
    'factory': lambda: ExtraTreesClassifier(n_estimators=300, random_state=RANDOM_STATE,
                                            n_jobs=-1, class_weight='balanced'),
    'grid': {'max_depth': [4, 6, None], 'min_samples_leaf': [2, 5, 10]},
    'scale': False,
    'weights': None,
})

MODELOS.append({
    'nombre': 'HistGradientBoosting',
    'factory': lambda: HistGradientBoostingClassifier(random_state=RANDOM_STATE),
    'grid': {'learning_rate': [0.03, 0.05, 0.1], 'max_depth': [3, 4, 6], 'max_iter': [100, 200]},
    'scale': False,
    'weights': 'balanced',
})

MODELOS.append({
    'nombre': 'XGBoost',
    'factory': lambda: XGBClassifier(n_estimators=300, n_jobs=-1, random_state=RANDOM_STATE,
                                     eval_metric='logloss'),
    'grid': {'max_depth': [3, 4, 6], 'learning_rate': [0.03, 0.05, 0.1],
             'scale_pos_weight': [1.0]},
    'scale': False,
    'weights': None,
})

MODELOS.append({
    'nombre': 'KNN',
    'factory': lambda: KNeighborsClassifier(),
    'grid': {'n_neighbors': [5, 10, 20], 'weights': ['uniform', 'distance']},
    'scale': True,
    'weights': None,
})

MODELOS.append({
    'nombre': 'SVM RBF',
    'factory': lambda: SVC(class_weight='balanced', probability=True, random_state=RANDOM_STATE),
    'grid': {'C': [0.5, 1, 5], 'gamma': ['scale']},
    'scale': True,
    'weights': None,
})

MODELOS.append({
    'nombre': 'Naive Bayes',
    'factory': lambda: GaussianNB(),
    'grid': {'var_smoothing': [1e-9, 1e-6, 1e-3]},
    'scale': True,
    'weights': None,
})

MODELOS.append({
    'nombre': 'MLP (clasico)',
    'factory': lambda: MLPClassifier(hidden_layer_sizes=(50, 25), max_iter=1500,
                                     random_state=RANDOM_STATE),
    'grid': {'alpha': [0.001, 0.01, 0.1]},
    'scale': True,
    'weights': None,
})


def main():
    df = cargar_datos()
    encoder = PositionEncoder(POS_COLUMNS)
    X_base = df[BASE_FEATURES].reset_index(drop=True)
    X_pos = encoder.transform(df['posicion']).reset_index(drop=True)
    X = pd.concat([X_base, X_pos], axis=1)
    y = df['etiqueta'].astype(int).reset_index(drop=True)
    test_mask = split_por_jugador(df)
    train_mask = ~test_mask

    X_tr, X_te = X[train_mask], X[test_mask]
    y_tr, y_te = y[train_mask], y[test_mask]
    print(f'Train: {len(X_tr)} | Test: {len(X_te)} (ADN: {int(y_te.sum())}/{len(y_te)})')

    resultados = []
    skf = StratifiedKFold(n_splits=5, shuffle=True, random_state=RANDOM_STATE)

    for cfg in MODELOS:
        nombre = cfg['nombre']
        scaler_tr = StandardScaler().fit(X_tr) if cfg['scale'] else None
        X_tr_fit = pd.DataFrame(scaler_tr.transform(X_tr), columns=X_tr.columns) if cfg['scale'] else X_tr
        X_te_fit = pd.DataFrame(scaler_tr.transform(X_te), columns=X_te.columns) if cfg['scale'] else X_te

        pesos = balanced_weights(y_tr.values) if cfg['weights'] == 'balanced' else None

        grid = GridSearchCV(cfg['factory'](), cfg['grid'], cv=skf, scoring='roc_auc')
        if pesos is not None:
            grid.fit(X_tr_fit, y_tr, sample_weight=pesos)
        else:
            grid.fit(X_tr_fit, y_tr)

        mejor = grid.best_estimator_
        best_params = grid.best_params_

        oof = np.zeros(len(X_tr))
        for tr_idx, val_idx in skf.split(X_tr_fit, y_tr):
            clf = cfg['factory']().set_params(**best_params)
            w = pesos[tr_idx] if pesos is not None else None
            if w is not None:
                clf.fit(X_tr_fit.iloc[tr_idx], y_tr.iloc[tr_idx], sample_weight=w)
            else:
                clf.fit(X_tr_fit.iloc[tr_idx], y_tr.iloc[tr_idx])
            oof[val_idx] = clf.predict_proba(X_tr_fit.iloc[val_idx])[:, 1]

        y_prob = mejor.predict_proba(X_te_fit)[:, 1]
        resultado = {
            'modelo': nombre,
            'auc_test': roc_auc_score(y_te, y_prob),
            'oof_auc': roc_auc_score(y_tr, oof),
            'params': best_params,
        }
        resultados.append(resultado)
        print(f'  {nombre:22s} | OOF {resultado["oof_auc"]:.3f} | TEST {resultado["auc_test"]:.3f} | {best_params}')

    print('\n=== RANKING (por OOF AUC, desempate AUC test) ===')
    for r in sorted(resultados, key=lambda x: (x['oof_auc'], x['auc_test']), reverse=True):
        flag = ' <<<' if r['oof_auc'] == max(x['oof_auc'] for x in resultados) else ''
        print(f'  {r["modelo"]:22s} | OOF {r["oof_auc"]:.3f} | TEST {r["auc_test"]:.3f}{flag}')


if __name__ == '__main__':
    from xgboost import XGBClassifier
    main()