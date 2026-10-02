"""Ranking semanal TOTW con fixtures y estadisticas de perfil de FotMob."""

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

from construir_features import aplicar_modelo
from fotmob_api import FotMobApi
from ligas import ligas_activas
from posiciones import (FOTMOB_KEY_ETIQUETA, agrupar_posicion,
                        posicion_desde_layout)


def normalizar_texto(valor):
    texto = unicodedata.normalize('NFKD', str(valor or ''))
    texto = ''.join(c for c in texto if not unicodedata.combining(c))
    return ' '.join(re.sub(r'[^a-z0-9]+', ' ', texto.lower()).split())


def _season_base(valor):
    """Normaliza una temporada quitando el sufijo de fase (Apertura, etapa...)."""
    n = normalizar_texto(valor)
    fases = ('apertura', 'clausura', 'opening', 'closing', 'etapa', 'stage')
    return ' '.join(w for w in n.split() if w not in fases)


def _seasones_coinciden(a, b):
    """Compara temporadas tolerando fases: '2026/2027 - Apertura' == '2026/2027'."""
    na, nb = normalizar_texto(a), normalizar_texto(b)
    if not na or not nb:
        return False
    return na == nb or _season_base(a) == _season_base(b)


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


def extraer_fixtures(payload):
    """Normaliza la lista de fixtures de FotMob, aunque no tenga round."""
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
            if fixture_id is not None and fecha is not None:
                try:
                    match_id = int(fixture_id)
                except (TypeError, ValueError):
                    match_id = None
                token = _round_token(round_raw) if round_raw is not None else ''
                key = (match_id, fecha.isoformat(), token)
                if match_id is not None and key not in vistos:
                    home_id, home_name = _extraer_equipo(obj, 'home')
                    away_id, away_name = _extraer_equipo(obj, 'away')
                    fixtures.append({
                        'match_id': match_id,
                        'fecha_partido_utc': fecha,
                        'round_raw': str(round_raw) if round_raw is not None else '',
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


def extraer_fixtures_semana(payload, inicio, fin):
    """Filtra fixtures por intervalo UTC semiabierto [inicio, fin)."""
    inicio = _parse_fecha(inicio)
    fin = _parse_fecha(fin)
    if inicio is None or fin is None or inicio >= fin:
        raise ValueError('inicio/fin deben formar un intervalo UTC valido')
    return [f for f in extraer_fixtures(payload)
            if inicio <= f['fecha_partido_utc'] < fin]


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
        if not tokens or _round_token(round_id) in tokens:
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

    fixtures_todos = extraer_fixtures(
        api_fotmob.fixtures(liga['fotmob_id'], season, force_refresh=True))
    inicio_dt, fin_dt = _parse_fecha(inicio), _parse_fecha(fin)
    fixtures_semana = [f for f in fixtures_todos
                       if inicio_dt <= f['fecha_partido_utc'] < fin_dt]
    if not fixtures_semana:
        return [], [f"{liga['nombre']} {season}: sin fixtures fechados en la semana"]

    rounds_payload = api_fotmob.totw_rounds(
        liga['fotmob_id'], season, force_refresh=True)
    round_ids = seleccionar_rounds(
        rounds_payload, {f['round_token'] for f in fixtures_semana if f['round_token']})
    if not round_ids:
        return [], [f"{liga['nombre']} {season}: no hay rounds TOTW completados"]

    fixture_por_id = {f['match_id']: f for f in fixtures_todos}
    fixture_ids_semana = {f['match_id'] for f in fixtures_semana}
    filas = []
    avisos = []
    for indice, round_id in enumerate(round_ids):
        totw = api_fotmob.totw(
            liga['fotmob_id'], season, round_id, force_refresh=indice < 3)
        jugadores = totw.get('players', []) if isinstance(totw, dict) else totw
        for jugador in jugadores if isinstance(jugadores, list) else []:
            try:
                match_id = int(jugador.get('matchId'))
            except (TypeError, ValueError):
                continue
            fixture = fixture_por_id.get(match_id)
            if fixture is None or match_id not in fixture_ids_semana:
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
    if not filas:
        avisos.append(
            f"{liga['nombre']} {season}: {len(fixtures_semana)} fixtures en la semana "
            "pero 0 jugadores de TOTW coinciden (el TOTW de la fecha aun puede no "
            "estar publicado)")
    return filas, avisos


def _posicion_perfil_fotmob(profile, layout):
    descripcion = profile.get('positionDescription') or {}
    primary = descripcion.get('primaryPosition') or {}
    key = primary.get('key')
    posicion = (FOTMOB_KEY_ETIQUETA.get(key)
                or FOTMOB_KEY_ETIQUETA.get(str(key).lower()))
    if not posicion and layout:
        posicion = posicion_desde_layout(layout.get('x'), layout.get('y'))
    return posicion


def _es_torneo_seleccion(nombre):
    """Heuristica: torneos de selecciones nacionales (clubes no entren en train)."""
    n = normalizar_texto(nombre)
    if not n:
        return True
    if 'club world cup' in n or 'mundial de clubes' in n or 'copa mundial de clubes' in n:
        return False
    frases = ('qualification', 'qualifier', 'world cup', 'copa america',
              'nations league', 'african cup', 'africa cup', 'gold cup',
              'asian cup', 'olympic', 'confederations', 'eurocopa',
              'euro 20', 'eliminatorias', 'eliminatory',
              'sub 20', 'sub20', 'sub 19', 'sub19', 'sub 17', 'sub17',
              'sub 23', 'sub23', 'u20', 'u19', 'u17', 'u23', 'u21')
    return any(f in n for f in frases)


def torneos_de_temporada(profile, season):
    """Torneos de CLUB de una temporada del perfil; None si la temporada no existe."""
    for s in profile.get('statSeasons') or []:
        if _seasones_coinciden(s.get('seasonName'), season):
            return [t for t in (s.get('tournaments') or [])
                    if not _es_torneo_seleccion(t.get('name'))]
    return None


def _leer_stats_torneo(payload):
    """Extrae Goals/Assists/Matches de un playerStats; None si no hay topStatCard."""
    if not isinstance(payload, dict):
        return None
    items = payload.get('topStatCard') or {}
    valores = {normalizar_texto(i.get('title')): i.get('statValue')
               for i in items.get('items') or []}

    def numero(titulo):
        v = valores.get(titulo)
        if v in (None, ''):
            return None
        try:
            return int(float(v))
        except (TypeError, ValueError):
            return None

    goles, asistencias = numero('goals'), numero('assists')
    if goles is None or asistencias is None:
        return None
    return {'goles': goles, 'asistencias': asistencias,
            'partidos': numero('matches')}


def extraer_stats_temporada_fotmob(profile, fila_totw, api):
    """Suma goles/asist/PJ de todos los torneos de CLUB de la temporada.

    El entrenamiento incluye copas/continental (verificado: partidos > 38 por
    temporada), asi que alinear exige sumar torneos, no solo mainLeague.
    Valida identidad contra el TOTW antes de llamar a la API. Torneo club sin
    goles/asistencias -> no se puntua (faltante != cero); sin 'Matches' solo
    afecta la auditoria, no las features del modelo.
    """
    if not profile:
        return None, 'perfil_fotmob_ausente'
    if str(profile.get('id')) != str(fila_totw.get('id_fotmob')):
        return None, 'id_fotmob_no_coincide'

    main = profile.get('mainLeague') or {}
    if str(main.get('leagueId')) != str(fila_totw.get('liga_id_fotmob')):
        return None, 'liga_mainLeague_no_coincide'
    if not _seasones_coinciden(main.get('season'), fila_totw.get('temporada_fotmob')):
        return None, 'temporada_mainLeague_no_coincide'

    team = profile.get('primaryTeam') or {}
    totw_team_id = fila_totw.get('team_id_fotmob')
    profile_team_id = team.get('id') or team.get('teamId')
    club = team.get('teamName') or team.get('name') or ''
    if totw_team_id and profile_team_id:
        if str(totw_team_id) != str(profile_team_id):
            return None, 'club_mainLeague_no_coincide'
    elif normalizar_texto(club) != normalizar_texto(fila_totw.get('club_fotmob')):
        return None, 'club_mainLeague_no_coincide'

    torneos = torneos_de_temporada(profile, fila_totw.get('temporada_fotmob'))
    if torneos is None:
        return None, 'temporada_stats_ausente'
    if not torneos:
        return None, 'sin_torneos_club_en_temporada'

    goles = asistencias = partidos = 0
    sin_partidos = 0
    nombres = []
    pid = int(profile['id'])
    for torneo in torneos:
        entry = torneo.get('entryId')
        if not entry:
            return None, 'stats_torneo_sin_entryid'
        try:
            payload = api.stats_torneo(pid, entry, force_refresh=True)
        except Exception as exc:
            return None, f'error_stats_torneo_{type(exc).__name__}'
        total = _leer_stats_torneo(payload)
        if total is None:
            return None, 'stats_torneo_incompleto'
        goles += total['goles']
        asistencias += total['asistencias']
        if total['partidos'] is None:
            sin_partidos += 1
        else:
            partidos += total['partidos']
        nombres.append(str(torneo.get('name') or entry))

    birth = profile.get('birthDate') or {}
    edad = _edad_en_fecha({
        'fecha_nacimiento': birth.get('utcTime'),
        'edad': profile.get('age'),
    }, fila_totw['fecha_partido_utc'])
    posicion = _posicion_perfil_fotmob(profile, fila_totw.get('vertical_layout'))
    if not posicion or agrupar_posicion(posicion) == 'Arquero':
        return None, 'posicion_no_soportada_o_arq'
    if edad is None:
        return None, 'feature_requerida_ausente'

    return {
        'player_id_fotmob': profile.get('id'),
        'nombre': profile.get('name') or fila_totw.get('nombre_fotmob'),
        'club': club or fila_totw.get('club_fotmob'),
        'posicion': posicion,
        'edad': edad,
        'goles': goles,
        'asistencias': asistencias,
        'partidos_temporada': partidos,
        'torneos_stats': ', '.join(nombres),
        'torneos_sin_matches': sin_partidos,
        'liga_stats': main.get('leagueName'),
        'temporada_stats': main.get('season'),
        'fuente_stats': 'FotMob playerStats (todos los torneos de club)',
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


def enriquecer_y_puntuar(filas_totw, api_fotmob, scorer=None):
    """Enriquece el TOTW, excluye features desconocidas y puntua una fila/jugador."""
    scorer = scorer or aplicar_modelo
    resueltos, no_resueltos = [], []
    perfiles = {}
    for fila in filas_totw:
        player_id = fila.get('id_fotmob')
        if not player_id:
            no_resueltos.append({**fila, 'motivo_no_puntuado': 'id_fotmob_ausente'})
            continue
        if player_id not in perfiles:
            try:
                profile = api_fotmob.jugador(int(player_id), force_refresh=True)
            except Exception as exc:
                perfiles[player_id] = (None, f'error_fotmob_{type(exc).__name__}')
            else:
                perfiles[player_id] = (profile, None)
        profile, error_profile = perfiles[player_id]
        stats, error_stats = (extraer_stats_temporada_fotmob(profile, fila, api_fotmob)
                              if profile else (None, error_profile or 'perfil_fotmob_ausente'))
        if stats is None:
            no_resueltos.append({**fila, 'motivo_no_puntuado': error_stats})
            continue
        resueltos.append({
            **fila,
            **stats,
        })

    if not resueltos:
        return pd.DataFrame(), pd.DataFrame(no_resueltos)

    # Una entrada por jugador/semana: si fue elegido en varias fechas, conserva
    # el mayor rating TOTW y deja el conteo/ligas para auditoria.
    df = pd.DataFrame(resueltos)
    df['week_key'] = df['fecha_partido_utc'].map(
        lambda d: f'{d.isocalendar().year}-W{d.isocalendar().week:02d}')
    seleccion = []
    for _, grupo in df.groupby('player_id_fotmob', sort=False):
        mejor = grupo.sort_values('rating_totw', ascending=False, na_position='last').iloc[0].copy()
        mejor['apariciones_totw_semana'] = len(grupo)
        mejor['ligas_totw_semana'] = ', '.join(sorted(set(grupo['liga'].astype(str))))
        mejor['fechas_totw_semana'] = ', '.join(sorted(
            {g.isoformat() for g in grupo['fecha_partido_utc']}))
        seleccion.append(mejor)
    df_unico = pd.DataFrame(seleccion).reset_index(drop=True)

    features = df_unico[['goles', 'asistencias', 'edad', 'posicion']].copy()
    scores_df = scorer(features)
    df_unico['score_adn_boca'] = scores_df['probabilidad'].to_numpy()
    if 'probabilidad_adn' in scores_df.columns:
        df_unico['probabilidad_adn'] = scores_df['probabilidad_adn'].to_numpy()
    df_unico = df_unico.sort_values('score_adn_boca', ascending=False).reset_index(drop=True)
    df_unico.insert(0, 'ranking', range(1, len(df_unico) + 1))
    df_unico['estadisticas_as_of_utc'] = datetime.now(timezone.utc).isoformat()
    return df_unico, pd.DataFrame(no_resueltos)


def generar_ranking_semanal(api_fotmob, inicio, fin, ligas=None, scorer=None, detalle=None):
    """Ranking de la semana. `detalle` (opcional) recibe el conteo de ligas con TOTW.

    Una liga cuenta solo si trajo al menos un jugador de TOTW: tener fixtures en la
    semana sin TOTW publicado significa que la fecha aun no se publico, y eso no
    debe habilitar la corrida semanal.
    """
    inicio_dt, fin_dt = _parse_fecha(inicio), _parse_fecha(fin)
    if inicio_dt is None or fin_dt is None or inicio_dt >= fin_dt:
        raise ValueError('Intervalo semanal invalido')
    ligas = ligas if ligas is not None else ligas_activas()
    totw_semana, avisos = [], []
    ligas_con_totw, ligas_sin_totw = [], []
    for liga in ligas:
        try:
            filas, avisos_liga = recolectar_totw_semana(api_fotmob, liga, inicio_dt, fin_dt)
        except Exception as exc:
            avisos.append(f"{liga['nombre']}: error de fuente {type(exc).__name__}: {exc}")
            continue
        totw_semana.extend(filas)
        avisos.extend(avisos_liga)
        (ligas_con_totw if filas else ligas_sin_totw).append(liga['nombre'])
    if detalle is not None:
        iso = inicio_dt.isocalendar()
        detalle.update({
            'semana': f'{iso.year}-W{iso.week:02d}',
            'inicio': inicio_dt.date().isoformat(),
            'fin': fin_dt.date().isoformat(),
            'ligas_consultadas': [liga['nombre'] for liga in ligas],
            'ligas_con_totw': ligas_con_totw,
            'ligas_sin_totw': ligas_sin_totw,
            'n_ligas_con_totw': len(ligas_con_totw),
        })
    if not totw_semana:
        return pd.DataFrame(), pd.DataFrame(), avisos

    resultado, no_resueltos = enriquecer_y_puntuar(
        totw_semana, api_fotmob, scorer=scorer)
    if resultado.empty:
        return resultado, no_resueltos, avisos
    # Si aparece en varias competiciones durante la semana, conserva el mejor
    # score, pero agrega contexto de todas sus apariciones.
    consolidados = []
    for _, grupo in resultado.groupby('player_id_fotmob', sort=False):
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
    return resultado, no_resueltos, avisos


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


def main(detalle=None):
    inicio, fin = ultimo_bloque_semanal_completo()
    fotmob = FotMobApi()
    try:
        ranking, no_resueltos, avisos = generar_ranking_semanal(
            fotmob, inicio, fin, detalle=detalle)
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


if __name__ == '__main__':
    main()
