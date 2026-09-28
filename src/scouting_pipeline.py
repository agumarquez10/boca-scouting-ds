"""Ranking semanal de jugadores de los Team of the Week de FotMob.

FotMob aporta las alineaciones y fechas; API-Football aporta estadisticas de
la temporada activa. Solo se puntua un snapshot por jugador y semana.
"""

import os
import re
import sys
import unicodedata
from datetime import date, datetime, time, timedelta, timezone

import pandas as pd

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT_DIR = os.path.dirname(SCRIPT_DIR)
DATA_DIR = os.path.join(ROOT_DIR, 'data')
sys.path.insert(0, SCRIPT_DIR)

from api_football import ApiFootball
from construir_features import aplicar_modelo
from fotmob_api import FotMobApi
from ligas import ligas_activas
from posiciones import agrupar_posicion, posicion_desde_layout


def normalizar_texto(valor):
    texto = unicodedata.normalize('NFKD', str(valor or ''))
    texto = ''.join(c for c in texto if not unicodedata.combining(c))
    return ' '.join(re.sub(r'[^a-z0-9]+', ' ', texto.lower()).split())


def ultimo_bloque_semanal_completo(referencia=None):
    """Devuelve [lunes 00:00 UTC, lunes siguiente 00:00 UTC), ya completado."""
    ahora = referencia or datetime.now(timezone.utc)
    if ahora.tzinfo is None:
        ahora = ahora.replace(tzinfo=timezone.utc)
    hoy_utc = ahora.astimezone(timezone.utc).date()
    lunes_actual = hoy_utc - timedelta(days=hoy_utc.weekday())
    lunes_previo = lunes_actual - timedelta(days=7)
    return (datetime.combine(lunes_previo, time.min, timezone.utc),
            datetime.combine(lunes_actual, time.min, timezone.utc))


def _parse_fecha(valor):
    if isinstance(valor, datetime):
        dt = valor
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    if isinstance(valor, date):
        return datetime.combine(valor, time.min, timezone.utc)
    if isinstance(valor, (int, float)):
        # FotMob suele serializar unix time en segundos o milisegundos.
        escala = 1000 if abs(valor) > 10_000_000_000 else 1
        return datetime.fromtimestamp(valor / escala, tz=timezone.utc)
    if not isinstance(valor, str) or not valor.strip():
        return None
    texto = valor.strip().replace('Z', '+00:00')
    try:
        dt = datetime.fromisoformat(texto)
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _buscar_recursivo(obj, claves):
    if isinstance(obj, dict):
        for clave in claves:
            if clave in obj and obj[clave] not in (None, ''):
                return obj[clave]
        for valor in obj.values():
            encontrado = _buscar_recursivo(valor, claves)
            if encontrado not in (None, ''):
                return encontrado
    elif isinstance(obj, list):
        for valor in obj:
            encontrado = _buscar_recursivo(valor, claves)
            if encontrado not in (None, ''):
                return encontrado
    return None


def _round_token(valor):
    texto = normalizar_texto(valor)
    if not texto:
        return ''
    numeros = re.findall(r'\d+', texto)
    return numeros[-1] if numeros else texto


def _extraer_equipo(fixture, lado):
    posibles = [fixture.get(lado), fixture.get(f'{lado}Team'),
                fixture.get(f'{lado}_team')]
    for equipo in posibles:
        if isinstance(equipo, dict):
            nombre = equipo.get('name') or equipo.get('teamName') or equipo.get('shortName')
            equipo_id = equipo.get('id') or equipo.get('teamId')
            if nombre or equipo_id:
                return equipo_id, nombre
        elif isinstance(equipo, str) and equipo:
            return None, equipo
    nombre = fixture.get(f'{lado}_name') or fixture.get(f'{lado}Name')
    equipo_id = fixture.get(f'{lado}_id') or fixture.get(f'{lado}Id')
    return equipo_id, nombre


