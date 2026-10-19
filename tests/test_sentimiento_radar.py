import pandas as pd

from sentimiento_radar import (
    calcular_sentimiento,
    combinar_fuentes,
    sentimiento_jugador,
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


def test_sentimiento_jugador_conserva_cantidades_por_fuente(monkeypatch):
    import sentimiento_jugadores_prensa as modulo_prensa
    import sentimiento_jugadores_youtube as modulo_youtube

    monkeypatch.setattr(
        modulo_youtube, 'sentimiento_jugador_youtube',
        lambda nombre, club, engine=None: {
            'ok': True, 'valor': 2.0, 'n_comentarios': 17,
        })
    monkeypatch.setattr(
        modulo_prensa, 'sentimiento_jugador_prensa',
        lambda nombre, club, engine=None: {
            'ok': True, 'valor': 4.0, 'n_textos': 9,
        })

    registro = sentimiento_jugador('Jugador', 'Club', engine=object())

    assert registro['sentimiento'] == 3.2
    assert registro['youtube_n_comentarios'] == 17
    assert registro['prensa_n_textos'] == 9


def test_sentimiento_jugador_registra_la_version_del_motor(monkeypatch):
    """La cache dice con que motor se midio: asi se puede re-medir despues."""
    import sentimiento_jugadores_prensa as modulo_prensa
    import sentimiento_jugadores_youtube as modulo_youtube
    from nlp_engine import MOTOR

    monkeypatch.setattr(
        modulo_youtube, 'sentimiento_jugador_youtube',
        lambda nombre, club, engine=None: {'ok': False, 'valor': 0.0})
    monkeypatch.setattr(
        modulo_prensa, 'sentimiento_jugador_prensa',
        lambda nombre, club, engine=None: {'ok': True, 'valor': 1.0, 'n_textos': 3})

    registro = sentimiento_jugador('Jugador', 'Club', engine=object())

    assert registro['motor'] == MOTOR


def test_sentimiento_jugador_permite_respuestas_legacy_sin_conteos(monkeypatch):
    import sentimiento_jugadores_prensa as modulo_prensa
    import sentimiento_jugadores_youtube as modulo_youtube

    monkeypatch.setattr(
        modulo_youtube, 'sentimiento_jugador_youtube',
        lambda nombre, club, engine=None: {'ok': False, 'valor': 0.0})
    monkeypatch.setattr(
        modulo_prensa, 'sentimiento_jugador_prensa',
        lambda nombre, club, engine=None: {
            'ok': True, 'valor': 4.0,
        })

    registro = sentimiento_jugador('Jugador', 'Club', engine=object())

    assert registro['sentimiento'] == 4.0
    assert registro['youtube_n_comentarios'] is None
    assert registro['prensa_n_textos'] is None


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


def test_calcular_sentimiento_guarda_textos_crudos_aparte(tmp_path):
    import json
    from sentimiento_radar import ruta_textos

    cache = tmp_path / 'sentimiento_radar_2026-W40.csv'

    def fake(nombre, club, engine=None):
        r = _registro(nombre, club, 3.0)
        r['textos'] = {'youtube': ['buen partido de ' + nombre], 'prensa': ['titular']}
        return r

    calcular_sentimiento([('A', 'X')], cache_path=cache, calcular=fake)

    csv = pd.read_csv(cache, encoding='utf-8-sig')
    assert 'textos' not in csv.columns
    with open(ruta_textos(str(cache)), encoding='utf-8') as f:
        crudos = json.load(f)
    assert crudos['A|X']['youtube'] == ['buen partido de A']
    assert crudos['A|X']['prensa'] == ['titular']


def test_ruta_textos_sigue_el_nombre_de_la_cache():
    from sentimiento_radar import ruta_textos
    assert ruta_textos('data/sentimiento_radar_2026-W40.csv').endswith(
        'sentimiento_textos_2026-W40.json')
