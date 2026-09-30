import numpy as np
import pytest

from calibracion import ajustar_platt, aplicar_platt, brier, ece


def datos_sinteticos(n=400, prevalencia=0.3, seed=7):
    """Scores con escala reponderada (prior 0.5) y etiquetas con prevalencia real."""
    rng = np.random.default_rng(seed)
    y = (rng.random(n) < prevalencia).astype(int)
    # score con señal + ruido, en escala de logit reponderado
    logits = 1.5 * (y - 0.5) + rng.normal(0, 0.8, n)
    scores = 1 / (1 + np.exp(-logits))
    return scores, y


def test_ajustar_platt_devuelve_pendiente_positiva_y_reporte():
    scores, y = datos_sinteticos()
    cal = ajustar_platt(scores, y, reporte='sintetico')

    assert cal['metodo'] == 'platt_sigmoid'
    assert cal['a'] > 0
    assert cal['n'] == len(scores)
    assert 0 <= cal['ece_platt'] <= 1


def test_aplicar_platt_es_monotonica_y_rangada():
    scores, y = datos_sinteticos()
    cal = ajustar_platt(scores, y)
    probs = aplicar_platt(scores, cal)

    assert np.all((probs >= 0) & (probs <= 1))
    orden = np.argsort(scores)
    assert np.all(np.diff(probs[orden]) >= -1e-12)


def test_platt_reduce_error_de_calibracion_de_prior():
    """Los scores reponderados (prior 0.5) sobreestiman; Platt recupera la prevalencia."""
    scores, y = datos_sinteticos(prevalencia=0.3)
    cal = ajustar_platt(scores, y)
    probs = aplicar_platt(scores, cal)

    assert abs(probs.mean() - y.mean()) < 0.08
    assert brier(y, probs) <= brier(y, scores) + 1e-9


def test_platt_rechaza_scores_sin_senal():
    scores, y = datos_sinteticos()
    scores_invertidos = 1 - scores
    with pytest.raises(ValueError, match='pendiente no positiva'):
        ajustar_platt(scores_invertidos, y)


def test_metricas_brier_ece():
    y = np.array([0, 0, 1, 1])
    perfecta = np.array([0.0, 0.0, 1.0, 1.0])
    assert brier(y, perfecta) == 0
    assert ece(y, perfecta, bins=4) == 0
    # ECE mide la brecha confianza-frecuencia, no el spread: con y=[0,0,0,1]
    # una confianza 0.5 está sesgada 0.25 sobre la frecuencia real 0.25.
    assert ece(np.array([0, 0, 0, 1]), np.full(4, 0.5), bins=1) == pytest.approx(0.25)
