import pandas as pd
import pytest

import corrida_semanal
import sentimiento_jugadores_prensa as prensa
import sentimiento_jugadores_youtube as yt
from corrida_semanal import EXIT_ERROR, EXIT_OK, EXIT_SIN_SALIDA, corrida, corrida_diaria
from sentimiento_radar import calcular_sentimiento, sentimiento_jugador
from test_corrida_semanal import RANGING, _fake_radar


@pytest.fixture(autouse=True)
def cuota_libre():
    yield
    yt.configurar_cuota(None, None)


class _Req:
    def __init__(self, data):
        self.data = data

    def execute(self):
        return self.data


class FakeYT:
    def __init__(self):
        self.consultas = []

    def search(self):
        outer = self

        class Search:
            def list(self, **kwargs):
                outer.consultas.append('search')
                return _Req({'items': [{'id': {'videoId': 'v1'}}]})
        return Search()

    def commentThreads(self):
        outer = self

        class Comentarios:
            def list(self, **kwargs):
                outer.consultas.append('comentarios')
                texto = {'snippet': {'topLevelComment': {'snippet': {
                    'textDisplay': 'Juan Perez es un crack'}}}}
                return _Req({'items': [texto, texto, texto]})
        return Comentarios()


class FakeEngine:
    def puntuar_lote(self, textos):
        return [1.0] * len(textos)


def _marcar_completa(tmp_path, ligas, ranking=RANGING):
    corrida_semanal.guardar_marcador(
        '2026-W42', corrida_semanal.ESTADO_COMPLETA,
        {'n_ligas_con_totw': len(ligas), 'ligas_con_totw': ligas},
        directorio=str(tmp_path))
    ranking.to_csv(tmp_path / 'ranking_jugadores_fecha_2026-W42.csv',
                   index=False, encoding='utf-8-sig')


def _mocks(monkeypatch, radar, borradores=None):
    monkeypatch.setattr(corrida_semanal, '_radar', radar)
    monkeypatch.setattr(corrida_semanal, '_semana_del_bloque', lambda inicio=None: '2026-W42')
    monkeypatch.setattr(corrida_semanal, '_refrescar_landing', lambda log: None)
    monkeypatch.setattr(corrida_semanal, '_refrescar_historicos',
                        lambda log, directorio=None: None)

    def borrador(*a, **k):
        if borradores is not None:
            borradores.append(k)
        return {'texto': 'x', 'con_datos': 0, 'jugadores': []}

    monkeypatch.setattr(corrida_semanal, 'generar_borrador', borrador)
    escrituras = []
    monkeypatch.setattr(corrida_semanal, 'guardar_resultados',
                        lambda *a, **k: (escrituras.append(1), ('r.csv', 'n.csv'))[1])
    return escrituras


def _corrida_revision(tmp_path, **kwargs):
    return corrida(min_ligas=3, revisar=True, directorio_log=str(tmp_path),
                   directorio_datos=str(tmp_path), **kwargs)


def test_revision_sin_cambios_no_reescribe(monkeypatch, tmp_path):
    _marcar_completa(tmp_path, ['Liga0', 'Liga1', 'Liga2'])
    escrituras = _mocks(monkeypatch, _fake_radar({}, 3))
    assert _corrida_revision(tmp_path) == EXIT_OK
    assert escrituras == []


def test_revision_agrega_liga_tardia(monkeypatch, tmp_path):
    _marcar_completa(tmp_path, ['Liga0', 'Liga1', 'Liga2'])
    escrituras = _mocks(monkeypatch, _fake_radar({}, 4))
    assert _corrida_revision(tmp_path) == EXIT_OK
    assert escrituras == [1]
    marcador = corrida_semanal.leer_marcador('2026-W42', directorio=str(tmp_path))
    assert marcador['n_ligas_con_totw'] == 4
    assert marcador['estado'] == corrida_semanal.ESTADO_COMPLETA


def test_revision_corrige_ranking_que_cambio(monkeypatch, tmp_path):
    _marcar_completa(tmp_path, ['Liga0', 'Liga1', 'Liga2'],
                     ranking=RANGING.assign(score_adn_boca=0.1))
    escrituras = _mocks(monkeypatch, _fake_radar({}, 3))
    assert _corrida_revision(tmp_path) == EXIT_OK
    assert escrituras == [1]


def test_revision_no_reescribe_si_una_liga_dejo_de_publicar(monkeypatch, tmp_path):
    _marcar_completa(tmp_path, ['Liga0', 'Liga1', 'Liga2', 'Liga3'])
    escrituras = _mocks(monkeypatch, _fake_radar({}, 3))
    assert _corrida_revision(tmp_path) == EXIT_OK
    assert escrituras == []


def test_sin_revisar_una_semana_completa_no_consulta_fotmob(monkeypatch, tmp_path):
    _marcar_completa(tmp_path, ['Liga0', 'Liga1', 'Liga2'])

    def no_deberia(*a, **k):
        raise AssertionError('una semana completa sin revisar no pega a FotMob')

    _mocks(monkeypatch, no_deberia)
    assert corrida(min_ligas=3, directorio_log=str(tmp_path),
                   directorio_datos=str(tmp_path)) == EXIT_OK


