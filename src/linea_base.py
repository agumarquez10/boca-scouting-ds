"""Linea base del modelo ADN: compara el score L1 contra scores mas simples.

Dos mediciones:
  1. Prueba (split por jugador): usa los artefactos guardados (sin reentrenar) y
     un bootstrap por jugador para los intervalos.
  2. Validacion cruzada repetida sobre todo el dataset: StratifiedGroupKFold con
     varias semillas, reentrenando el modelo dentro de cada fold.

No modifica los `.pkl` de produccion. Escribe `models/linea_base.json`, que la
landing lee.
"""

import json
import os
import sys
from datetime import datetime, timezone

import joblib
import numpy as np
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import average_precision_score, roc_auc_score
from sklearn.model_selection import StratifiedGroupKFold
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, SCRIPT_DIR)

import train_model as tm
from rutas import dir_models

BOOTSTRAP_B = 2000
REPETICIONES_CV = 20
SEMILLA = 42
N_SPLITS = 5
ARCHIVO_SALIDA = 'linea_base.json'


def _metricas(y, score):
    return float(roc_auc_score(y, score)), float(average_precision_score(y, score))


def _pipeline_l1(C):
    return make_pipeline(StandardScaler(), LogisticRegression(
        penalty='l1', solver='saga', C=C, class_weight='balanced', max_iter=5000))


def _pipeline_goles_asistencias():
    return make_pipeline(StandardScaler(), LogisticRegression(
        class_weight='balanced', max_iter=1000))


def _intervalo(valores):
    v = np.asarray(valores, dtype=float)
    return [float(np.percentile(v, 2.5)), float(np.percentile(v, 97.5))]


def bootstrap_por_jugador(y, nombres, p_modelo, p_base, B=BOOTSTRAP_B, seed=SEMILLA):
    """Remuestrea jugadores (no filas) y devuelve IC95 de AUC/AUPRC y de su diferencia."""
    rng = np.random.default_rng(seed)
    y = np.asarray(y)
    nombres = np.asarray(nombres)
    jugadores = np.unique(nombres)
    idx_por = {j: np.where(nombres == j)[0] for j in jugadores}
    acum = {k: [] for k in ('auc_modelo', 'auprc_modelo', 'auc_base', 'auprc_base',
                            'dif_auc', 'dif_auprc')}
    for _ in range(B):
        muestra = rng.choice(jugadores, size=len(jugadores), replace=True)
        idx = np.concatenate([idx_por[j] for j in muestra])
        if y[idx].min() == y[idx].max():
            continue
        am, pm = _metricas(y[idx], p_modelo[idx])
        ab, pb = _metricas(y[idx], p_base[idx])
        acum['auc_modelo'].append(am)
        acum['auprc_modelo'].append(pm)
        acum['auc_base'].append(ab)
        acum['auprc_base'].append(pb)
        acum['dif_auc'].append(am - ab)
        acum['dif_auprc'].append(pm - pb)
    resultado = {k: _intervalo(v) for k, v in acum.items()}
    resultado['p_dif_auprc_positiva'] = float(np.mean(np.array(acum['dif_auprc']) > 0))
    resultado['remuestreos_validos'] = len(acum['dif_auprc'])
    return resultado


def cv_repetido(X, y, nombres, C, repeticiones=REPETICIONES_CV, seed=SEMILLA):
    """Metricas por repeticion (AUC, AUPRC sobre OOF) del modelo L1 y de goles+asistencias.

    Las dos primeras columnas de X tienen que ser goles y asistencias.
    """
    por_modelo = {'modelo': [], 'goles_asistencias_logistica': []}
    for r in range(repeticiones):
        cv = StratifiedGroupKFold(n_splits=N_SPLITS, shuffle=True, random_state=seed + r)
        oof = {k: np.zeros(len(y)) for k in por_modelo}
        for tr, te in cv.split(X, y, nombres):
            modelo = _pipeline_l1(C).fit(X[tr], y[tr])
            oof['modelo'][te] = modelo.predict_proba(X[te])[:, 1]
            base = _pipeline_goles_asistencias().fit(X[tr][:, :2], y[tr])
            oof['goles_asistencias_logistica'][te] = base.predict_proba(X[te][:, :2])[:, 1]
        for k in por_modelo:
            por_modelo[k].append(_metricas(y, oof[k]))
    return por_modelo


