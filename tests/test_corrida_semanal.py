import logging
import os
import sys
from pathlib import Path

import pandas as pd
import pytest

import corrida_semanal
from corrida_semanal import (
    EXIT_OK,
    EXIT_PARCIAL,
    EXIT_SIN_SALIDA,
    cumple_gate,
    corrida,
)
from scouting_pipeline import generar_ranking_semanal
from sentimiento_radar import _guardar_cache


def _corrida(tmp_path, **kwargs):
    """Corrida con log y datos en el tmp: los tests no tocan outputs/ ni data/."""
    kwargs.setdefault('directorio_log', str(tmp_path))
    kwargs.setdefault('directorio_datos', str(tmp_path))
    return corrida(**kwargs)


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
    def radar(detalle_recibido, inicio=None, fin=None):
        detalle_recibido.update({
            'semana': '2026-W40', 'inicio': '2026-09-28', 'fin': '2026-10-05',
            'ligas_con_totw': [f'Liga{i}' for i in range(n_ligas)],
            'ligas_sin_totw': ['Sin TOTW'],
            'n_ligas_con_totw': n_ligas,
        })
        return (RANGING if ranking is None else ranking), pd.DataFrame(), INICIO
    return radar


INICIO = pd.Timestamp('2026-09-28', tz='UTC')


def test_corrida_sin_gate_no_escribe(monkeypatch, tmp_path):
    monkeypatch.setattr(corrida_semanal, '_radar', _fake_radar({}, 1))
    llamado = {'guardar': 0, 'borrador': False, 'landing': False}
    monkeypatch.setattr(corrida_semanal, 'guardar_resultados',
                        lambda *a, **k: llamado.update(guardar=llamado['guardar'] + 1))
    monkeypatch.setattr(corrida_semanal, 'generar_borrador',
                        lambda *a, **k: llamado.update(borrador=True))
    monkeypatch.setattr(corrida_semanal, '_refrescar_landing',
                        lambda log: llamado.update(landing=True))

    assert _corrida(tmp_path, min_ligas=3) == EXIT_SIN_SALIDA
    assert llamado == {'guardar': 0, 'borrador': False, 'landing': False}


def test_corrida_con_gate_hace_todo(monkeypatch, tmp_path):
    monkeypatch.setattr(corrida_semanal, '_radar', _fake_radar({}, 3))
    llamado = {'guardar': 0, 'borrador': 0, 'landing': False}
    monkeypatch.setattr(corrida_semanal, 'guardar_resultados',
                        lambda *a, **k: (llamado.update(guardar=llamado['guardar'] + 1),
                                         ('ranking.csv', 'no_resueltos.csv'))[1])
    monkeypatch.setattr(corrida_semanal, 'generar_borrador', lambda *a, **k: (
        llamado.update(borrador=llamado['borrador'] + 1),
        {'texto': 'x' * 10, 'con_datos': 1, 'jugadores': [('A', 'B')]})[1])
    monkeypatch.setattr(corrida_semanal, '_refrescar_landing',
                        lambda log: llamado.update(landing=True))

    assert _corrida(tmp_path, min_ligas=3) == EXIT_OK
    assert llamado == {'guardar': 1, 'borrador': 1, 'landing': True}


def test_corrida_ranking_vacio_da_sin_salida(monkeypatch, tmp_path):
    monkeypatch.setattr(corrida_semanal, '_radar',
                        _fake_radar({}, 3, ranking=pd.DataFrame()))
    assert _corrida(tmp_path, min_ligas=3) == EXIT_SIN_SALIDA


def test_corrida_forzar_ignora_el_gate(monkeypatch, tmp_path):
    monkeypatch.setattr(corrida_semanal, '_radar', _fake_radar({}, 1))
    monkeypatch.setattr(corrida_semanal, 'guardar_resultados',
                        lambda *a, **k: ('ranking.csv', 'no_resueltos.csv'))
    monkeypatch.setattr(corrida_semanal, 'generar_borrador', lambda *a, **k: {
        'texto': 'x', 'con_datos': 0, 'jugadores': []})
    monkeypatch.setattr(corrida_semanal, '_refrescar_landing', lambda log: None)
    assert _corrida(tmp_path, min_ligas=3, forzar=True) == EXIT_OK


