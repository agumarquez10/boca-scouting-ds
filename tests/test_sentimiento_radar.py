import pandas as pd

from sentimiento_radar import (
    calcular_sentimiento,
    combinar_fuentes,
    top_por_sentimiento,
)


def test_combinar_fuentes_prioriza_medios():
    valor, fuentes = combinar_fuentes({'ok': True, 'valor': 10.0},
                                      {'ok': True, 'valor': 20.0})
    assert valor == 16.0
    assert fuentes == ['prensa', 'youtube']


def test_combinar_fuentes_solo_una():
    assert combinar_fuentes({'ok': True, 'valor': 10.0}, {'ok': False}) == (10.0, ['youtube'])
    assert combinar_fuentes({'ok': False}, {'ok': True, 'valor': -4.0}) == (-4.0, ['prensa'])


def test_combinar_fuentes_sin_datos():
    assert combinar_fuentes({'ok': False}, {'ok': False}) == (None, [])


def _registro(nombre, club, sentimiento, n=1):
    return {
        'nombre': nombre, 'club': club, 'sentimiento': sentimiento,
        'n_fuentes': n, 'fuentes': 'prensa',
        'youtube_valor': None, 'prensa_valor': sentimiento,
    }


def test_calcular_sentimiento_cachea(tmp_path):
    cache = tmp_path / 'sent.csv'
    llamadas = []

    def fake(nombre, club, engine=None):
        llamadas.append(nombre)
        return _registro(nombre, club, 5.0)

    primera = calcular_sentimiento([('A', 'X')], cache_path=cache, calcular=fake)
    segunda = calcular_sentimiento([('A', 'X')], cache_path=cache, calcular=fake)
    assert llamadas == ['A']
    assert primera[0]['sentimiento'] == 5.0
    assert segunda[0]['sentimiento'] == 5.0


def test_calcular_sentimiento_cachea_sin_datos(tmp_path):
    cache = tmp_path / 'sent.csv'
    llamadas = []

    def fake(nombre, club, engine=None):
        llamadas.append(nombre)
        return _registro(nombre, club, None, n=0)

    calcular_sentimiento([('A', 'X')], cache_path=cache, calcular=fake)
    calcular_sentimiento([('A', 'X')], cache_path=cache, calcular=fake)
    assert llamadas == ['A']
    assert pd.read_csv(cache, encoding='utf-8-sig')['sentimiento'].isna().all()


def test_top_por_sentimiento_ordena_y_excluye_sin_datos():
    registros = [
        _registro('A', 'X', 5.0),
        _registro('B', 'Y', None, n=0),
        _registro('C', 'Z', 9.0),
    ]
    top = top_por_sentimiento(registros, 3)
    assert [r['nombre'] for r in top] == ['C', 'A']


def test_top_por_sentimiento_limita_n():
    registros = [_registro(str(i), 'X', float(i)) for i in range(5)]
    assert len(top_por_sentimiento(registros, 3)) == 3


def test_top_por_sentimiento_vacio():
    assert top_por_sentimiento([]) == []
    assert top_por_sentimiento([_registro('A', 'X', None, n=0)]) == []
