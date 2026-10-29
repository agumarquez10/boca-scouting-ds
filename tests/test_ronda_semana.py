from datetime import datetime, timezone

from scouting_pipeline import _ronda_en_semana, recolectar_totw_semana
from test_scouting_pipeline import fixture


W43 = (datetime(2026, 9, 14, tzinfo=timezone.utc), datetime(2026, 9, 21, tzinfo=timezone.utc))
W44 = (datetime(2026, 9, 21, tzinfo=timezone.utc), datetime(2026, 9, 28, tzinfo=timezone.utc))
LIGA = {'nombre': 'Argentina', 'fotmob_id': 112}


def jugador(i, match_id):
    return {'id': i, 'name': {'fullName': f'Jugador {i}'}, 'teamId': 11,
            'matchId': match_id, 'rating': {'num': '7.0'},
            'verticalLayout': {'x': 0.5, 'y': 0.5}}


class ApiRondas:
    def __init__(self, partidos, rondas):
        self.partidos = partidos
        self.rondas = rondas

    def temporada_actual(self, league_id, force_refresh=False):
        return '2026'

    def fixtures(self, league_id, season, force_refresh=False):
        return {'fixtures': {'allMatches': self.partidos}}

    def totw_rounds(self, league_id, season, force_refresh=False):
        return {'rounds': [{'roundId': r, 'isCompleted': True} for r in self.rondas]}

    def totw(self, league_id, season, round_id, force_refresh=False):
        return self.rondas[round_id]


def test_ronda_pertenece_a_la_semana_de_la_mayoria_de_partidos():
    d = lambda dia, hora=20: datetime(2026, 9, dia, hora, tzinfo=timezone.utc)
    assert _ronda_en_semana([d(18), d(19), d(22)], *W43)
    assert not _ronda_en_semana([d(18), d(22), d(23)], *W43)


def test_empate_exacto_lo_decide_la_fecha_mediana():
    d = lambda dia: datetime(2026, 9, dia, 20, tzinfo=timezone.utc)
    assert not _ronda_en_semana([d(20), d(22)], *W43)
    assert _ronda_en_semana([d(20), d(22)], *W44)


def test_ronda_que_cruza_el_corte_queda_completa_en_una_sola_semana():
    partidos = [
        fixture(910, utc='2026-09-20T20:00:00Z'),
        fixture(911, utc='2026-09-20T22:00:00Z'),
        fixture(912, utc='2026-09-21T00:30:00Z'),
    ]
    rondas = {'14': [jugador(1, 910), jugador(2, 911), jugador(3, 912)]}
    api = ApiRondas(partidos, rondas)

    filas_w43, _ = recolectar_totw_semana(api, LIGA, *W43)
    filas_w44, _ = recolectar_totw_semana(api, LIGA, *W44)

    assert len(filas_w43) == 3
    assert filas_w44 == []
