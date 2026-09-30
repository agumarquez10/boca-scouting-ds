from datetime import datetime, timezone

from scouting_pipeline import (
    enriquecer_y_puntuar,
    extraer_fixtures_semana,
    extraer_stats_temporada_fotmob,
    generar_ranking_semanal,
    seleccionar_rounds,
    torneos_de_temporada,
    ultimo_bloque_semanal_completo,
    _es_torneo_seleccion,
    _seasones_coinciden,
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


def stats_payload(goles, asistencias, partidos=None):
    items = [
        {'title': 'Goals', 'statValue': str(goles)},
        {'title': 'Assists', 'statValue': str(asistencias)},
    ]
    if partidos is not None:
        items.append({'title': 'Matches', 'statValue': str(partidos)})
    return {'topStatCard': {'items': items}}


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
        'statSeasons': [{
            'seasonName': '2026',
            'tournaments': [
                {'name': 'Liga Profesional', 'tournamentId': 112, 'entryId': '0-0'},
                {'name': 'Copa Argentina', 'tournamentId': 9305, 'entryId': '0-1'},
                {'name': 'World Cup CONMEBOL qualification',
                 'tournamentId': 10199, 'entryId': '0-2'},
            ],
        }],
        # Trampa: valores repetidos en otra seccion no deben sumarse.
        'firstSeasonStats': {'statsSection': {'items': [
            {'title': 'Goals', 'statValue': '99'},
            {'title': 'Assists', 'statValue': '88'},
        ]}},
    }
    profile.update(overrides)
    return profile


class ApiFalso:
    def __init__(self, perfil=None, stats_por_entry=None):
        self.perfil = perfil if perfil is not None else perfil_fotmob()
        self.stats_por_entry = stats_por_entry or {
            '0-0': stats_payload(7, 2, 10),
            '0-1': stats_payload(0, 0, 2),
        }
        self.llamadas_stats = []

    def jugador(self, player_id, force_refresh=False):
        assert force_refresh
        return self.perfil

    def stats_torneo(self, player_id, season_id, force_refresh=False):
        assert force_refresh
        assert player_id == 1234
        self.llamadas_stats.append(season_id)
        if season_id not in self.stats_por_entry:
            raise KeyError(season_id)
        return self.stats_por_entry[season_id]


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


def test_filtro_selecciones_y_mundial_de_clubes_incluido():
    assert _es_torneo_seleccion('World Cup CONMEBOL qualification')
    assert _es_torneo_seleccion('Copa América')
    assert _es_torneo_seleccion('Sudamericano Sub-20')
    assert not _es_torneo_seleccion('FIFA Club World Cup')
    assert not _es_torneo_seleccion('Copa Libertadores')


def test_matching_de_temporada_tolerante_al_sufijo_de_fase():
    assert _seasones_coinciden('2026/2027 - Apertura', '2026/2027')
    assert _seasones_coinciden('2026/2027', '2026/2027 - Clausura')
    assert _seasones_coinciden('2026', '2026')
    assert not _seasones_coinciden('2026', '2026/2027')
    assert not _seasones_coinciden(None, '2026')
    assert not _seasones_coinciden('', '2026')

    perfil = perfil_fotmob(
        mainLeague={'leagueId': 112, 'leagueName': 'Liga', 'season': '2026/2027',
                    'stats': [{'title': 'Goals', 'value': '7'}]},
        statSeasons=[{'seasonName': '2026/2027',
                      'tournaments': [{'name': 'Liga', 'tournamentId': 112,
                                       'entryId': '0-0'}]}])
    fila = fila_totw()
    fila['temporada_fotmob'] = '2026/2027 - Apertura'
    stats, error = extraer_stats_temporada_fotmob(
        perfil, fila, ApiFalso(stats_por_entry={'0-0': stats_payload(7, 2, 10)}))
    assert error is None
    assert stats['goles'] == 7


def test_torneos_de_temporada_filtra_selecciones():
    torneos = torneos_de_temporada(perfil_fotmob(), '2026')
    assert [t['entryId'] for t in torneos] == ['0-0', '0-1']
    assert torneos_de_temporada(perfil_fotmob(), '2025') is None


def test_suma_todos_los_torneos_club_sin_llamar_a_selecciones():
    api = ApiFalso()
    stats, error = extraer_stats_temporada_fotmob(perfil_fotmob(), fila_totw(), api)

    assert error is None
    assert stats['player_id_fotmob'] == 1234
    assert stats['goles'] == 7
    assert stats['asistencias'] == 2
    assert stats['partidos_temporada'] == 12
    assert stats['torneos_stats'] == 'Liga Profesional, Copa Argentina'
    assert stats['torneos_sin_matches'] == 0
    assert stats['edad'] == 24
    assert stats['posicion'] == 'Centre-Forward'
    assert stats['fuente_stats'] == 'FotMob playerStats (todos los torneos de club)'
    assert api.llamadas_stats == ['0-0', '0-1']


