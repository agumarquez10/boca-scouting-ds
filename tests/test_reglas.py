"""Tests mínimos de las reglas obligatorias de Data Science (AGENTS.md)."""

import os

import joblib
import numpy as np
import pandas as pd

from posiciones import PositionEncoder
from train_model import (BASE_FEATURES, POS_COLUMNS, UMBRAL_TEST,
                         cargar_datos, construir_X, split_por_jugador)

RAIZ = os.path.dirname(os.path.abspath(__file__)) + os.sep + '..'
DATA_DIR = os.path.join(RAIZ, 'data')
MODEL_DIR = os.path.join(RAIZ, 'models')

COLUMNAS_PROHIBIDAS = {'rating', 'goles', 'asistencias', 'goles_por_partido',
                       'asist_por_partido', 'contribucion_gol', 'pases_norm',
                       'rendimiento', 'experiencia', 'edad_estimada_debut'}


def test_rating_y_derivados_no_son_features():
    config = joblib.load(os.path.join(MODEL_DIR, 'config.pkl'))
    features = config['features'] + config['pos_columns']
    infiltrados = COLUMNAS_PROHIBIDAS & set(features)
    assert not infiltrados, f'features con leakage: {infiltrados}'


def test_etiqueta_definida_con_rating_no_como_feature():
    df = cargar_datos()
    assert 'rating' not in df.columns
    raw = pd.read_csv(os.path.join(DATA_DIR, 'adn_boca_real.csv'), encoding='utf-8-sig')
    esperada = ((raw['rating'] >= 7.0) & (raw['goles'] + raw['asistencias'] >= 3)).astype(int)
    assert (raw['etiqueta'] == esperada).all()
    for col in COLUMNAS_PROHIBIDAS:
        assert col not in BASE_FEATURES


def test_split_por_jugador_sin_fuga():
    df = cargar_datos()
    mask = split_por_jugador(df)
    jugadores_test = set(df.loc[mask, 'nombre'])
    jugadores_train = set(df.loc[~mask, 'nombre'])
    assert jugadores_train.isdisjoint(jugadores_test)
    assert df.loc[mask, 'temporada'].max() >= UMBRAL_TEST


def test_multicolinealidad_features_finales():
    df = cargar_datos()
    enc = PositionEncoder(POS_COLUMNS)
    X = construir_X(df, enc)
    c = X[BASE_FEATURES + POS_COLUMNS].corr().abs()
    for i in range(len(c)):
        for j in range(i + 1, len(c)):
            assert c.iloc[i, j] <= 0.8, (
                f'pares colineales: {c.index[i]} <-> {c.columns[j]} = {c.iloc[i, j]:.3f}')


def test_pkls_cargables_y_prediccion_valida():
    config = joblib.load(os.path.join(MODEL_DIR, 'config.pkl'))
    modelo = joblib.load(os.path.join(MODEL_DIR, 'modelo_adn_boca.pkl'))
    scaler = joblib.load(os.path.join(MODEL_DIR, 'scaler.pkl'))
    encoder = joblib.load(os.path.join(MODEL_DIR, 'position_encoder.pkl'))

    fila = {'pases_precisos': 75, 'edad': 23, 'temporadas_en_dataset': 3,
            'partidos_por_temporada': 30, 'perfil_ofensivo': 1}
    X_base = pd.DataFrame([fila])
    X_pos = encoder.transform(pd.Series(['Attacker']))
    X = pd.concat([X_base, X_pos], axis=1).reindex(
        columns=config['features'] + config['pos_columns'])
    X_scaled = scaler.transform(X)
    prob = modelo.predict_proba(X_scaled)[:, 1]
    assert 0.0 <= prob[0] <= 1.0
    assert X.shape[1] == len(config['features']) + len(config['pos_columns'])


def test_config_consistente_con_features_list():
    config = joblib.load(os.path.join(MODEL_DIR, 'config.pkl'))
    features_list = joblib.load(os.path.join(MODEL_DIR, 'features_list.pkl'))
    assert features_list == config['features'] + config['pos_columns']


def test_ranking_candidatos_generado():
    df = pd.read_csv(os.path.join(DATA_DIR, 'scouting_resultado.csv'), encoding='utf-8-sig')
    for col in ['nombre', 'probabilidad', 'prediccion', 'posicion']:
        assert col in df.columns
    assert df['probabilidad'].is_monotonic_decreasing
    assert df['probabilidad'].between(0, 1).all()
    assert df['prediccion'].isin([0, 1]).all()


def test_historico_valido():
    df = pd.read_csv(os.path.join(DATA_DIR, 'scouting_resultado_historico.csv'),
                     encoding='utf-8-sig')
    assert {'fuente', 'etiqueta', 'probabilidad'}.issubset(df.columns)
    assert df['probabilidad'].between(0, 1).all()
    assert set(df['fuente']) == {'cv', 'test'}
