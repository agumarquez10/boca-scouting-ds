import logging

import pandas as pd
import pytest

import corrida_semanal
from corrida_semanal import (
    EXIT_OK,
    EXIT_SIN_SALIDA,
    cumple_gate,
    corrida,
)
from scouting_pipeline import generar_ranking_semanal
from sentimiento_radar import _guardar_cache


LIGAS = [{'nombre': 'Argentina', 'fotmob_id': 112},
         {'nombre': 'Brasil', 'fotmob_id': 268},
         {'nombre': 'Peru', 'fotmob_id': 131},
         {'nombre': 'Chile', 'fotmob_id': 273},
         {'nombre': 'Paraguay', 'fotmob_id': 199}]

RANGING = pd.DataFrame([{
    'player_id_fotmob': 1, 'ranking': 1,
    'nombre': 'Jugador 1', 'club': 'Club 1', 'liga': 'Argentina',
    'posicion': 'Centre-Forward', 'score_adn_boca': 0.9, 'probabilidad_adn': 0.8,
    'goles': 1, 'asistencias': 1,
    'apariciones_totw_semana': 1, 'ligas_totw_semana': 'Argentina',
    'fechas_totw_semana': '2026-09-28',
}])


def _api_fake(ligas_con_totw):
    """Stub de FotMobApi: solo devuelve filas TOTW para las ligas indicadas."""
    class Api:
        def temporada_actual(self, liga_id, force_refresh=False):
            return '2026'

        def fixtures(self, liga_id, season, force_refresh=False):
            return {}

        def totw_rounds(self, liga_id, season, force_refresh=False):
            return {}

        def totw(self, liga_id, season, round_id, force_refresh=False):
            return {}

        def close(self):
            pass

    return Api()


@pytest.mark.parametrize('n_ligas,esperado', [
    (0, False), (2, False), (3, True), (4, True), (5, True),
])
def test_cumple_gate(n_ligas, esperado):
    detalle = {'n_ligas_con_totw': n_ligas}
    assert cumple_gate(detalle) is esperado


def test_cumple_gate_umbral_configurable():
    detalle = {'n_ligas_con_totw': 3}
    assert cumple_gate(detalle, min_ligas=3) is True
    assert cumple_gate(detalle, min_ligas=4) is False


def test_detalle_cuenta_ligas_con_totw(monkeypatch):
    import scouting_pipeline as modulo

    con_totw = {'Argentina', 'Brasil', 'Peru'}

    def fake_recolectar(api, liga, inicio, fin):
        filas = [{'liga': liga['nombre']}] if liga['nombre'] in con_totw else []
        return filas, ([] if filas else [f"{liga['nombre']}: sin TOTW"])

    monkeypatch.setattr(modulo, 'recolectar_totw_semana', fake_recolectar)
    monkeypatch.setattr(modulo, 'enriquecer_y_puntuar',
                        lambda filas, api, scorer=None: (RANGING, pd.DataFrame()))

    detalle = {}
    ranking, _, _ = generar_ranking_semanal(
        _api_fake(con_totw), '2026-09-28', '2026-10-05',
        ligas=LIGAS, detalle=detalle)

    assert not ranking.empty
    assert detalle['n_ligas_con_totw'] == 3
    assert detalle['ligas_con_totw'] == ['Argentina', 'Brasil', 'Peru']
    assert detalle['ligas_sin_totw'] == ['Chile', 'Paraguay']
    assert detalle['semana'] == '2026-W40'
    assert detalle['inicio'] == '2026-09-28'


def test_detalle_registra_liga_con_error_de_fuente(monkeypatch):
    import scouting_pipeline as modulo

    def fake_recolectar(api, liga, inicio, fin):
        if liga['nombre'] == 'Brasil':
            raise ConnectionError('red caida')
        return ([{'liga': liga['nombre']}]
                if liga['nombre'] in ('Argentina', 'Peru', 'Chile', 'Paraguay')
                else []), []

    monkeypatch.setattr(modulo, 'recolectar_totw_semana', fake_recolectar)
    monkeypatch.setattr(modulo, 'enriquecer_y_puntuar',
                        lambda filas, api, scorer=None: (RANGING, pd.DataFrame()))

    detalle = {}
    generar_ranking_semanal(_api_fake(set()), '2026-09-28', '2026-10-05',
                            ligas=LIGAS, detalle=detalle)
    assert detalle['ligas_con_totw'] == ['Argentina', 'Peru', 'Chile', 'Paraguay']
    assert detalle['n_ligas_con_totw'] == 4


