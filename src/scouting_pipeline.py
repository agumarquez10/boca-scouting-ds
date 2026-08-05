import os
import sqlite3
import sys
import warnings

import joblib
import pandas as pd

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, SCRIPT_DIR)
warnings.filterwarnings('ignore')

from posiciones import PositionEncoder, es_perfil_ofensivo  # noqa: E402

DATA_DIR = os.path.join(SCRIPT_DIR, '..', 'data')
MODEL_DIR = os.path.join(SCRIPT_DIR, '..', 'models')
DB_PATH = os.path.join(DATA_DIR, 'boca_juniors.db')

MIN_PARTIDOS = 1


def cargar_candidatos():
    con = sqlite3.connect(DB_PATH)
    df = pd.read_sql('SELECT * FROM candidatos_mercado', con)
    con.close()
    return df


def build_candidate_features(df):
    """Features de perfil para candidatos de mercado.

    Los candidatos tienen una sola temporada observada, por lo que
    temporadas_en_dataset = 1 y partidos_por_temporada = partidos jugados.
    Se respetan las mismas features que el train (perfil puro, sin goles).
    """
    feat = pd.DataFrame(index=df.index)
    feat['pases_precisos'] = df['pases_precisos'].fillna(0)
    feat['edad'] = df['edad'].fillna(0)
    feat['temporadas_en_dataset'] = 1
    feat['partidos_por_temporada'] = df['partidos'].fillna(0)
    feat['perfil_ofensivo'] = df['posicion'].apply(es_perfil_ofensivo).astype(int)
    return feat


def main():
    df = cargar_candidatos()
    total = len(df)
    df = df[df['partidos'] >= MIN_PARTIDOS].copy()
    print(f'Candidatos: {total} | con partidos>={MIN_PARTIDOS}: {len(df)}')

    config = joblib.load(os.path.join(MODEL_DIR, 'config.pkl'))
    modelo = joblib.load(os.path.join(MODEL_DIR, 'modelo_adn_boca.pkl'))
    scaler = joblib.load(os.path.join(MODEL_DIR, 'scaler.pkl'))
    encoder = joblib.load(os.path.join(MODEL_DIR, 'position_encoder.pkl'))

    base = config['features']
    X = build_candidate_features(df)
    X_pos = encoder.transform(df['posicion']).reset_index(drop=True)
    X = pd.concat([X[base].reset_index(drop=True), X_pos], axis=1)
    X = X.reindex(columns=config['features'] + config['pos_columns'])

    X_scaled = scaler.transform(X)
    prob = modelo.predict_proba(X_scaled)[:, 1]
    pred = (prob >= 0.5).astype(int)

    ranking = df[['nombre', 'club_actual', 'posicion', 'edad', 'partidos',
                  'goles', 'asistencias', 'temporada']].copy()
    ranking['probabilidad'] = prob
    ranking['prediccion'] = pred
    ranking = ranking.sort_values('probabilidad', ascending=False).reset_index(drop=True)

    ranking.to_csv(os.path.join(DATA_DIR, 'scouting_resultado.csv'),
                   index=False, encoding='utf-8-sig')
    print(f'data/scouting_resultado.csv guardado ({len(ranking)} candidatos)')

    con = sqlite3.connect(DB_PATH)
    ranking.to_sql('scouting_resultado', con, if_exists='replace', index=False)
    con.close()
    print('Tabla SQLite scouting_resultado reemplazada (esquema nuevo)')

    print('\n=== TOP 10 CANDIDATOS CON ADN BOCA ===')
    cols = ['nombre', 'club_actual', 'posicion', 'partidos', 'goles', 'asistencias', 'probabilidad']
    print(ranking.head(10)[cols].to_string(index=False))
    return ranking


if __name__ == '__main__':
    main()