def extraer_fixtures_semana(payload, inicio, fin):
    """Normaliza fixtures FotMob dentro de la semana y retiene el round.

    Se aceptan las formas anidadas y normalizadas que devuelve FotMob. Si una
    fixture no trae fecha o round identificable, se omite: asignarle una semana
    o ronda por aproximacion podria mezclar jugadores de fechas distintas.
    """
    inicio = _parse_fecha(inicio)
    fin = _parse_fecha(fin)
    if inicio is None or fin is None or inicio >= fin:
        raise ValueError('inicio/fin deben formar un intervalo UTC valido')

    fixtures = []
    vistos = set()

    def recorrer(obj):
        if isinstance(obj, dict):
            fixture_id = obj.get('id') or obj.get('matchId')
            fecha_raw = _buscar_recursivo(obj, (
                'status_utcTime', 'utcTime', 'matchTimeUTC', 'kickoffUTC', 'date'))
            fecha = _parse_fecha(fecha_raw)
            round_raw = _buscar_recursivo(obj, (
                'roundId', 'roundName', 'tournamentRound_roundName',
                'tournamentRound_name', 'round_name', 'round_number',
                'round', 'tournamentRound'))
            if fixture_id is not None and fecha is not None and round_raw is not None:
                try:
                    match_id = int(fixture_id)
                except (TypeError, ValueError):
                    match_id = None
                token = _round_token(round_raw)
                key = (match_id, fecha.isoformat(), token)
                if (match_id is not None and token and inicio <= fecha < fin
                        and key not in vistos):
                    home_id, home_name = _extraer_equipo(obj, 'home')
                    away_id, away_name = _extraer_equipo(obj, 'away')
                    fixtures.append({
                        'match_id': match_id,
                        'fecha_partido_utc': fecha,
                        'round_raw': str(round_raw),
                        'round_token': token,
                        'home_id': str(home_id) if home_id is not None else '',
                        'home_name': home_name or '',
                        'away_id': str(away_id) if away_id is not None else '',
                        'away_name': away_name or '',
                    })
                    vistos.add(key)
            for valor in obj.values():
                recorrer(valor)
        elif isinstance(obj, list):
            for valor in obj:
                recorrer(valor)

    recorrer(payload)
    return fixtures


def seleccionar_rounds(rounds_payload, fixture_round_tokens):
    rounds = rounds_payload.get('rounds', []) if isinstance(rounds_payload, dict) else []
    tokens = set(fixture_round_tokens)
    elegidos = []
    for item in rounds:
        if isinstance(item, dict):
            round_id = item.get('roundId')
            completado = item.get('isCompleted', True)
        else:
            round_id, completado = item, True
        if not round_id or str(round_id).strip().lower() == 'tots' or not completado:
            continue
        if _round_token(round_id) in tokens:
            elegidos.append(str(round_id))
    return list(dict.fromkeys(elegidos))


def _equipo_del_jugador(jugador_totw, fixture):
    team_id = jugador_totw.get('teamId')
    if team_id is None:
        return ''
    team_id = str(team_id)
    if team_id == fixture['home_id']:
        return fixture['home_name']
    if team_id == fixture['away_id']:
        return fixture['away_name']
    return ''


def recolectar_totw_semana(api_fotmob, liga, inicio, fin):
    """Obtiene solo los jugadores cuyo partido cayó en la semana solicitada."""
    season = api_fotmob.temporada_actual(liga['fotmob_id'], force_refresh=True)
    if not season:
        return [], [f"{liga['nombre']}: FotMob no devolvio temporada actual"]

    fixtures = extraer_fixtures_semana(
        api_fotmob.fixtures(liga['fotmob_id'], season, force_refresh=True), inicio, fin)
    if not fixtures:
        return [], [f"{liga['nombre']} {season}: sin fixtures fechados/round en la semana"]

    rounds_payload = api_fotmob.totw_rounds(
        liga['fotmob_id'], season, force_refresh=True)
    round_ids = seleccionar_rounds(
        rounds_payload, {f['round_token'] for f in fixtures})
    if not round_ids:
        return [], [f"{liga['nombre']} {season}: no se pudo asociar fixture con round TOTW"]

    fixture_por_id = {f['match_id']: f for f in fixtures}
    filas = []
    avisos = []
    for round_id in round_ids:
        totw = api_fotmob.totw(
            liga['fotmob_id'], season, round_id, force_refresh=True)
        jugadores = totw.get('players', []) if isinstance(totw, dict) else totw
        for jugador in jugadores if isinstance(jugadores, list) else []:
            try:
                match_id = int(jugador.get('matchId'))
            except (TypeError, ValueError):
                continue
            fixture = fixture_por_id.get(match_id)
            if fixture is None:
                continue
            rating = (jugador.get('rating') or {}).get('num')
            try:
                rating = float(rating) if rating not in (None, '') else None
            except (TypeError, ValueError):
                rating = None
            filas.append({
                'id_fotmob': jugador.get('id'),
                'nombre_fotmob': ((jugador.get('name') or {}).get('fullName')
                                  or jugador.get('name') or ''),
                'team_id_fotmob': str(jugador.get('teamId') or ''),
                'club_fotmob': _equipo_del_jugador(jugador, fixture),
                'liga': liga['nombre'],
                'liga_id_fotmob': liga['fotmob_id'],
                'temporada_fotmob': season,
                'round_id': round_id,
                'match_id_fotmob': match_id,
                'fecha_partido_utc': fixture['fecha_partido_utc'],
                'rating_totw': rating,
                'vertical_layout': jugador.get('verticalLayout') or {},
            })
    return filas, avisos