def test_corrida_sin_sentimiento_no_toca_la_tweet(monkeypatch, tmp_path):
    monkeypatch.setattr(corrida_semanal, '_radar', _fake_radar({}, 3))
    monkeypatch.setattr(corrida_semanal, 'guardar_resultados',
                        lambda *a, **k: ('ranking.csv', 'no_resueltos.csv'))

    def no_deberia(*a, **k):
        raise AssertionError('no hay que generar el borrador sin sentimiento')

    monkeypatch.setattr(corrida_semanal, 'generar_borrador', no_deberia)
    monkeypatch.setattr(corrida_semanal, '_refrescar_landing', no_deberia)
    assert _corrida(tmp_path, min_ligas=3, con_sentimiento=False) == EXIT_PARCIAL


def test_corrida_falla_si_la_landing_no_se_refresca(monkeypatch, tmp_path):
    monkeypatch.setattr(corrida_semanal, '_radar', _fake_radar({}, 3))
    monkeypatch.setattr(corrida_semanal, 'guardar_resultados',
                        lambda *a, **k: ('ranking.csv', 'no_resueltos.csv'))
    monkeypatch.setattr(corrida_semanal, 'generar_borrador', lambda *a, **k: {
        'texto': 'x', 'con_datos': 0, 'jugadores': []})

    def landing_rota(log):
        raise OSError('data.js en uso')

    monkeypatch.setattr(corrida_semanal, '_refrescar_landing', landing_rota)
    assert _corrida(tmp_path, min_ligas=3) == corrida_semanal.EXIT_ERROR


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


def test_logger_crea_logs_y_limpia_handlers(tmp_path):
    log = corrida_semanal._logger(directorio=str(tmp_path))
    assert log.handlers
    assert logging.getLogger('corrida_semanal') is log
    corrida_semanal._logger(directorio=str(tmp_path))
    assert len(logging.getLogger('corrida_semanal').handlers) == len(log.handlers)
    assert list(tmp_path.glob('*.log'))


def test_el_log_de_los_tests_no_toca_outputs(monkeypatch, tmp_path):
    """Los tests escriben el log en el tmp, no en outputs/logs."""
    log_real = Path(corrida_semanal.dir_outputs()) / 'logs' / 'corrida_semanal.log'
    antes = log_real.read_bytes() if log_real.exists() else None

    monkeypatch.setattr(corrida_semanal, '_radar', _fake_radar({}, 1))
    _corrida(tmp_path, min_ligas=3)

    assert list(tmp_path.glob('*.log'))
    despues = log_real.read_bytes() if log_real.exists() else None
    assert despues == antes, 'el test escribio en el log de produccion'


def test_marcador_guarda_y_relee_el_estado(tmp_path):
    ruta = corrida_semanal.guardar_marcador(
        '2026-W42', corrida_semanal.ESTADO_COMPLETA,
        {'n_ligas_con_totw': 3, 'jugadores': 12}, directorio=str(tmp_path))
    assert os.path.exists(ruta)
    marcador = corrida_semanal.leer_marcador('2026-W42', directorio=str(tmp_path))
    assert marcador['estado'] == corrida_semanal.ESTADO_COMPLETA
    assert marcador['n_ligas_con_totw'] == 3
    assert marcador['generado']
    assert corrida_semanal.leer_marcador('2026-W41', directorio=str(tmp_path)) is None


def test_semana_completa_no_se_reprocesa(monkeypatch, tmp_path):
    """Una semana ya completa no vuelve a pegarle a FotMob."""
    llamado = {'radar': 0}

    def radar_que_no_deberia_llamarse(detalle):
        llamado['radar'] += 1
        return pd.DataFrame(), pd.DataFrame(), INICIO

    monkeypatch.setattr(corrida_semanal, '_radar', radar_que_no_deberia_llamarse)
    monkeypatch.setattr(corrida_semanal, '_semana_del_bloque',
                        lambda inicio=None: '2026-W42')
    corrida_semanal.guardar_marcador(
        '2026-W42', corrida_semanal.ESTADO_COMPLETA,
        {'n_ligas_con_totw': 3}, directorio=str(tmp_path))

    assert _corrida(tmp_path, min_ligas=3) == EXIT_OK
    assert llamado['radar'] == 0


