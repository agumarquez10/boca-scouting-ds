import pandas as pd
import pytest

from automatizacion import (
    cargar_hype,
    clasificar_hype,
    componer_tweet,
    hype_actual,
    seleccionar_por_puesto,
)


POSICIONES = [
    ('Centre-Forward', 'DEL'), ('Left Winger', 'DEL'),
    ('Central Midfield', 'MED'), ('Attacking Midfield', 'MED'),
    ('Centre-Back', 'DEF'), ('Right-Back', 'DEF'),
]


def ranking():
    filas = []
    for i, (posicion, _) in enumerate(POSICIONES, 1):
        filas.append({
            'nombre': f'Jugador {i}',
            'club': f'Club {i}',
            'liga': 'Liga',
            'posicion': posicion,
            'score_adn_boca': 0.9 - i * 0.05,
            'probabilidad_adn': 0.8 - i * 0.05,
            'goles': i,
            'asistencias': i + 1,
        })
    return pd.DataFrame(filas)


def test_clasificar_hype():
    assert clasificar_hype(None) == 'sin datos'
    assert clasificar_hype(0.2) == 'hinchada eufórica'
    assert clasificar_hype(0.1) == 'clima positivo'
    assert clasificar_hype(-0.1) == 'clima negativo'
    assert clasificar_hype(0.0) == 'clima neutral'


def test_hype_actual_usa_ultima_semana():
    sent = pd.DataFrame({
        'fecha': ['2026-09-01', '2026-09-02', '2026-09-03'],
        'compound': [0.5, 0.5, 0.5],
        'clasificacion': ['positivo', 'positivo', 'positivo'],
    })
    valor = hype_actual(sent)
    assert valor == pytest.approx((0.6 * 0.5 + 0.4 * 1.0) * (1.386294 / 3.0), abs=1e-4)


def test_cargar_hype_archivo_inexistente(tmp_path):
    assert cargar_hype(tmp_path / 'no_existe.csv') is None


def test_seleccionar_por_puesto_agrupa_y_ordena():
    seleccion = seleccionar_por_puesto(ranking())
    assert list(seleccion) == ['DEL', 'MED', 'DEF']
    for grupo in seleccion.values():
        assert len(grupo) <= 3
    delanteros = seleccion['DEL']
    assert list(delanteros['posicion']) == ['Centre-Forward', 'Left Winger']
    assert delanteros['score_adn_boca'].is_monotonic_decreasing


def test_seleccionar_por_puesto_omite_grupo_vacio():
    df = ranking()
    df = df[df['posicion'] == 'Centre-Forward']
    seleccion = seleccionar_por_puesto(df)
    assert list(seleccion) == ['DEL']


def test_seleccionar_por_puesto_vacio():
    assert seleccionar_por_puesto(pd.DataFrame()) == {}


def test_componer_tweet_incluye_club_goles_asistencias_y_puestos():
    texto = componer_tweet(seleccionar_por_puesto(ranking()))
    assert 'DEL:' in texto and 'MED:' in texto and 'DEF:' in texto
    assert 'Jugador 1 (Club 1) 1+2' in texto
    assert 'Hype:' not in texto
    assert '#Boca' in texto


def test_componer_tweet_sin_sentimiento():
    texto = componer_tweet(seleccionar_por_puesto(ranking()))
    assert 'SENT' not in texto


def test_componer_tweet_incluye_sentimiento():
    sentimiento = [
        {'nombre': 'Jugador 1', 'club': 'Club 1', 'sentimiento': 19.6},
        {'nombre': 'Jugador 2', 'club': 'Club 2', 'sentimiento': 7.2},
    ]
    texto = componer_tweet(seleccionar_por_puesto(ranking()), sentimiento)
    assert 'SENT (hinchada+medios):' in texto
    assert 'Jugador 1 (Club 1) +19.6' in texto
    assert 'Jugador 2 (Club 2) +7.2' in texto


def test_componer_tweet_incluye_club_con_nombres_largos():
    df = pd.DataFrame({
        'nombre': [f'Jugador Largo {i}' for i in range(6)],
        'club': ['Club Muy Largo'] * 6,
        'posicion': [p for p, _ in POSICIONES],
        'score_adn_boca': [0.9] * 6,
        'probabilidad_adn': [0.9] * 6,
        'goles': [1] * 6,
        'asistencias': [1] * 6,
    })
    texto = componer_tweet(seleccionar_por_puesto(df))
    assert 'Club Muy Largo' in texto
    assert texto.rstrip().endswith('#Boca #MercadoDePases #Fichajes')