def test_guardar_cache_escribe_csv(tmp_path):
    ruta = tmp_path / 'cache.csv'
    _guardar_cache({'a|C': {'nombre': 'a', 'club': 'C', 'sentimiento': 1.0}}, ruta)
    previo = pd.read_csv(ruta, encoding='utf-8-sig')
    assert list(previo['nombre']) == ['a']


def test_cache_sentimiento_incremental_no_pierde_trajo(tmp_path):
    """Si el calculo falla a mitad, los jugadores ya hechos quedan cacheados."""
    from sentimiento_radar import calcular_sentimiento

    ruta = tmp_path / 'sentimiento_radar_2026-W40.csv'
    calculados = []

    def calcular(nombre, club, engine=None):
        calculados.append(nombre)
        if nombre == 'C':
            raise RuntimeError('se cayo la cuota')
        return {'nombre': nombre, 'club': club, 'sentimiento': 1.0}

    jugadores = [('A', 'X'), ('B', 'Y'), ('C', 'Z')]
    with pytest.raises(RuntimeError):
        calcular_sentimiento(jugadores, cache_path=ruta, calcular=calcular)

    assert calculados == ['A', 'B', 'C']
    cacheado = pd.read_csv(ruta, encoding='utf-8-sig')
    assert set(cacheado['nombre']) == {'A', 'B'}


def _fake_radar(detalle, n_ligas, ranking=None):
    """Sustituye la consulta a FotMob: llena `detalle` y devuelve el ranking."""
    def radar(detalle_recibido):
        detalle_recibido.update({
            'semana': '2026-W40', 'inicio': '2026-09-28', 'fin': '2026-10-05',
            'ligas_con_totw': [f'Liga{i}' for i in range(n_ligas)],
            'ligas_sin_totw': ['Sin TOTW'],
            'n_ligas_con_totw': n_ligas,
        })
        return (RANGING if ranking is None else ranking), pd.DataFrame(), INICIO
    return radar


INICIO = pd.Timestamp('2026-09-28', tz='UTC')


def test_corrida_sin_gate_no_escribe(monkeypatch):
    monkeypatch.setattr(corrida_semanal, '_radar', _fake_radar({}, 1))
    llamado = {'guardar': 0, 'borrador': False, 'landing': False}
    monkeypatch.setattr(corrida_semanal, 'guardar_resultados',
                        lambda *a: llamado.update(guardar=llamado['guardar'] + 1))
    monkeypatch.setattr(corrida_semanal, 'generar_borrador',
                        lambda *a, **k: llamado.update(borrador=True))
    monkeypatch.setattr(corrida_semanal, '_refrescar_landing',
                        lambda log: llamado.update(landing=True))

    assert corrida(min_ligas=3) == EXIT_SIN_SALIDA
    assert llamado == {'guardar': 0, 'borrador': False, 'landing': False}


def test_corrida_con_gate_hace_todo(monkeypatch):
    monkeypatch.setattr(corrida_semanal, '_radar', _fake_radar({}, 3))
    llamado = {'guardar': 0, 'borrador': 0, 'landing': False}
    monkeypatch.setattr(corrida_semanal, 'guardar_resultados',
                        lambda *a: (llamado.update(guardar=llamado['guardar'] + 1),
                                    ('ranking.csv', 'no_resueltos.csv'))[1])
    monkeypatch.setattr(corrida_semanal, 'generar_borrador', lambda *a, **k: (
        llamado.update(borrador=llamado['borrador'] + 1),
        {'texto': 'x' * 10, 'con_datos': 1, 'jugadores': [('A', 'B')]})[1])
    monkeypatch.setattr(corrida_semanal, '_refrescar_landing',
                        lambda log: llamado.update(landing=True))

    assert corrida(min_ligas=3) == EXIT_OK
    assert llamado == {'guardar': 1, 'borrador': 1, 'landing': True}


