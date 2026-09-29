from datetime import datetime, timezone

from scouting_pipeline import (
    enriquecer_y_puntuar,
    extraer_fixtures_semana,
    extraer_stats_perfil_fotmob,
    generar_ranking_semanal,
    seleccionar_rounds,
    ultimo_bloque_semanal_completo,
)


SEMANA_INICIO = datetime(2026, 9, 14, tzinfo=timezone.utc)
SEMANA_FIN = datetime(2026, 9, 21, tzinfo=timezone.utc)


def test_intervalo_default_es_ultima_semana_iso_completa_utc():
    inicio, fin = ultimo_bloque_semanal_completo(
        datetime(2026, 9, 28, 9, 0, tzinfo=timezone.utc))
    assert inicio == SEMANA_FIN
    assert fin == datetime(2026, 9, 28, 0, 0, tzinfo=timezone.utc)


def fixture(match_id=910, utc='2026-09-16T20:00:00Z', round_name='Regular Season - 5'):
    return {
        'id': match_id,
        'status': {'utcTime': utc, 'finished': True},
        'tournamentRound': {'roundName': round_name},
        'home': {'id': 11, 'name': 'Boca Juniors'},
        'away': {'id': 22, 'name': 'River Plate'},
    }


def fila_totw(match_id=910, dia=16, rating=8.7):
    return {
        'id_fotmob': 1234,
        'nombre_fotmob': 'Juan Perez',
        'team_id_fotmob': '11',
        'club_fotmob': 'Boca Juniors',
        'liga': 'Argentina',
        'liga_id_fotmob': 112,
        'temporada_fotmob': '2026',
        'round_id': '5',
        'match_id_fotmob': match_id,
        'fecha_partido_utc': datetime(2026, 9, dia, tzinfo=timezone.utc),
        'rating_totw': rating,
        'vertical_layout': {'x': 0.5, 'y': 0.9},
    }


def perfil_fotmob(**overrides):
    profile = {
        'id': 1234,
        'name': 'Juan Perez',
        'birthDate': {'utcTime': '2002-04-10T00:00:00.000Z'},
        'primaryTeam': {'teamName': 'Boca Juniors'},
        'positionDescription': {'primaryPosition': {'key': 'striker'}},
        'mainLeague': {
            'leagueId': 112,
            'leagueName': 'Liga Profesional',
            'season': '2026',
            'stats': [
                {'title': 'Goals', 'value': '7'},
                {'title': 'Assists', 'value': '2'},
                {'title': 'Matches', 'value': '10'},
            ],
        },
        # Algunos perfiles repiten stats en firstSeasonStats; no deben sumarse.
        'firstSeasonStats': {'statsSection': {'items': [
            {'title': 'Goals', 'statValue': '99'},
            {'title': 'Assists', 'statValue': '88'},
        ]}},
    }
    profile.update(overrides)
    return profile


def test_extrae_fixtures_anidadas_y_normalizadas_solo_de_la_semana():
    payload = {'fixtures': {'allMatches': [
        fixture(),
        fixture(911, '2026-09-21T00:00:00Z', 'Regular Season - 6'),
        fixture(912, '2026-09-13T23:59:59Z', 'Regular Season - 4'),
        {
            'id': 913,
            'status_utcTime': '2026-09-17T20:00:00Z',
            'tournamentRound_roundName': 'Regular Season - 5',
            'home_id': 11, 'home_name': 'Boca Juniors',
            'away_id': 22, 'away_name': 'River Plate',
        },
    ]}}

    result = extraer_fixtures_semana(payload, SEMANA_INICIO, SEMANA_FIN)

    assert len(result) == 2
    assert {r['match_id'] for r in result} == {910, 913}
    assert result[0]['round_token'] == '5'
    assert result[0]['home_name'] == 'Boca Juniors'


def test_selecciona_rounds_del_fixture_y_excluye_tots():
    rounds = {'rounds': [
        {'roundId': 'TOTS', 'isCompleted': True},
        {'roundId': '6', 'isCompleted': True},
        {'roundId': '5', 'isCompleted': True},
        {'roundId': '4', 'isCompleted': False},
    ]}

    assert seleccionar_rounds(rounds, {'5'}) == ['5']
    assert seleccionar_rounds(rounds, set()) == ['6', '5']


def test_stats_fotmob_usa_solo_main_league_y_confirma_id_club_liga_temporada():
    stats, error = extraer_stats_perfil_fotmob(perfil_fotmob(), fila_totw())

    assert error is None
    assert stats['player_id_fotmob'] == 1234
    assert stats['club'] == 'Boca Juniors'
    assert stats['liga_stats'] == 'Liga Profesional'
    assert stats['temporada_stats'] == '2026'
    assert stats['goles'] == 7
    assert stats['asistencias'] == 2
    assert stats['partidos_temporada'] == 10
    assert stats['edad'] == 24
    assert stats['posicion'] == 'Centre-Forward'


