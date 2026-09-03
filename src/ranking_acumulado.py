"""
Acumula el 11 ideal (Team of the Week) historico de todas las ligas activas.

Por cada liga y temporada configuradas en ligas.py, descarga el 11 ideal de
todas las fechas/rounds publicadas. Para cada jugador del 11 ideal, obtiene
las features del modelo via FotMob (get_player) y la trayectoria (minimo 30
partidos en 2 temporadas).

Salida: data/11ideal_historico.csv con todos los registros, y un DataFrame
filtrado con los que cumplen trayectoria minima.

Cada corrida es incremental: si el CSV ya existe, solo agrega fechas/rounds
nuevos que no estaban procesados. La cache de FotMob evita llamadas repetidas.
"""

import os
import sys
from datetime import datetime, timezone

import pandas as pd

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, SCRIPT_DIR)

from fotmob_api import FotMobApi
from fotmob_features import build_features_fotmob, trayectoria_2_temporadas
from ligas import ligas_activas, ligas_saltadas

DATA_DIR = os.path.join(SCRIPT_DIR, '..', 'data')
HISTORICO_CSV = os.path.join(DATA_DIR, '11ideal_historico.csv')
MIN_PARTIDOS = 30


def cargar_historico():
    if os.path.exists(HISTORICO_CSV):
        return pd.read_csv(HISTORICO_CSV, encoding='utf-8-sig')
    return pd.DataFrame()


def _round_key(liga_id, temporada, round_id):
    return f'{liga_id}|{temporada}|{round_id}'


def procesar_liga(api, liga_config):
    """Descarga el 11 ideal de todos los rounds de una liga/temporada."""
    nombre = liga_config['nombre']
    lid = liga_config['fotmob_id']
    temporadas = liga_config.get('temporadas_totw', [])
    fecha_hoy = datetime.now(timezone.utc).isoformat()

    filas = []

    for season in temporadas:
        print(f'  {nombre} season={season}...')
        rounds_data = api.totw_rounds(lid, season)

        if not isinstance(rounds_data, dict) or not rounds_data.get('rounds'):
            print(f'    [aviso] sin rounds para {nombre} {season}')
            continue

        rounds = rounds_data['rounds']
        # excluir TOTS (es una ronda especial, no fecha de liga)
        rounds = [r for r in rounds if r.get('roundId', '').lower() != 'tots']
        print(f'    {len(rounds)} rounds a procesar')

        for r in rounds:
            rid = r.get('roundId')
            rk = _round_key(lid, season, rid)
            jugadores = api.totw(lid, season, rid)

            if not isinstance(jugadores, list):
                continue

            for j in jugadores:
                pid = j.get('id')
                if not pid:
                    continue

                try:
                    pdata = api.jugador(pid)
                    vl = j.get('verticalLayout', {})
                    feats = build_features_fotmob(pdata, pid, temporadas=2, layout=vl)
                    total_apps, n_temp = trayectoria_2_temporadas(pdata)

                    rating_raw = j.get('rating', {}).get('num')
                    try:
                        rating_toot = float(rating_raw) if rating_raw else None
                    except (ValueError, TypeError):
                        rating_toot = None

                    filas.append({
                        'id_fotmob': pid,
                        'nombre': feats['nombre'],
                        'posicion': feats['posicion'],
                        'posicion_key': feats['posicion_key'],
                        'grupo_posicion': feats['grupo_posicion'],
                        'club': feats['club'],
                        'team_id_totw': j.get('teamId'),
                        'liga': nombre,
                        'liga_id_fotmob': lid,
                        'temporada_totw': season,
                        'round_id': rid,
                        'round_key': rk,
                        'edad': feats['edad'],
                        'temporadas_en_dataset': feats['temporadas_en_dataset'],
                        'partidos_por_temporada': feats['partidos_por_temporada'],
                        'perfil_ofensivo': feats['perfil_ofensivo'],
                        'pases_precisos': feats['pases_precisos'],
                        'trayectoria_total': total_apps,
                        'n_temporadas': n_temp,
                        'rating_toot': rating_toot,
                        'layout_x': vl.get('x'),
                        'layout_y': vl.get('y'),
                        'fecha_captura': fecha_hoy,
                    })

                except Exception as e:
                    print(f'    [error] player {pid}: {e}')
                    continue

    return pd.DataFrame(filas)


def main(solo_ligas=None):
    """Acumula el 11 ideal de todas las ligas (o solo las de `solo_ligas`).

    `solo_ligas` opcional: lista de nombres a procesar (para correr de a una).
    Guarda el CSV incrementalmente tras cada liga, asi un corte no pierde el
    progreso (la cache SQLite tambien se conserva entre corridas).
    """
    # Avisar ligas saltadas
    saltadas = ligas_saltadas()
    if saltadas:
        print('=== Ligas sin TOTW en FotMob (se saltan) ===')
        for l in saltadas:
            print(f"  - {l['nombre']}: {l.get('razon_skip', '')}")

    activas = ligas_activas()
    if solo_ligas:
        activas = [l for l in activas if l['nombre'] in solo_ligas]
        print(f'\nProcesando solo: {solo_ligas}')
    print(f'\nLigas activas: {len(activas)}')
    for l in activas:
        print(f"  - {l['nombre']} (id={l['fotmob_id']})")
    print()

    df_hist = cargar_historico()
    rks_existentes = set()
    if not df_hist.empty and 'round_key' in df_hist.columns:
        rks_existentes = set(df_hist['round_key'].unique())
        print(f'Historico existente: {len(df_hist)} filas, {len(rks_existentes)} rounds')

    api = FotMobApi()

    for liga in activas:
        print(f'--- {liga["nombre"]} ---')
        df_liga = procesar_liga(api, liga)
        if not df_liga.empty:
            mask = ~df_liga['round_key'].isin(rks_existentes)
            df_nuevo = df_liga[mask].copy()
            print(f'  Total capturados: {len(df_liga)}, nuevos: {len(df_nuevo)}')

            if not df_nuevo.empty:
                if not df_hist.empty:
                    df_hist = pd.concat([df_hist, df_nuevo], ignore_index=True)
                else:
                    df_hist = df_nuevo
                rks_existentes.update(df_liga['round_key'].unique())
                os.makedirs(DATA_DIR, exist_ok=True)
                df_hist.to_csv(HISTORICO_CSV, index=False, encoding='utf-8-sig')
                print(f'  Guardado parcial tras {liga["nombre"]}: {len(df_hist)} filas')
        else:
            print('  Sin datos nuevos')

    api.close()

    if df_hist.empty:
        print('\nSin datos acumulados.')
        return pd.DataFrame()

    df_hist.to_csv(HISTORICO_CSV, index=False, encoding='utf-8-sig')
    print(f'\nHistorico final: {HISTORICO_CSV} ({len(df_hist)} filas)')

    # Filtrar por trayectoria
    df_filtrado = df_hist[df_hist['trayectoria_total'] >= MIN_PARTIDOS].copy()
    df_filtrado = df_filtrado.sort_values('rating_toot', ascending=False).reset_index(drop=True)
    print(f'Con trayectoria >= {MIN_PARTIDOS}: {len(df_filtrado)} jugadores')

    if not df_filtrado.empty:
        cols = ['nombre', 'liga', 'posicion', 'edad', 'trayectoria_total',
                'rating_toot', 'pases_precisos']
        cols_ok = [c for c in cols if c in df_filtrado.columns]
        print('\n=== TOP 15 por rating ===')
        print(df_filtrado.head(15)[cols_ok].to_string(index=False))

    return df_filtrado


if __name__ == '__main__':
    main()
