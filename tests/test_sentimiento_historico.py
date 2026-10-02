import pandas as pd
import pytest

import sentimiento_historico as modulo
from sentimiento_historico import (
    barrer_semanas,
    consolidar,
    jugadores_de_semana,
    semanas_registradas,
    top_por_semana,
)


def _ranking():
    filas = []
    for i, posicion in enumerate(['Centre-Forward', 'Left Winger',
                                  'Central Midfield', 'Attacking Midfield',
                                  'Centre-Back', 'Right-Back'], 1):
        filas.append({
            'player_id_fotmob': i, 'ranking': i,
            'nombre': f'Jugador {i}', 'club': f'Club {i}', 'liga': 'Liga',
            'posicion': posicion, 'score_adn_boca': 0.9 - i * 0.05,
            'probabilidad_adn': 0.8, 'goles': i, 'asistencias': i,
        })
    return pd.DataFrame(filas)


def _calcular(nombre, club, engine=None):
    return {'nombre': nombre, 'club': club, 'sentimiento': float(nombre[-1]),
            'n_fuentes': 2, 'fuentes': 'prensa,youtube',
            'youtube_valor': 1.0, 'prensa_valor': 0.5}


def test_jugadores_de_semana_incluye_puesto():
    jugadores = jugadores_de_semana(_ranking())
    assert len(jugadores) == 6
    assert [p for _, _, p in jugadores] == ['DEL', 'DEL', 'MED', 'MED', 'DEF', 'DEF']
    assert jugadores[0][:2] == ('Jugador 1', 'Club 1')


def test_semanas_registradas_ordena_y_descarta_vacias(tmp_path):
    for semana in ('2026-W36', '2026-W34'):
        _ranking().to_csv(tmp_path / f'ranking_jugadores_fecha_{semana}.csv',
                          index=False, encoding='utf-8-sig')
    pd.DataFrame(columns=['ranking']).to_csv(
        tmp_path / 'ranking_jugadores_fecha_2026-W38.csv', index=False)
    (tmp_path / 'ranking_historico_acumulado.csv').write_text('x', encoding='utf-8')

    assert [s for s, _ in semanas_registradas(tmp_path)] == ['2026-W34', '2026-W36']


def test_barrer_semanas_calcula_y_cachea(tmp_path):
    _ranking().to_csv(tmp_path / 'ranking_jugadores_fecha_2026-W36.csv',
                      index=False, encoding='utf-8-sig')
    df = barrer_semanas(tmp_path, calcular=_calcular, verbose=False)

    assert len(df) == 6
    assert set(df['semana']) == {'2026-W36'}
    assert set(df['puesto']) == {'DEL', 'MED', 'DEF'}
    assert (tmp_path / 'sentimiento_radar_2026-W36.csv').exists()


def test_barrer_semanas_reusa_la_cache(tmp_path):
    _ranking().to_csv(tmp_path / 'ranking_jugadores_fecha_2026-W36.csv',
                      index=False, encoding='utf-8-sig')
    barrer_semanas(tmp_path, calcular=_calcular, verbose=False)

    def no_deberia_calcular(*args, **kwargs):
        raise AssertionError('la cache deberia evitar la consulta')

    segunda = barrer_semanas(tmp_path, calcular=no_deberia_calcular, verbose=False)
    assert len(segunda) == 6


def test_consolidar_ordena_por_maximo():
    df = pd.DataFrame([
        {'semana': '2026-W34', 'puesto': 'DEL', 'nombre': 'A', 'club': 'C1',
         'sentimiento': 1.0, 'n_fuentes': 2, 'fuentes': 'prensa,youtube',
         'youtube_valor': 1.0, 'prensa_valor': 0.0},
        {'semana': '2026-W35', 'puesto': 'MED', 'nombre': 'A', 'club': 'C1',
         'sentimiento': 3.0, 'n_fuentes': 1, 'fuentes': 'prensa',
         'youtube_valor': None, 'prensa_valor': 3.0},
        {'semana': '2026-W35', 'puesto': 'DEF', 'nombre': 'B', 'club': 'C2',
         'sentimiento': 2.0, 'n_fuentes': 2, 'fuentes': 'prensa,youtube',
         'youtube_valor': 1.0, 'prensa_valor': 3.0},
    ])
    out = consolidar(df)
    assert list(out['nombre']) == ['A', 'B']
    fila = out.iloc[0]
    assert fila['semanas_medidas'] == 2
    assert fila['sentimiento_medio'] == 2.0
    assert fila['sentimiento_max'] == 3.0
    assert fila['primera_semana'] == '2026-W34'
    assert fila['ultima_semana'] == '2026-W35'


def test_consolidar_ignora_jugadores_sin_datos():
    df = pd.DataFrame([
        {'semana': '2026-W34', 'puesto': 'DEL', 'nombre': 'A', 'club': 'C1',
         'sentimiento': None, 'n_fuentes': 0, 'fuentes': '',
         'youtube_valor': None, 'prensa_valor': None},
    ])
    assert consolidar(df).empty


def test_top_por_semana_excluye_sin_datos():
    df = pd.DataFrame([
        {'semana': '2026-W34', 'puesto': 'DEL', 'nombre': 'A', 'club': 'C1',
         'sentimiento': 1.0, 'n_fuentes': 1, 'fuentes': 'prensa',
         'youtube_valor': None, 'prensa_valor': 1.0},
        {'semana': '2026-W34', 'puesto': 'MED', 'nombre': 'B', 'club': 'C2',
         'sentimiento': None, 'n_fuentes': 0, 'fuentes': '',
         'youtube_valor': None, 'prensa_valor': None},
    ])
    top = top_por_semana(df)
    assert len(top['2026-W34']) == 1
    assert top['2026-W34'][0]['nombre'] == 'A'


def test_top_por_semana_vacio():
    assert top_por_semana(pd.DataFrame()) == {}
    assert consolidar(pd.DataFrame()).empty


def test_barrer_sin_semanas_devuelve_vacio(tmp_path):
    assert barrer_semanas(tmp_path, calcular=_calcular, verbose=False).empty