def resolver_liga_api_football(api_football, liga, semana):
    parametros = {
        'country': liga['api_country'],
        'search': liga['api_league_search'],
    }
    # La cache global no tiene TTL: refrescar la temporada activa semanalmente.
    payload = api_football.get('leagues', parametros, use_cache=False)
    respuesta = payload.get('response', [])
    termino = normalizar_texto(liga['api_league_search'])
    candidatas = []
    for item in respuesta:
        league = item.get('league') or {}
        if (item.get('country', {}).get('name', '').lower() != liga['api_country'].lower()
                and item.get('country', {}).get('code', '').lower() != liga['api_country'].lower()):
            continue
        if termino not in normalizar_texto(league.get('name')):
            continue
        temporadas = item.get('seasons') or []
        actuales = [s for s in temporadas if s.get('current')]
        if not actuales:
            actuales = [s for s in temporadas if str(s.get('year')) == str(semana.year)]
        for season in actuales:
            candidatas.append((league.get('id'), season.get('year')))
    candidatas = list(dict.fromkeys((lid, year) for lid, year in candidatas if lid and year))
    if len(candidatas) != 1:
        raise LookupError(
            f"Liga API-Football ambigua/sin temporada actual para {liga['nombre']}: {candidatas}")
    return int(candidatas[0][0]), int(candidatas[0][1])


def _stats_de_jugador(response, nombre, club, league_id):
    """Cruza nombre+club+liga y agrega stats si API-Football lista varios equipos."""
    nombre_key, club_key = normalizar_texto(nombre), normalizar_texto(club)
    candidatos = []
    for item in response or []:
        player = item.get('player') or {}
        if normalizar_texto(player.get('name')) != nombre_key:
            continue
        stats_liga = [s for s in item.get('statistics', [])
                      if str((s.get('league') or {}).get('id')) == str(league_id)]
        stats_club = [s for s in stats_liga
                      if normalizar_texto((s.get('team') or {}).get('name')) == club_key]
        if stats_club:
            candidatos.append((player, stats_liga, stats_club))
    ids = {str(p.get('id')) for p, _, _ in candidatos if p.get('id') is not None}
    if len(ids) != 1 or not candidatos:
        return None, 'identidad_api_no_univoca'

    player = candidatos[0][0]
    stats_liga = candidatos[0][1]
    stat_actual = candidatos[0][2][-1]
    goles, asistencias, partidos = 0, 0, 0
    hubo_goles, hubo_asist, hubo_partidos = False, False, False
    for stat in stats_liga:
        goals = stat.get('goals') or {}
        games = stat.get('games') or {}
        if goals.get('total') is not None:
            goles += int(goals['total'])
            hubo_goles = True
        if goals.get('assists') is not None:
            asistencias += int(goals['assists'])
            hubo_asist = True
        if games.get('appearences') is not None:
            partidos += int(games['appearences'])
            hubo_partidos = True

    birth_date = ((player.get('birth') or {}).get('date'))
    position = ((stat_actual.get('games') or {}).get('position'))
    return {
        'player_id_api': player.get('id'),
        'nombre': player.get('name') or nombre,
        'edad': player.get('age'),
        'fecha_nacimiento': birth_date,
        'goles': goles if hubo_goles else None,
        'asistencias': asistencias if hubo_asist else None,
        'partidos_temporada': partidos if hubo_partidos else None,
        'posicion_api': position,
        'club_api': (stat_actual.get('team') or {}).get('name', ''),
    }, None


def _edad_en_fecha(stats, fecha):
    nacimiento = _parse_fecha(stats.get('fecha_nacimiento'))
    if nacimiento:
        d = fecha.date() if isinstance(fecha, datetime) else fecha
        return d.year - nacimiento.year - ((d.month, d.day) < (nacimiento.month, nacimiento.day))
    try:
        return int(stats['edad']) if stats.get('edad') is not None else None
    except (TypeError, ValueError):
        return None