def test_no_acepta_perfil_de_otra_liga_temporada_club_o_id():
    casos = [
        (perfil_fotmob(id=999), fila_totw(), 'id_fotmob_no_coincide'),
        (perfil_fotmob(mainLeague={'leagueId': 268, 'season': '2026', 'stats': []}),
         fila_totw(), 'liga_mainLeague_no_coincide'),
        (perfil_fotmob(mainLeague={'leagueId': 112, 'season': '2025', 'stats': []}),
         fila_totw(), 'temporada_mainLeague_no_coincide'),
        (perfil_fotmob(primaryTeam={'id': 99, 'teamName': 'Otro Club'}),
         fila_totw(), 'club_mainLeague_no_coincide'),
    ]
    for profile, totw, esperado in casos:
        stats, error = extraer_stats_perfil_fotmob(profile, totw)
        assert stats is None
        assert error == esperado


def test_missing_stats_y_arqueros_no_se_puntuan():
    missing = perfil_fotmob(mainLeague={
        'leagueId': 112, 'leagueName': 'Liga Profesional', 'season': '2026',
        'stats': [{'title': 'Goals', 'value': '0'}],
    })
    stats, error = extraer_stats_perfil_fotmob(missing, fila_totw())
    assert stats is None
    assert error == 'feature_requerida_ausente'

    goalkeeper = perfil_fotmob(positionDescription={
        'primaryPosition': {'key': 'keeper'}})
    stats, error = extraer_stats_perfil_fotmob(goalkeeper, fila_totw())
    assert stats is None
    assert error == 'posicion_no_soportada_o_arq'


class FotMobFalso:
    def __init__(self, perfil=None, filas=None):
        self.perfil = perfil or perfil_fotmob()
        self.filas = filas or [fila_totw()]
        self.perfiles_consultados = []

    def temporada_actual(self, league_id, force_refresh=False):
        assert force_refresh
        return '2026'

    def fixtures(self, league_id, season, force_refresh=False):
        assert force_refresh
        return {'fixtures': {'allMatches': [fixture()]}}

    def totw_rounds(self, league_id, season, force_refresh=False):
        assert force_refresh
        return {'rounds': [{'roundId': '5', 'isCompleted': True}]}

    def totw(self, league_id, season, round_id, force_refresh=False):
        assert force_refresh
        return [{
            'id': 1234,
            'name': {'fullName': 'Juan Perez'},
            'teamId': 11,
            'matchId': 910,
            'rating': {'num': '8.7'},
            'verticalLayout': {'x': 0.5, 'y': 0.9},
        }]

    def jugador(self, player_id, force_refresh=False):
        assert force_refresh
        self.perfiles_consultados.append(player_id)
        return self.perfil


def test_pipeline_puntua_con_perfil_fotmob_sin_red_ni_sqlite():
    liga = {'nombre': 'Argentina', 'fotmob_id': 112}

    def scorer(features):
        assert list(features.columns) == ['goles', 'asistencias', 'edad', 'posicion']
        out = features.copy()
        out['probabilidad'] = [0.81] * len(out)
        return out

    fotmob = FotMobFalso()
    ranking, unmatched, avisos = generar_ranking_semanal(
        fotmob, SEMANA_INICIO, SEMANA_FIN, ligas=[liga], scorer=scorer)

    assert avisos == []
    assert unmatched.empty
    assert len(ranking) == 1
    assert ranking.iloc[0]['score_adn_boca'] == 0.81
    assert ranking.iloc[0]['goles'] == 7
    assert ranking.iloc[0]['club'] == 'Boca Juniors'
    assert fotmob.perfiles_consultados == [1234]


def test_missing_stats_profile_queda_no_resuelto_sin_asignar_cero():
    profile = perfil_fotmob(mainLeague={
        'leagueId': 112, 'leagueName': 'Liga Profesional', 'season': '2026',
        'stats': [{'title': 'Assists', 'value': '2'}],
    })

    def scorer(_):
        raise AssertionError('no debe puntuar features incompletas')

    ranking, unmatched = enriquecer_y_puntuar(
        [fila_totw()], FotMobFalso(perfil=profile), scorer=scorer)

    assert ranking.empty
    assert unmatched.iloc[0]['motivo_no_puntuado'] == 'feature_requerida_ausente'


def test_deduplica_jugador_repetido_y_consulta_perfil_una_vez():
    filas = [fila_totw(910, dia=16, rating=8.7),
             fila_totw(911, dia=19, rating=9.1)]

    def scorer(features):
        assert len(features) == 1
        out = features.copy()
        out['probabilidad'] = [0.9]
        return out

    fotmob = FotMobFalso(filas=filas)
    ranking, unmatched = enriquecer_y_puntuar(filas, fotmob, scorer=scorer)

    assert unmatched.empty
    assert len(ranking) == 1
    assert ranking.iloc[0]['apariciones_totw_semana'] == 2
    assert ranking.iloc[0]['rating_totw'] == 9.1
    assert fotmob.perfiles_consultados == [1234]