def test_corrida_ranking_vacio_da_sin_salida(monkeypatch):
    monkeypatch.setattr(corrida_semanal, '_radar',
                        _fake_radar({}, 3, ranking=pd.DataFrame()))
    assert corrida(min_ligas=3) == EXIT_SIN_SALIDA


def test_corrida_forzar_ignora_el_gate(monkeypatch):
    monkeypatch.setattr(corrida_semanal, '_radar', _fake_radar({}, 1))
    monkeypatch.setattr(corrida_semanal, 'guardar_resultados',
                        lambda *a: ('ranking.csv', 'no_resueltos.csv'))
    monkeypatch.setattr(corrida_semanal, 'generar_borrador', lambda *a, **k: {
        'texto': 'x', 'con_datos': 0, 'jugadores': []})
    monkeypatch.setattr(corrida_semanal, '_refrescar_landing', lambda log: None)
    assert corrida(min_ligas=3, forzar=True) == EXIT_OK


def test_corrida_sin_sentimiento_no_toca_la_tweet(monkeypatch):
    monkeypatch.setattr(corrida_semanal, '_radar', _fake_radar({}, 3))
    monkeypatch.setattr(corrida_semanal, 'guardar_resultados',
                        lambda *a: ('ranking.csv', 'no_resueltos.csv'))

    def no_deberia(*a, **k):
        raise AssertionError('no hay que generar el borrador sin sentimiento')

    monkeypatch.setattr(corrida_semanal, 'generar_borrador', no_deberia)
    monkeypatch.setattr(corrida_semanal, '_refrescar_landing', no_deberia)
    assert corrida(min_ligas=3, con_sentimiento=False) == EXIT_SIN_SALIDA


def test_corrida_falla_si_la_landing_no_se_refresca(monkeypatch):
    monkeypatch.setattr(corrida_semanal, '_radar', _fake_radar({}, 3))
    monkeypatch.setattr(corrida_semanal, 'guardar_resultados',
                        lambda *a: ('ranking.csv', 'no_resueltos.csv'))
    monkeypatch.setattr(corrida_semanal, 'generar_borrador', lambda *a, **k: {
        'texto': 'x', 'con_datos': 0, 'jugadores': []})

    def landing_rota(log):
        raise OSError('data.js en uso')

    monkeypatch.setattr(corrida_semanal, '_refrescar_landing', landing_rota)
    assert corrida(min_ligas=3) == corrida_semanal.EXIT_ERROR


def test_radar_cierra_el_cliente_y_no_guarda(monkeypatch, tmp_path):
    monkeypatch.setattr(corrida_semanal, 'ultimo_bloque_semanal_completo',
                        lambda: (INICIO, INICIO + pd.Timedelta(days=7)))

    def fake_generar(api, ini, fin, detalle=None):
        detalle.update({'semana': '2026-W40', 'n_ligas_con_totw': 1})
        return RANGING, pd.DataFrame(), ['aviso']

    monkeypatch.setattr(corrida_semanal, 'generar_ranking_semanal', fake_generar)

    cerrado = {'ok': False}
    clase = corrida_semanal.FotMobApi

    class ApiConClose(clase):
        def close(self):
            cerrado['ok'] = True

    monkeypatch.setattr(corrida_semanal, 'FotMobApi', ApiConClose)

    detalle = {}
    ranking, no_resueltos, inicio = corrida_semanal._radar(detalle)
    assert not ranking.empty
    assert inicio == INICIO
    assert detalle['n_ligas_con_totw'] == 1
    assert cerrado['ok'] is True
    assert not list(tmp_path.glob('*.csv'))


def test_logger_crea_logs_y_limpia_handlers():
    log = corrida_semanal._logger()
    assert log.handlers
    assert logging.getLogger('corrida_semanal') is log
    corrida_semanal._logger()
    assert len(logging.getLogger('corrida_semanal').handlers) == len(log.handlers)


def test_buscar_videos_devuelve_vacio_si_falla():
    """Un 403 por cuota no debe abortar la corrida semanal."""
    from sentimiento_jugadores_youtube import buscar_videos

    class YoutubeRoto:
        def search(self):
            class Search:
                def list(self, **kwargs):
                    class Exec:
                        def execute(self):
                            raise RuntimeError('quota exceeded')
                    return Exec()
            return Search()

    assert buscar_videos(YoutubeRoto(), 'Jugador', 'Club') == []