def resolver_stats_candidato(api_football, nombre, club, league_id, season):
    if len(normalizar_texto(nombre)) < 4:
        return None, 'nombre_insuficiente_para_busqueda'
    payload = api_football.get('players', {
        'search': nombre, 'league': league_id, 'season': season,
    }, use_cache=False)
    return _stats_de_jugador(payload.get('response', []), nombre, club, league_id)


def enriquecer_y_puntuar(filas_totw, api_football, liga_api_id, season_api, scorer=None):
    """Enriquece el TOTW, excluye features desconocidas y puntua una fila/jugador."""
    scorer = scorer or aplicar_modelo
    resueltos, no_resueltos = [], []
    cache_stats = {}
    for fila in filas_totw:
        nombre, club = fila['nombre_fotmob'], fila['club_fotmob']
        cache_key = (normalizar_texto(nombre), normalizar_texto(club), liga_api_id, season_api)
        if cache_key not in cache_stats:
            try:
                cache_stats[cache_key] = resolver_stats_candidato(
                    api_football, nombre, club, liga_api_id, season_api)
            except Exception as exc:
                cache_stats[cache_key] = (None, f'error_api_{type(exc).__name__}')
        stats, razon = cache_stats[cache_key]
        if stats is None:
            no_resueltos.append({**fila, 'motivo_no_puntuado': razon})
            continue

        posicion = stats.get('posicion_api')
        if not posicion:
            layout = fila.get('vertical_layout') or {}
            if layout:
                posicion = posicion_desde_layout(layout.get('x'), layout.get('y'))
        if not posicion or agrupar_posicion(posicion) == 'Arquero':
            no_resueltos.append({**fila, 'motivo_no_puntuado': 'posicion_no_soportada_o_arq'})
            continue

        stats['edad'] = _edad_en_fecha(stats, fila['fecha_partido_utc'])
        if any(stats.get(c) is None for c in ('edad', 'goles', 'asistencias')):
            no_resueltos.append({**fila, 'motivo_no_puntuado': 'feature_requerida_ausente'})
            continue
        resueltos.append({
            **fila,
            'player_id_api': stats['player_id_api'],
            'nombre': stats['nombre'],
            'club': stats['club_api'] or club,
            'posicion': posicion,
            'edad': stats['edad'],
            'goles': stats['goles'],
            'asistencias': stats['asistencias'],
            'partidos_temporada': stats['partidos_temporada'],
            'api_liga_id': liga_api_id,
            'api_season': season_api,
        })

    if not resueltos:
        return pd.DataFrame(), pd.DataFrame(no_resueltos)

    # Una entrada por jugador/semana: si fue elegido en varias fechas, conserva
    # el mayor rating TOTW y deja el conteo/ligas para auditoria.
    df = pd.DataFrame(resueltos)
    df['week_key'] = df['fecha_partido_utc'].map(
        lambda d: f'{d.isocalendar().year}-W{d.isocalendar().week:02d}')
    seleccion = []
    for _, grupo in df.groupby('player_id_api', sort=False):
        mejor = grupo.sort_values('rating_totw', ascending=False, na_position='last').iloc[0].copy()
        mejor['apariciones_totw_semana'] = len(grupo)
        mejor['ligas_totw_semana'] = ', '.join(sorted(set(grupo['liga'].astype(str))))
        mejor['fechas_totw_semana'] = ', '.join(sorted(
            {g.isoformat() for g in grupo['fecha_partido_utc']}))
        seleccion.append(mejor)
    df_unico = pd.DataFrame(seleccion).reset_index(drop=True)

    features = df_unico[['goles', 'asistencias', 'edad', 'posicion']].copy()
    scores = scorer(features)['probabilidad'].to_numpy()
    df_unico['score_adn_boca'] = scores
    df_unico = df_unico.sort_values('score_adn_boca', ascending=False).reset_index(drop=True)
    df_unico.insert(0, 'ranking', range(1, len(df_unico) + 1))
    df_unico['estadisticas_as_of_utc'] = datetime.now(timezone.utc).isoformat()
    return df_unico, pd.DataFrame(no_resueltos)


