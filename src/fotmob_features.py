"""
Extraccion de features del modelo desde el perfil de jugador de FotMob.

El modelo ADN Boca (config.pkl) usa:
  pases_precisos, edad, temporadas_en_dataset, partidos_por_temporada,
  perfil_ofensivo + dummies de posicion.

FotMob (get_player) provee:
  - edad: desde birthDate
  - partidos: mainLeague.stats[title=="Matches"] (temporada actual)
  - pases_precisos: firstSeasonStats.statsSection[title=="Pass accuracy"]
  - posicion: positionDescription.primaryPosition.key -> grupo del modelo
"""

from datetime import date, datetime

from posiciones import (
    posicion_fotmob_a_grupo,
    es_perfil_ofensivo_fotmob,
    FOTMOB_KEY_ETIQUETA,
    posicion_desde_layout,
)


def _stats_section_titulo(player_data):
    fs = player_data.get('firstSeasonStats')
    if isinstance(fs, dict):
        ss = fs.get('statsSection')
        if isinstance(ss, dict):
            return ss
        ns = fs.get('mainStatsSection')
        if isinstance(ns, dict):
            return ns
    return None


def _buscar_stat(node, titulo):
    """Devuelve el valor (o None) del stat con `title == titulo`, buscando
    recursivamente en el arbol de `firstSeasonStats`."""
    if isinstance(node, dict):
        if node.get('title') == titulo:
            return node.get('statValue')
        for v in node.values():
            r = _buscar_stat(v, titulo)
            if r is not None:
                return r
    elif isinstance(node, list):
        for item in node:
            r = _buscar_stat(item, titulo)
            if r is not None:
                return r
    return None


def _buscar_main_stat(player_data, titulo):
    ml = player_data.get('mainLeague')
    if isinstance(ml, dict):
        for item in ml.get('stats', []) or []:
            if item.get('title') == titulo:
                return item.get('value')
    return None


def _edad_desde_birth(birth_data):
    if not isinstance(birth_data, dict):
        return 0
    utc = birth_data.get('utcTime')
    if not utc:
        return 0
    try:
        nac = datetime.fromisoformat(utc[:10]).date()
        hoy = date.today()
        return hoy.year - nac.year - ((hoy.month, hoy.day) < (nac.month, nac.day))
    except (ValueError, TypeError):
        return 0


def posicion_key(player_data):
    pd_ = player_data.get('positionDescription') or {}
    prim = pd_.get('primaryPosition') or {}
    key = prim.get('key')
    if key:
        return key
    for pos in pd_.get('positions', []) or []:
        spr = pos.get('strPos') or {}
        if pos.get('isMainPosition') and spr.get('key'):
            return spr.get('key')
    return None


def matches_temporada(player_data):
    val = _buscar_main_stat(player_data, 'Matches')
    if val is None:
        val = _buscar_main_stat(player_data, 'Started')
    try:
        return int(val or 0)
    except (TypeError, ValueError):
        return 0


def pases_precisos(player_data):
    val = _buscar_stat(_stats_section_titulo(player_data), 'Pass accuracy')
    if val is None and _stats_section_titulo(player_data) is None:
        # cae a la estructura completa como respaldo
        val = _buscar_stat(player_data, 'Pass accuracy')
    try:
        return float(val) if val is not None else None
    except (TypeError, ValueError):
        return None


def temporadas_en_dataset(player_data):
    """Devuelve las temporadas de carrera del jugador (solo informativo).

    NOTA: el feature `temporadas_en_dataset` del modelo NO puede usar la
    carrera completa (13-15 años para veteranos); para el scouting se fija en
    las temporadas de la ventana (2024 + 2023 = 2). Ver build_features_fotmob.
    """
    seasons = player_data.get('statSeasons')
    if isinstance(seasons, list) and seasons:
        return len(seasons)
    return 1


def trayectoria_2_temporadas(player_data, n_temporadas=2):
    """Partidos totales en las n_temporadas mas recientes (sin llamadas extra).

    Devuelve (total_partidos, n_temporadas_disponibles).
    Usa careerHistory.seasonEntries que viene en get_player.
    """
    ch = (player_data.get('careerHistory') or {}).get('careerItems') or {}
    senior = ch.get('senior') or {}
    entries = senior.get('seasonEntries') or []
    total = 0
    usadas = 0
    for e in entries[:n_temporadas]:
        try:
            apps = int(e.get('appearances', 0) or 0)
        except (ValueError, TypeError):
            apps = 0
        total += apps
        usadas += 1
    return total, usadas


def build_features_fotmob(player_data, player_id=None, temporadas=2, layout=None):
    """Construye las features del modelo para un jugador de FotMob.

    `temporadas` = temporadas observadas en la ventana de scouting (por defecto
    2: 2024 + 2023). El modelo fue entrenado con paridad de ventana, no con la
    carrera completa.
    `layout` opcional (dict x/y del TOTW) usado como fallback de posicion si
    FotMob no reporta positionDescription.primaryPosition.
    """
    pkey = posicion_key(player_data)
    if not pkey and layout is not None:
        pkey = posicion_desde_layout(layout.get('x'), layout.get('y'))
    nombre = player_data.get('name', '')
    prim = player_data.get('primaryTeam') or {}
    ml = player_data.get('mainLeague') or {}
    pases = pases_precisos(player_data)
    matches = matches_temporada(player_data)

    club = prim.get('teamName', '') or ''
    liga = ml.get('leagueName', '') or ''

    grupo = posicion_fotmob_a_grupo(pkey)

    # Etiqueta que GRUPOS_POSICION reconoce (ej. "Right Winger", no "Extremo").
    # El PositionEncoder del modelo espera esta etiqueta para generar dummies.
    etiqueta = FOTMOB_KEY_ETIQUETA.get(pkey) or pkey or ''

    return {
        'nombre': nombre,
        'player_id_fotmob': player_id or player_data.get('id'),
        'edad': _edad_desde_birth(player_data.get('birthDate')),
        'temporadas_en_dataset': temporadas,
        'partidos_por_temporada': matches,
        'perfil_ofensivo': int(es_perfil_ofensivo_fotmob(pkey)),
        'posicion': etiqueta or 'Midfielder',
        'posicion_key': pkey,
        'grupo_posicion': grupo,
        'club': club,
        'liga': liga,
        'pases_precisos': pases if pases is not None else 0.0,
    }
