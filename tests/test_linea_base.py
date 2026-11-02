import numpy as np
import pytest

from linea_base import (_metricas, bootstrap_por_jugador, cv_repetido, resumen_cv)


def _datos_sinteticos(n_jugadores=30, filas=6, seed=0):
    rng = np.random.default_rng(seed)
    nombres = np.repeat([f'J{i}' for i in range(n_jugadores)], filas)
    goles = rng.poisson(2, size=len(nombres)).astype(float)
    asistencias = rng.poisson(1, size=len(nombres)).astype(float)
    edad = rng.integers(18, 35, size=len(nombres)).astype(float)
    ruido = rng.normal(0, 1, size=len(nombres))
    y = ((goles + asistencias + ruido) > 3).astype(int)
    X = np.column_stack([goles, asistencias, edad])
    return X, y, nombres


def test_metricas_perfectas():
    auc, auprc = _metricas(np.array([0, 0, 1, 1]), np.array([0.1, 0.2, 0.8, 0.9]))
    assert auc == pytest.approx(1.0)
    assert auprc == pytest.approx(1.0)


def test_bootstrap_con_el_mismo_score_da_diferencia_cero():
    y = np.array([0, 1, 0, 1, 1, 0, 1, 0])
    nombres = np.array(['a', 'a', 'b', 'b', 'c', 'c', 'd', 'd'])
    score = np.array([0.2, 0.7, 0.4, 0.6, 0.9, 0.1, 0.8, 0.3])
    r = bootstrap_por_jugador(y, nombres, score, score, B=200, seed=1)
    assert r['dif_auprc'] == [0.0, 0.0]
    assert r['dif_auc'] == [0.0, 0.0]
    assert r['p_dif_auprc_positiva'] == 0.0


def test_bootstrap_no_usa_filas_sueltas_como_si_fueran_jugadores():
    y = np.array([1, 0, 1, 0, 1, 0])
    nombres = np.array(['a', 'a', 'b', 'b', 'c', 'c'])
    score = np.array([0.9, 0.1, 0.8, 0.2, 0.7, 0.3])
    r = bootstrap_por_jugador(y, nombres, score, score, B=100, seed=2)
    assert r['remuestreos_validos'] > 0
    assert r['auc_modelo'][0] <= r['auc_modelo'][1]


def test_cv_repetido_devuelve_una_metrica_por_repeticion():
    X, y, nombres = _datos_sinteticos()
    por_modelo = cv_repetido(X, y, nombres, C=10, repeticiones=2, seed=0)
    assert set(por_modelo) == {'modelo', 'goles_asistencias_logistica'}
    assert all(len(v) == 2 for v in por_modelo.values())
    for auc, auprc in por_modelo['modelo']:
        assert 0.0 <= auc <= 1.0 and 0.0 <= auprc <= 1.0


def test_resumen_cv_calcula_la_diferencia_pareada():
    por_modelo = {
        'modelo': [(0.8, 0.70), (0.8, 0.72), (0.8, 0.74)],
        'goles_asistencias_logistica': [(0.8, 0.75), (0.8, 0.76), (0.8, 0.77)],
    }
    r = resumen_cv(por_modelo)
    dif = r['diferencia_auprc_modelo_menos_base']
    assert dif['media'] == pytest.approx(-0.04)
    assert dif['p_positiva'] == 0.0
    assert dif['ic95'][0] <= dif['media'] <= dif['ic95'][1]


def test_landing_sin_linea_base_queda_en_none(tmp_path):
    import landing_data
    assert landing_data._leer_linea_base(str(tmp_path)) is None