def generar_ranking_semanal(api_fotmob, api_football, inicio, fin,
                            ligas=None, scorer=None):
    inicio_dt, fin_dt = _parse_fecha(inicio), _parse_fecha(fin)
    if inicio_dt is None or fin_dt is None or inicio_dt >= fin_dt:
        raise ValueError('Intervalo semanal invalido')
    ligas = ligas if ligas is not None else ligas_activas()
    totw_semana, avisos = [], []
    for liga in ligas:
        try:
            filas, avisos_liga = recolectar_totw_semana(api_fotmob, liga, inicio_dt, fin_dt)
        except Exception as exc:
            avisos.append(f"{liga['nombre']}: error de fuente {type(exc).__name__}: {exc}")
            continue
        totw_semana.extend(filas)
        avisos.extend(avisos_liga)
    if not totw_semana:
        return pd.DataFrame(), pd.DataFrame(), avisos

    por_liga = {}
    for fila in totw_semana:
        por_liga.setdefault(fila['liga'], []).append(fila)

    rankings, no_resueltos = [], []
    liga_por_nombre = {l['nombre']: l for l in ligas}
    for nombre_liga, filas in por_liga.items():
        liga = liga_por_nombre[nombre_liga]
        try:
            league_id, season = resolver_liga_api_football(api_football, liga, inicio_dt)
        except Exception as e:
            avisos.append(str(e))
            no_resueltos.extend({**r, 'motivo_no_puntuado': 'liga_api_no_resuelta'} for r in filas)
            continue
        ranking, unmatched = enriquecer_y_puntuar(
            filas, api_football, league_id, season, scorer=scorer)
        if not ranking.empty:
            rankings.append(ranking)
        if not unmatched.empty:
            no_resueltos.extend(unmatched.to_dict('records'))

    if not rankings:
        return pd.DataFrame(), pd.DataFrame(no_resueltos), avisos
    resultado = pd.concat(rankings, ignore_index=True)
    # Si aparece en varias competiciones durante la semana, conserva el mejor
    # score, pero agrega contexto de todas sus apariciones.
    consolidados = []
    for _, grupo in resultado.groupby('player_id_api', sort=False):
        mejor = grupo.sort_values('score_adn_boca', ascending=False).iloc[0].copy()
        mejor['apariciones_totw_semana'] = int(grupo['apariciones_totw_semana'].sum())
        mejor['ligas_totw_semana'] = ', '.join(sorted(
            {liga for lista in grupo['ligas_totw_semana'] for liga in str(lista).split(', ')}))
        mejor['fechas_totw_semana'] = ', '.join(sorted(
            {fecha for lista in grupo['fechas_totw_semana'] for fecha in str(lista).split(', ')}))
        consolidados.append(mejor)
    resultado = (pd.DataFrame(consolidados)
                 .sort_values('score_adn_boca', ascending=False).reset_index(drop=True))
    resultado['ranking'] = range(1, len(resultado) + 1)
    return resultado, pd.DataFrame(no_resueltos), avisos


def guardar_resultados(ranking, no_resueltos, inicio, directorio=DATA_DIR):
    inicio = _parse_fecha(inicio)
    if inicio is None:
        raise ValueError('inicio no es una fecha valida')
    iso = inicio.isocalendar()
    semana = f'{iso.year}-W{iso.week:02d}'
    os.makedirs(directorio, exist_ok=True)
    ranking_path = os.path.join(directorio, f'ranking_jugadores_fecha_{semana}.csv')
    no_resueltos_path = os.path.join(directorio, f'jugadores_fecha_no_resueltos_{semana}.csv')
    ranking.to_csv(ranking_path, index=False, encoding='utf-8-sig')
    no_resueltos.to_csv(no_resueltos_path, index=False, encoding='utf-8-sig')
    return ranking_path, no_resueltos_path


def main():
    from dotenv import load_dotenv
    from rutas import dir_secrets

    load_dotenv(os.path.join(dir_secrets(), '.env'))
    api_key = os.getenv('API_KEY')
    if not api_key:
        raise RuntimeError('Falta API_KEY en secrets/.env')

    inicio, fin = ultimo_bloque_semanal_completo()
    fotmob = FotMobApi()
    football = ApiFootball(api_key)
    try:
        ranking, no_resueltos, avisos = generar_ranking_semanal(
            fotmob, football, inicio, fin)
        for aviso in avisos:
            print(f'[aviso] {aviso}')
        if ranking.empty:
            print('No hubo jugadores puntuables en el período.')
            return ranking
        ranking_path, unmatched_path = guardar_resultados(ranking, no_resueltos, inicio)
        print(f'Ranking: {ranking_path} ({len(ranking)} jugadores)')
        print(f'No resueltos: {unmatched_path} ({len(no_resueltos)} filas)')
        print(ranking.head(10)[['ranking', 'nombre', 'club', 'liga', 'score_adn_boca']]
              .to_string(index=False))
        return ranking
    finally:
        fotmob.close()
        football.session.close()


if __name__ == '__main__':
    main()