def test_no_acepta_perfil_de_otra_liga_temporada_club_o_id_sin_llamar_stats():
    api = ApiFalso()
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
        stats, error = extraer_stats_temporada_fotmob(profile, totw, api)
        assert stats is None
        assert error == esperado
    assert api.llamadas_stats == []


def test_torneo_sin_goles_o_temporada_ausente_no_se_puntua():
    api = ApiFalso(stats_por_entry={
        '0-0': stats_payload(None, 2, 10),
        '0-1': stats_payload(0, 0, 2),
    })
    stats, error = extraer_stats_temporada_fotmob(perfil_fotmob(), fila_totw(), api)
    assert stats is None
    assert error == 'stats_torneo_incompleto'

    perfil_sin_temporada = perfil_fotmob(statSeasons=[
        {'seasonName': '2025', 'tournaments': [
            {'name': 'Liga Profesional', 'tournamentId': 112, 'entryId': '0-0'}]}])
    stats, error = extraer_stats_temporada_fotmob(perfil_sin_temporada, fila_totw(), api)
    assert stats is None
    assert error == 'temporada_stats_ausente'

    perfil_solo_seleccion = perfil_fotmob(statSeasons=[{
        'seasonName': '2026',
        'tournaments': [{'name': 'World Cup', 'tournamentId': 77, 'entryId': '0-0'}]}])
    stats, error = extraer_stats_temporada_fotmob(perfil_solo_seleccion, fila_totw(), api)
    assert stats is None
    assert error == 'sin_torneos_club_en_temporada'


def test_arquero_y_edad_ausente_no_se_puntuan():
    goalkeeper = perfil_fotmob(positionDescription={
        'primaryPosition': {'key': 'keeper'}})
    stats, error = extraer_stats_temporada_fotmob(goalkeeper, fila_totw(), ApiFalso())
    assert stats is None
    assert error == 'posicion_no_soportada_o_arq'

    sin_nacimiento = perfil_fotmob(birthDate={}, age=None)
    stats, error = extraer_stats_temporada_fotmob(sin_nacimiento, fila_totw(), ApiFalso())
    assert stats is None
    assert error == 'feature_requerida_ausente'


class FotMobFalso(ApiFalso):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
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


def test_pipeline_puntua_con_stats_por_torneo_sin_red_ni_sqlite():
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
    assert fotmob.llamadas_stats == ['0-0', '0-1']


def test_stats_incompletas_quedan_no_resueltas_sin_asignar_cero():
    def scorer(_):
        raise AssertionError('no debe puntuar features incompletas')

    fotmob = FotMobFalso(stats_por_entry={
        '0-0': stats_payload(7, None, 10),
        '0-1': stats_payload(0, 0, 2),
    })
    ranking, unmatched = enriquecer_y_puntuar(
        [fila_totw()], fotmob, scorer=scorer)

    assert ranking.empty
    assert unmatched.iloc[0]['motivo_no_puntuado'] == 'stats_torneo_incompleto'


def test_totw_sin_match_con_fixtures_de_la_semana_emite_aviso():
    class FotMobSinMatch(FotMobFalso):
        def totw(self, *args, **kwargs):
            filas = super().totw(*args, **kwargs)
            for f in filas:
                f['matchId'] = 999
            return filas

    liga = {'nombre': 'USA (MLS)', 'fotmob_id': 130}
    ranking, unmatched, avisos = generar_ranking_semanal(
        FotMobSinMatch(), SEMANA_INICIO, SEMANA_FIN, ligas=[liga],
        scorer=lambda _: AssertionError('no debe puntuar sin filas'))

    assert ranking.empty
    assert unmatched.empty
    assert any('0 jugadores de TOTW coinciden' in a for a in avisos)


def test_deduplica_jugador_repetido_y_consulta_perfil_una_vez():
    filas = [fila_totw(910, dia=16, rating=8.7),
             fila_totw(911, dia=19, rating=9.1)]

    def scorer(features):
        assert len(features) == 1
        out = features.copy()
        out['probabilidad'] = [0.9]
        return out

    fotmob = FotMobFalso()
    ranking, unmatched = enriquecer_y_puntuar(filas, fotmob, scorer=scorer)

    assert unmatched.empty
    assert len(ranking) == 1
    assert ranking.iloc[0]['apariciones_totw_semana'] == 2
    assert ranking.iloc[0]['rating_totw'] == 9.1
    assert fotmob.perfiles_consultados == [1234]
