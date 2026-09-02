import os
import sys

import pandas as pd

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, SCRIPT_DIR)

MIN_PARTIDOS = 30


def _apps_de_record(record):
    """Apariciones de un registro API (topscorers/topassists/stats)."""
    stats_list = record.get('statistics', [])
    if isinstance(stats_list, list) and stats_list:
        games = stats_list[0].get('games') or {}
        return games.get('appearences', 0) or 0
    return 0


def calcular_trayectoria_desde_records(jugadores_stats):
    """Suma apariciones de cada temporada aportada por topscorers/topassists.

    Los tops ya traen una temporada por registro (2024 y 2023). Para cada
    jugador sumamos las apariciones de todos sus registros = trayectoria total
    sin gastar requests extra.

    Devuelve dict {player_id: {'total': int, 'actuales': int}} y el
    DataFrame con la columna trayectoria_total.
    """
    actuales = {}
    totales = {}
    temporada_por_id = {}
    for record in jugadores_stats:
        pid = (record.get('player') or {}).get('id')
        if not pid:
            continue
        apps = _apps_de_record(record)
        totales[pid] = totales.get(pid, 0) + apps
        season = (record.get('statistics') or [{}])[0].get('league', {}).get('season')
        # la temporada mas reciente = la primera que veamos (2024 viene primero)
        if season not in temporada_por_id.get(pid, {}):
            temporada_por_id.setdefault(pid, {})[season] = apps
    for pid, seasons in temporada_por_id.items():
        # 'actuales' = apariciones de la temporada mas alta
        mejor = max(seasons, key=lambda s: s or 0)
        actuales[pid] = seasons.get(mejor, 0)
    return {'actuales': actuales, 'totales': totales}


def filtrar_por_trayectoria(df_features, info_trayectoria, min_partidos=MIN_PARTIDOS):
    totales = info_trayectoria['totales']
    actuales = info_trayectoria['actuales']
    df = df_features.copy()
    df['trayectoria_total'] = df['player_id'].map(totales).fillna(0).astype(int)
    df['partidos_actuales'] = df['player_id'].map(actuales).fillna(0).astype(int)
    df_filtrado = df[df['trayectoria_total'] >= min_partidos].copy()
    return df_filtrado
