from datetime import datetime, timezone

from scouting_pipeline import (
    _stats_de_jugador,
    enriquecer_y_puntuar,
    extraer_fixtures_semana,
    generar_ranking_semanal,
    resolver_stats_candidato,
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


def api_player_response():
    return [{
        'player': {
            'id': 99, 'name': 'Juan Perez', 'age': 24,
            'birth': {'date': '2002-04-10'},
        },
        'statistics': [{
            'team': {'id': 50, 'name': 'Boca Juniors'},
            'league': {'id': 8, 'name': 'Liga Profesional', 'season': 2026},
            'games': {'position': 'Forward', 'appearences': 10},
            'goals': {'total': 7, 'assists': 2},
        }],
    }]


def test_extrae_solo_fixtures_de_la_semana_y_normaliza_round():
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
    assert result[0]['match_id'] == 910
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


def test_cruce_api_exige_nombre_club_y_liga_y_agrega_stats_de_equipos():
    response = api_player_response()
    response[0]['statistics'].append({
        'team': {'id': 51, 'name': 'Club Anterior'},
        'league': {'id': 8, 'name': 'Liga Profesional', 'season': 2026},
        'games': {'position': 'Forward', 'appearences': 3},
        'goals': {'total': 1, 'assists': 1},
    })

    stats, error = _stats_de_jugador(response, 'Juan Pérez', 'Boca Juniors', 8)

    assert error is None
    assert stats['player_id_api'] == 99
    assert stats['goles'] == 8
    assert stats['asistencias'] == 3
    assert stats['partidos_temporada'] == 13


def test_no_acepta_club_o_liga_ambiguos():
    stats, error = _stats_de_jugador(api_player_response(), 'Juan Perez', 'Otro Club', 8)
    assert stats is None
    assert error == 'identidad_api_no_univoca'


def test_identifica_limite_de_plan_en_stats_api():
    class ApiPlanLimitado:
        def get(self, endpoint, params, use_cache=True):
            assert endpoint == 'players'
            assert not use_cache
            return {'errors': {'plan': 'Free plans do not have access to this season'}}

    stats, error = resolver_stats_candidato(
        ApiPlanLimitado(), 'Juan Perez', 'Boca Juniors', 8, 2026)

    assert stats is None
    assert error == 'plan_api_sin_acceso_a_temporada'


class FotMobFalso:
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


class ApiFootballFalsa:
    def get(self, endpoint, params, use_cache=True):
        assert not use_cache
        if endpoint == 'leagues':
            return {'response': [{
                'league': {'id': 8, 'name': 'Liga Profesional'},
                'country': {'name': 'Argentina', 'code': 'ARG'},
                'seasons': [{'year': 2026, 'current': True}],
            }]}
        if endpoint == 'players':
            return {'response': api_player_response()}
        raise AssertionError(f'endpoint no esperado: {endpoint}')


def test_pipeline_inyectable_ordena_por_score_sin_red_ni_sqlite():
    liga = {
        'nombre': 'Argentina', 'fotmob_id': 112,
        'api_country': 'Argentina', 'api_league_search': 'Liga Profesional',
    }

    def scorer(features):
        assert list(features.columns) == ['goles', 'asistencias', 'edad', 'posicion']
        out = features.copy()
        out['probabilidad'] = [0.81] * len(out)
        return out

    ranking, unmatched, avisos = generar_ranking_semanal(
        FotMobFalso(), ApiFootballFalsa(), SEMANA_INICIO, SEMANA_FIN,
        ligas=[liga], scorer=scorer)

    assert avisos == []
    assert unmatched.empty
    assert len(ranking) == 1
    assert ranking.iloc[0]['score_adn_boca'] == 0.81
    assert ranking.iloc[0]['goles'] == 7
    assert ranking.iloc[0]['club'] == 'Boca Juniors'


def test_no_puntua_stats_ausentes_como_si_fueran_cero():
    response = api_player_response()
    response[0]['statistics'][0]['goals'] = {'total': None, 'assists': 2}
    stats, _ = _stats_de_jugador(response, 'Juan Perez', 'Boca Juniors', 8)
    assert stats['goles'] is None


def test_stats_ausentes_quedan_en_no_resueltos_y_no_llegan_al_modelo():
    response = api_player_response()
    response[0]['statistics'][0]['goals'] = {'total': None, 'assists': 2}

    class ApiSinGoles:
        def get(self, endpoint, params, use_cache=True):
            assert not use_cache
            return {'response': response}

    fila = {
        'id_fotmob': 1234, 'nombre_fotmob': 'Juan Perez',
        'club_fotmob': 'Boca Juniors', 'liga': 'Argentina',
        'liga_id_fotmob': 112, 'temporada_fotmob': '2026',
        'round_id': '5', 'match_id_fotmob': 910,
        'fecha_partido_utc': datetime(2026, 9, 16, tzinfo=timezone.utc),
        'rating_totw': 8.7, 'vertical_layout': {'x': 0.5, 'y': 0.9},
    }

    ranking, unmatched = enriquecer_y_puntuar(
        [fila], ApiSinGoles(), 8, 2026,
        scorer=lambda _: (_ for _ in ()).throw(AssertionError('no debe puntuar')))

    assert ranking.empty
    assert unmatched.iloc[0]['motivo_no_puntuado'] == 'feature_requerida_ausente'


def test_deduplica_jugador_repetido_en_la_semana_y_guarda_apariciones():
    class Api:
        def get(self, endpoint, params, use_cache=True):
            assert not use_cache
            return {'response': api_player_response()}

    filas = []
    for match_id, day, rating in [(910, 16, 8.7), (911, 19, 9.1)]:
        filas.append({
            'id_fotmob': 1234, 'nombre_fotmob': 'Juan Perez',
            'club_fotmob': 'Boca Juniors', 'liga': 'Argentina',
            'liga_id_fotmob': 112, 'temporada_fotmob': '2026',
            'round_id': str(match_id), 'match_id_fotmob': match_id,
            'fecha_partido_utc': datetime(2026, 9, day, tzinfo=timezone.utc),
            'rating_totw': rating, 'vertical_layout': {'x': 0.5, 'y': 0.9},
        })

    def scorer(features):
        out = features.copy()
        out['probabilidad'] = [0.9]
        return out

    ranking, unmatched = enriquecer_y_puntuar(filas, Api(), 8, 2026, scorer=scorer)

    assert unmatched.empty
    assert len(ranking) == 1
    assert ranking.iloc[0]['apariciones_totw_semana'] == 2
    assert ranking.iloc[0]['rating_totw'] == 9.1