def test_tweet_principal_solo_para_la_ultima_semana(monkeypatch, tmp_path):
    borradores = []
    _mocks(monkeypatch, _fake_radar({}, 3), borradores)
    monkeypatch.setattr(corrida_semanal, '_ultima_semana_cerrada', lambda: '2026-W43')
    assert _corrida_revision(tmp_path) == EXIT_OK
    assert borradores[0]['escribir_principal'] is False

    borradores.clear()
    monkeypatch.setattr(corrida_semanal, '_ultima_semana_cerrada', lambda: '2026-W42')
    _marcar_completa(tmp_path, ['Liga0', 'Liga1', 'Liga2'])
    corrida(min_ligas=3, forzar=True, directorio_log=str(tmp_path),
            directorio_datos=str(tmp_path))
    assert borradores[0]['escribir_principal'] is True


def test_diaria_revisa_tres_semanas_con_el_tope(monkeypatch):
    llamadas = []
    codigos = iter([EXIT_SIN_SALIDA, EXIT_OK, EXIT_OK])

    def fake(semana=None, **kwargs):
        llamadas.append((semana, kwargs['revisar'], kwargs['cuota_youtube']))
        return next(codigos)

    monkeypatch.setattr(corrida_semanal, 'corrida', fake)
    assert corrida_diaria() == EXIT_SIN_SALIDA
    assert len(llamadas) == 3
    assert all(revisar for _, revisar, _ in llamadas)
    assert all(cuota == 1000 for _, _, cuota in llamadas)
    semanas = [s for s, _, _ in llamadas]
    assert semanas[0] > semanas[1] > semanas[2]


def test_diaria_con_error_devuelve_error(monkeypatch):
    codigos = iter([EXIT_OK, EXIT_ERROR, EXIT_OK])
    monkeypatch.setattr(corrida_semanal, 'corrida', lambda semana=None, **k: next(codigos))
    assert corrida_diaria() == EXIT_ERROR


def test_cli_diaria(monkeypatch, tmp_path):
    import sys
    monkeypatch.setattr(sys, 'argv', ['corrida_semanal.py', '--diaria',
                                      '--log-dir', str(tmp_path)])
    monkeypatch.setattr(corrida_semanal, 'corrida_diaria', lambda **k: EXIT_OK)
    assert corrida_semanal.main() == EXIT_OK


def test_tope_agotado_no_pide_nada_a_youtube(tmp_path, monkeypatch):
    yt.configurar_cuota(str(tmp_path), 50)
    monkeypatch.setattr(yt, 'YOUTUBE_API_KEY', 'x')
    monkeypatch.setattr(yt, '_cliente', lambda: pytest.fail('no debe pedir a YouTube'))
    r = yt.sentimiento_jugador_youtube('Juan Perez', 'Boca', engine=FakeEngine())
    assert not r['ok'] and r['error'] == 'cuota_agotada'


def test_tope_que_corta_a_mitad_marca_pendiente(tmp_path, monkeypatch):
    yt.configurar_cuota(str(tmp_path), 100)
    monkeypatch.setattr(yt, 'YOUTUBE_API_KEY', 'x')
    fake = FakeYT()
    monkeypatch.setattr(yt, '_cliente', lambda: fake)
    r = yt.sentimiento_jugador_youtube('Juan Perez', 'Boca', engine=FakeEngine())
    assert fake.consultas == ['search']
    assert not r['ok'] and r['error'] == 'cuota_agotada'


def test_con_cuota_mide_y_registra_el_consumo(tmp_path, monkeypatch):
    yt.configurar_cuota(str(tmp_path), 1000)
    monkeypatch.setattr(yt, 'YOUTUBE_API_KEY', 'x')
    fake = FakeYT()
    monkeypatch.setattr(yt, '_cliente', lambda: fake)
    r = yt.sentimiento_jugador_youtube('Juan Perez', 'Boca', engine=FakeEngine())
    assert r['ok']
    assert yt.cuota_usada() == 100 + 1


def test_error_de_cuota_de_youtube_frena_el_resto_de_la_corrida(tmp_path, monkeypatch):
    yt.configurar_cuota(str(tmp_path), 1000)

    class Cuota:
        def search(self):
            class Search:
                def list(self, **kwargs):
                    class Exec:
                        def execute(self):
                            raise RuntimeError('quotaExceeded')
                    return Exec()
            return Search()

    assert yt.buscar_videos(Cuota(), 'Jugador', 'Club') == []
    assert not yt.cuota_disponible(1)


def test_sin_tope_no_limita(tmp_path):
    yt.configurar_cuota(None, None)
    assert yt.cuota_disponible(10 ** 6)


def test_jugador_pendiente_por_cuota_no_se_cachea(tmp_path):
    ruta = tmp_path / 'sentimiento_radar_2026-W42.csv'

    def calcular(nombre, club, engine=None):
        return {'nombre': nombre, 'club': club, 'sentimiento': None, 'pendiente': True,
                'textos': {}}

    registros = calcular_sentimiento([('A', 'X')], cache_path=ruta, calcular=calcular)
    assert len(registros) == 1 and 'pendiente' not in registros[0]
    assert not ruta.exists()


def test_sentimiento_jugador_marca_pendiente_si_se_acabo_la_cuota(monkeypatch):
    monkeypatch.setattr(yt, 'sentimiento_jugador_youtube', lambda *a, **k: {
        'ok': False, 'error': 'cuota_agotada', 'valor': 0.0, 'n_comentarios': 0, 'textos': []})
    monkeypatch.setattr(prensa, 'sentimiento_jugador_prensa', lambda *a, **k: {
        'ok': False, 'valor': 0.0, 'n_textos': 0, 'textos': []})
    assert sentimiento_jugador('A', 'X', engine=object())['pendiente'] is True