def test_semana_con_ranking_retoma_sin_consultar_fotmob(monkeypatch, tmp_path):
    """Si el ranking ya esta escrito, la corrida retoma sin tocar FotMob."""
    RANGING.to_csv(tmp_path / 'ranking_jugadores_fecha_2026-W42.csv',
                   index=False, encoding='utf-8-sig')

    llamado = {'radar': 0}

    def radar_que_no_deberia_llamarse(detalle):
        llamado['radar'] += 1
        return pd.DataFrame(), pd.DataFrame(), INICIO

    monkeypatch.setattr(corrida_semanal, '_radar', radar_que_no_deberia_llamarse)
    monkeypatch.setattr(corrida_semanal, '_semana_del_bloque',
                        lambda inicio=None: '2026-W42')
    corrida_semanal.guardar_marcador(
        '2026-W42', corrida_semanal.ESTADO_RANKING,
        {'n_ligas_con_totw': 3, 'inicio': '2026-10-12', 'fin': '2026-10-19'},
        directorio=str(tmp_path))
    monkeypatch.setattr(corrida_semanal, 'generar_borrador', lambda *a, **k: {
        'texto': 'x', 'con_datos': 0, 'jugadores': []})
    monkeypatch.setattr(corrida_semanal, '_refrescar_landing', lambda log: None)

    assert _corrida(tmp_path, min_ligas=3) == EXIT_OK
    assert llamado['radar'] == 0


def test_forzar_ignora_el_marcador_de_semana_completa(monkeypatch, tmp_path):
    monkeypatch.setattr(corrida_semanal, '_radar', _fake_radar({}, 3))
    monkeypatch.setattr(corrida_semanal, 'guardar_resultados',
                        lambda *a, **k: ('ranking.csv', 'no_resueltos.csv'))
    monkeypatch.setattr(corrida_semanal, 'generar_borrador', lambda *a, **k: {
        'texto': 'x', 'con_datos': 0, 'jugadores': []})
    monkeypatch.setattr(corrida_semanal, '_refrescar_landing', lambda log: None)
    monkeypatch.setattr(corrida_semanal, '_semana_del_bloque',
                        lambda inicio=None: '2026-W42')
    corrida_semanal.guardar_marcador(
        '2026-W42', corrida_semanal.ESTADO_COMPLETA,
        {'n_ligas_con_totw': 3}, directorio=str(tmp_path))

    assert _corrida(tmp_path, min_ligas=3, forzar=True) == EXIT_OK


def test_semana_abierta_no_se_procesa(tmp_path):
    """Una semana que todavia no termino no se puede reprocesar."""
    with pytest.raises(ValueError, match='todavia no esta cerrada'):
        corrida_semanal.bloque_semana_cerrada('2099-W01')


def test_bloque_semana_iso_es_lunes_a_lunes():
    from scouting_pipeline import bloque_semana_iso

    inicio, fin = bloque_semana_iso('2026-W40')
    assert inicio.isoformat() == '2026-09-28T00:00:00+00:00'
    assert fin.isoformat() == '2026-10-05T00:00:00+00:00'


def test_bloque_semana_iso_rechaza_una_semana_invalida():
    from scouting_pipeline import bloque_semana_iso

    with pytest.raises(ValueError):
        bloque_semana_iso('2026-W60')
    with pytest.raises(ValueError):
        bloque_semana_iso('no-es-una-semana')


