"""Calibración de probabilidades del score ADN Boca.

La L1 se entrena con `class_weight='balanced'`, por lo que su salida NO es
una probabilidad: está en una escala reponderada (prior ~50%) y sin verificar
frecuencia observada. Platt (sigmoid) mapea el logit del score contra las
etiquetas reales usando OOF por jugador, corrigiendo ambos efectos.

Interpretación: P(etiqueta manual = ADN Boca | features) bajo la distribución
de entrenamiento. No es una probabilidad verificada sobre TOTW (no hay
etiquetas allí), y el orden del ranking no cambia si a > 0.
"""

import numpy as np
from sklearn.linear_model import LogisticRegression

EPS = 1e-6


def _logit(scores):
    p = np.clip(np.asarray(scores, dtype=float), EPS, 1 - EPS)
    return np.log(p / (1 - p))


def ajustar_platt(oof, y, reporte='OOF'):
    """Ajusta Platt (sigmoid) sobre scores OOF de CV por jugador.

    Devuelve el calibrador como dict con pendiente `a`, ordenada `b` y
    métrica del ajuste. Sin regularización (penalty=None por defecto en
    sklearn>=1.8): el mapeo refleja la frecuencia observada, no simplifica.
    """
    oof = np.asarray(oof, dtype=float)
    y = np.asarray(y, dtype=float)
    if len(np.unique(y)) < 2:
        raise ValueError('platt requiere ambas clases en y')
    z = _logit(oof).reshape(-1, 1)
    # Sin regularización: penalty=None es el default de sklearn>=1.8 (equivale
    # a C=inf) y no emite warnings si no se pasa C. El mapeo debe reflejar la
    # frecuencia observada, no simplificar.
    modelo = LogisticRegression(solver='lbfgs')
    modelo.fit(z, y)
    a = float(modelo.coef_[0][0])
    b = float(modelo.intercept_[0])
    if a <= 0:
        raise ValueError(
            f'pendiente no positiva (a={a:.4f}): el score no ordena con la etiqueta; '
            'revisar features/split antes de calibrar')
    p_cal = aplicar_platt(oof, {'a': a, 'b': b})
    return {'a': a, 'b': b, 'metodo': 'platt_sigmoid',
            'reporte': reporte, 'n': int(len(oof)),
            'ece_platt': ece(y, p_cal, bins=5)}


def aplicar_platt(scores, calibrador):
    """Transforma scores [0,1] a probabilidades calibradas; monotónico si a > 0."""
    z = _logit(scores)
    return 1.0 / (1.0 + np.exp(-(calibrador['a'] * z + calibrador['b'])))


def brier(y, prob):
    y = np.asarray(y, dtype=float)
    prob = np.asarray(prob, dtype=float)
    return float(np.mean((prob - y) ** 2))


def ece(y, prob, bins=5):
    """Expected Calibration Error con `bins` de igual ancho en [0,1]."""
    y = np.asarray(y, dtype=float)
    prob = np.asarray(prob, dtype=float)
    if len(y) == 0:
        return float('nan')
    bordes = np.linspace(0.0, 1.0, bins + 1)
    total = 0.0
    for i in range(bins):
        if i == bins - 1:
            mask = (prob >= bordes[i]) & (prob <= bordes[i + 1])
        else:
            mask = (prob >= bordes[i]) & (prob < bordes[i + 1])
        if mask.sum() == 0:
            continue
        total += mask.sum() / len(y) * abs(y[mask].mean() - prob[mask].mean())
    return float(total)
