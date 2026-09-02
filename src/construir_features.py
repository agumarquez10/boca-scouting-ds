import os
import sys

import pandas as pd

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, SCRIPT_DIR)

from posiciones import agrupar_posicion, es_perfil_ofensivo

DATA_DIR = os.path.join(SCRIPT_DIR, '..', 'data')
MODEL_DIR = os.path.join(SCRIPT_DIR, '..', 'models')


def construir_features_jugador(jugador_stats):
    """Construye features de perfil para un jugador desde la API Football.

    Acepta un dict con la estructura de statistics[0] de la API:
    - player: {id, name, age, ...}
    - statistics: [{games: {appearences, position}, passes: {total, accuracy}}]

    Devuelve un dict con las features del modelo (sin pases_precisos).
    """
    player = jugador_stats.get('player', {})
    stats = jugador_stats.get('statistics', [{}])
    if isinstance(stats, list) and stats:
        stats = stats[0]
    else:
        stats = {}

    games = stats.get('games', {}) or {}
    passes = stats.get('passes', {}) or {}

    position_raw = games.get('position', '') or ''

    return {
        'nombre': player.get('name', ''),
        'player_id': player.get('id'),
        'edad': player.get('age', 0) or 0,
        'temporadas_en_dataset': 1,
        'partidos_por_temporada': games.get('appearences', 0) or 0,
        'perfil_ofensivo': int(es_perfil_ofensivo(position_raw)),
        'posicion': position_raw,
        'club': (stats.get('team') or {}).get('name', ''),
        'club_id': (stats.get('team') or {}).get('id'),
        'liga': (stats.get('league') or {}).get('name', ''),
        'liga_id': (stats.get('league') or {}).get('id'),
        'pases_total': passes.get('total', 0) or 0,
        'pases_accuracy': passes.get('accuracy'),
    }


def construir_features_batch(jugadores_stats):
    """Construye DataFrame de features para una lista de jugadores."""
    filas = []
    for j in jugadores_stats:
        filas.append(construir_features_jugador(j))
    df = pd.DataFrame(filas)
    return df


def aplicar_modelo(df_features, modelo_path=None, scaler_path=None, config_path=None):
    """Aplica el modelo entrenado a un DataFrame de features.

    Devuelve el DataFrame con columna 'probabilidad' (0.0-1.0).
    """
    import joblib

    if modelo_path is None:
        modelo_path = os.path.join(MODEL_DIR, 'modelo_adn_boca.pkl')
    if scaler_path is None:
        scaler_path = os.path.join(MODEL_DIR, 'scaler.pkl')
    if config_path is None:
        config_path = os.path.join(MODEL_DIR, 'config.pkl')

    modelo = joblib.load(modelo_path)
    scaler = joblib.load(scaler_path)
    config = joblib.load(config_path)

    from posiciones import PositionEncoder
    encoder = PositionEncoder(config['pos_columns'])

    X_base = df_features[config['features']].copy()
    X_pos = encoder.transform(df_features['posicion']).reset_index(drop=True)
    X = pd.concat([X_base.reset_index(drop=True), X_pos], axis=1)
    X = X.reindex(columns=config['features'] + config['pos_columns'], fill_value=0)

    X_scaled = scaler.transform(X)
    prob = modelo.predict_proba(X_scaled)[:, 1]
    df_features = df_features.copy()
    df_features['probabilidad'] = prob
    return df_features


if __name__ == '__main__':
    print('construir_features.py - modulo de uso, ejecutar scouting_mercado.py')