def test_corrida_con_semana_usa_esa_semana(monkeypatch, tmp_path):
    """Con --semana se reprocesa ese bloque y no el de la ultima semana."""
    pedido = {}

    def radar(detalle, inicio=None, fin=None):
        pedido['inicio'] = inicio
        pedido['fin'] = fin
        detalle.update({'semana': '2026-W40', 'n_ligas_con_totw': 3,
                        'ligas_con_totw': ['A'], 'inicio': '2026-09-28',
                        'fin': '2026-10-05'})
        return RANGING, pd.DataFrame(), inicio

    monkeypatch.setattr(corrida_semanal, '_radar', radar)
    monkeypatch.setattr(corrida_semanal, 'guardar_resultados',
                        lambda *a, **k: ('ranking.csv', 'no_resueltos.csv'))
    monkeypatch.setattr(corrida_semanal, 'generar_borrador', lambda *a, **k: {
        'texto': 'x', 'con_datos': 0, 'jugadores': []})
    monkeypatch.setattr(corrida_semanal, '_refrescar_landing', lambda log: None)
    monkeypatch.setattr(corrida_semanal, '_refrescar_historicos', lambda log, directorio=None: None)

    assert _corrida(tmp_path, min_ligas=3, semana='2026-W40') == EXIT_OK
    assert pedido['inicio'].date().isoformat() == '2026-09-28'
    assert pedido['fin'].date().isoformat() == '2026-10-05'
    marcador = corrida_semanal.leer_marcador('2026-W40', directorio=str(tmp_path))
    assert marcador['semana'] == '2026-W40'


def test_la_corrida_refresca_los_historicos(monkeypatch, tmp_path):
    """Sin这一步 la seccion de menciones de la landing queda vieja."""
    llamado = {'historicos': 0}

    def historicos(log, directorio=None):
        llamado['historicos'] += 1

    monkeypatch.setattr(corrida_semanal, '_radar', _fake_radar({}, 3))
    monkeypatch.setattr(corrida_semanal, 'guardar_resultados',
                        lambda *a, **k: ('ranking.csv', 'no_resueltos.csv'))
    monkeypatch.setattr(corrida_semanal, 'generar_borrador', lambda *a, **k: {
        'texto': 'x', 'con_datos': 0, 'jugadores': []})
    monkeypatch.setattr(corrida_semanal, '_refrescar_landing', lambda log: None)
    monkeypatch.setattr(corrida_semanal, '_refrescar_historicos', historicos)

    assert _corrida(tmp_path, min_ligas=3) == EXIT_OK
    assert llamado['historicos'] == 1


def test_sin_historicos_no_los_refresca(monkeypatch, tmp_path):
    monkeypatch.setattr(corrida_semanal, '_radar', _fake_radar({}, 3))
    monkeypatch.setattr(corrida_semanal, 'guardar_resultados',
                        lambda *a, **k: ('ranking.csv', 'no_resueltos.csv'))
    monkeypatch.setattr(corrida_semanal, 'generar_borrador', lambda *a, **k: {
        'texto': 'x', 'con_datos': 0, 'jugadores': []})
    monkeypatch.setattr(corrida_semanal, '_refrescar_landing', lambda log: None)

    def no_deberia(log, directorio=None):
        raise AssertionError('no hay que refrescar los historicos')

    monkeypatch.setattr(corrida_semanal, '_refrescar_historicos', no_deberia)
    assert _corrida(tmp_path, min_ligas=3, con_historicos=False) == EXIT_OK


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

def test_gate_forzado_queda_marcado_en_el_marcador(monkeypatch, tmp_path):
    monkeypatch.setattr(corrida_semanal, '_radar', _fake_radar({}, 2))
    monkeypatch.setattr(corrida_semanal, 'guardar_resultados',
                        lambda *a, **k: ('ranking.csv', 'no_resueltos.csv'))
    monkeypatch.setattr(corrida_semanal, 'generar_borrador', lambda *a, **k: {
        'texto': 'x', 'con_datos': 0, 'jugadores': []})
    monkeypatch.setattr(corrida_semanal, '_refrescar_landing', lambda log: None)
    monkeypatch.setattr(corrida_semanal, '_refrescar_historicos',
                        lambda log, directorio=None: None)

    monkeypatch.setattr(corrida_semanal, '_semana_del_bloque', lambda inicio=None: '2026-W40')
    assert _corrida(tmp_path, min_ligas=3, forzar=True) == EXIT_OK
    marcador = corrida_semanal.leer_marcador('2026-W40', directorio=str(tmp_path))
    assert marcador['gate_forzado'] is True
    assert marcador['estado'] == corrida_semanal.ESTADO_COMPLETA