def resumen_cv(por_modelo):
    def estadisticas(filas):
        auc = np.array([f[0] for f in filas])
        auprc = np.array([f[1] for f in filas])
        return {
            'auc_media': float(auc.mean()), 'auc_sd': float(auc.std(ddof=1)),
            'auprc_media': float(auprc.mean()), 'auprc_sd': float(auprc.std(ddof=1)),
            'auprc_ic95': _intervalo(auprc),
        }

    modelo = por_modelo['modelo']
    base = por_modelo['goles_asistencias_logistica']
    dif = np.array([m[1] - b[1] for m, b in zip(modelo, base)])
    return {
        'modelo': estadisticas(modelo),
        'goles_asistencias_logistica': estadisticas(base),
        'diferencia_auprc_modelo_menos_base': {
            'media': float(dif.mean()), 'ic95': _intervalo(dif),
            'p_positiva': float(np.mean(dif > 0)),
        },
    }


def _trivial(y, score):
    auc, auprc = _metricas(y, score)
    return {'auc': auc, 'auprc': auprc}


def main():
    df = tm.cargar_datos()
    enc = joblib.load(os.path.join(dir_models(), 'position_encoder.pkl'))
    estimador = joblib.load(os.path.join(dir_models(), 'modelo_adn_boca.pkl'))
    scaler = joblib.load(os.path.join(dir_models(), 'scaler.pkl'))
    C = estimador.get_params()['C']

    X = tm.construir_X(df, enc).to_numpy(dtype=float)
    y = df['etiqueta'].to_numpy(dtype=int)
    nombres = df['nombre'].to_numpy()
    test = tm.split_por_jugador(df)
    train = ~test

    p_modelo_test = estimador.predict_proba(scaler.transform(X[test]))[:, 1]
    lr_base = _pipeline_goles_asistencias().fit(X[train][:, :2], y[train])
    p_base_test = lr_base.predict_proba(X[test][:, :2])[:, 1]
    gol, ast = X[test][:, 0], X[test][:, 1]
    edad = X[test][:, 2]

    prueba = {
        'n_filas': int(test.sum()),
        'n_jugadores': int(len(set(nombres[test]))),
        'positivos': int(y[test].sum()),
        'modelo': dict(zip(('auc', 'auprc'), _metricas(y[test], p_modelo_test))),
        'lineas_base': {
            'goles_asistencias_logistica': dict(zip(
                ('auc', 'auprc'), _metricas(y[test], p_base_test))),
            'goles_asistencias_suma': _trivial(y[test], gol + ast),
            'goles': _trivial(y[test], gol),
            'asistencias': _trivial(y[test], ast),
            'edad_menor_es_mejor': _trivial(y[test], -edad),
            'azar': {'auc': 0.5, 'auprc': float(y[test].mean())},
        },
        'bootstrap_por_jugador': bootstrap_por_jugador(
            y[test], nombres[test], p_modelo_test, p_base_test),
    }

    cv = resumen_cv(cv_repetido(X, y, nombres, C))
    cv['repeticiones'] = REPETICIONES_CV
    cv['n_splits'] = N_SPLITS
    cv['C'] = C
    cv['lineas_base_sin_entrenar'] = {
        'goles_asistencias_suma': _trivial(y, X[:, 0] + X[:, 1]),
        'goles': _trivial(y, X[:, 0]),
    }

    salida = {
        'generado': datetime.now(timezone.utc).isoformat(timespec='seconds'),
        'nota': ('Prueba: artefactos guardados sin reentrenar. CV: reentrena en cada '
                 'fold con el mismo C; la comparacion es pareada por repeticion.'),
        'prueba': prueba,
        'cv': cv,
    }
    ruta = os.path.join(dir_models(), ARCHIVO_SALIDA)
    with open(ruta, 'w', encoding='utf-8') as f:
        json.dump(salida, f, ensure_ascii=False, indent=2)
    print(f'Linea base guardada en {ruta}')
    return salida


if __name__ == '__main__':
    main()