def test_gate_cumplido_no_se_marca_como_forzado(monkeypatch, tmp_path):
    monkeypatch.setattr(corrida_semanal, '_radar', _fake_radar({}, 3))
    monkeypatch.setattr(corrida_semanal, 'guardar_resultados',
                        lambda *a, **k: ('ranking.csv', 'no_resueltos.csv'))
    monkeypatch.setattr(corrida_semanal, 'generar_borrador', lambda *a, **k: {
        'texto': 'x', 'con_datos': 0, 'jugadores': []})
    monkeypatch.setattr(corrida_semanal, '_refrescar_landing', lambda log: None)
    monkeypatch.setattr(corrida_semanal, '_refrescar_historicos',
                        lambda log, directorio=None: None)

    monkeypatch.setattr(corrida_semanal, '_semana_del_bloque', lambda inicio=None: '2026-W40')
    assert _corrida(tmp_path, min_ligas=3) == EXIT_OK
    marcador = corrida_semanal.leer_marcador('2026-W40', directorio=str(tmp_path))
    assert marcador['gate_forzado'] is False


def test_la_corrida_regenera_los_historicos_en_su_directorio(monkeypatch, tmp_path):
    """Integracion sin red: la corrida reanuda una semana con ranking guardado,
    genera el sentimiento desde la cache y debe dejar los historicos que lee la
    landing en el mismo directorio de datos."""
    import automatizacion

    RANGING.to_csv(tmp_path / 'ranking_jugadores_fecha_2026-W42.csv',
                   index=False, encoding='utf-8-sig')
    pd.DataFrame([{
        'nombre': 'Jugador 1', 'club': 'Club 1', 'sentimiento': 5.0, 'n_fuentes': 2,
        'fuentes': 'prensa,youtube', 'youtube_valor': 6.0, 'prensa_valor': 4.0,
        'youtube_n_comentarios': 10, 'prensa_n_textos': 8, 'motor': 'vader_lexico_2',
    }]).to_csv(tmp_path / 'sentimiento_radar_2026-W42.csv',
               index=False, encoding='utf-8-sig')
    corrida_semanal.guardar_marcador(
        '2026-W42', corrida_semanal.ESTADO_RANKING,
        {'n_ligas_con_totw': 3, 'inicio': '2026-10-12', 'fin': '2026-10-19'},
        directorio=str(tmp_path))
    monkeypatch.setattr(automatizacion, 'TWEET_TXT', str(tmp_path / 'tweet_top5.txt'))
    monkeypatch.setattr(corrida_semanal, '_refrescar_landing', lambda log: None)

    assert _corrida(tmp_path, min_ligas=3, semana='2026-W42') == EXIT_OK

    assert (tmp_path / 'ranking_historico_acumulado.csv').exists()
    historico = pd.read_csv(tmp_path / 'sentimiento_historico.csv', encoding='utf-8-sig')
    assert set(historico['semana']) == {'2026-W42'}
    assert historico['motor'].iloc[0] == 'vader_lexico_2'
    assert (tmp_path / 'sentimiento_historico_acumulado.csv').exists()
    assert (tmp_path / 'tweet_2026-W42.txt').exists()
    marcador = corrida_semanal.leer_marcador('2026-W42', directorio=str(tmp_path))
    assert marcador['estado'] == corrida_semanal.ESTADO_COMPLETA
    assert marcador['con_historicos'] is True


def test_cli_con_semana_abierta_sale_con_error(monkeypatch, tmp_path):
    monkeypatch.setattr(sys, 'argv', ['corrida_semanal.py', '--semana', '2099-W01',
                                      '--log-dir', str(tmp_path)])
    assert corrida_semanal.main() == corrida_semanal.EXIT_ERROR


def test_radar_rechaza_semana_abierta_antes_de_tocar_fotmob(monkeypatch):
    import scouting_pipeline

    def no_deberia(*a, **k):
        raise AssertionError('no hay que consultar FotMob para una semana abierta')

    monkeypatch.setattr(scouting_pipeline, 'FotMobApi', no_deberia)
    with pytest.raises(ValueError, match='todavia no esta cerrada'):
        scouting_pipeline.main(semana='2099-W01')
