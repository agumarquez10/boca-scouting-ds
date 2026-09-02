import os
import sys
import warnings

import pandas as pd

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, SCRIPT_DIR)

from dotenv import load_dotenv
load_dotenv(os.path.join(SCRIPT_DIR, '..', 'secrets', '.env'))

from api_football import ApiFootball
from construir_features import construir_features_batch, aplicar_modelo
from trayectoria import calcular_trayectoria_desde_records, filtrar_por_trayectoria

DATA_DIR = os.path.join(SCRIPT_DIR, '..', 'data')
TEMPORADA_ACTUAL = 2024  # plan Free: acceso solo 2022-2024
MIN_PARTIDOS = 30
UMBRAL_ADN = 0.70
TOP_ESPANA_SEGUNDA = 5

LIGAS = [
    {'nombre': 'Argentina', 'liga_id': 128, 'temporadas': [2024, 2023]},
    {'nombre': 'Uruguay', 'liga_id': 268, 'temporadas': [2024, 2023]},
    {'nombre': 'Brasil', 'liga_id': 71, 'temporadas': [2024, 2023]},
    {'nombre': 'Mexico', 'liga_id': 262, 'temporadas': [2024, 2023]},
    {'nombre': 'USA', 'liga_id': 253, 'temporadas': [2024, 2023]},
    {'nombre': 'Turquia', 'liga_id': 203, 'temporadas': [2024, 2023]},
    {'nombre': 'Espana - LaLiga', 'liga_id': 140, 'temporadas': [2024, 2023]},
    {'nombre': 'Espana - Segunda', 'liga_id': 141, 'temporadas': [2024, 2023],
     'usar_top_equipos': True},
]

warnings.filterwarnings('ignore')


def cargar_ids_equipos_top_segunda(api):
    """Carga los IDs de los 5 primeros equipos de Segunda División española."""
    standings = api.standings(141, 2025)
    if not standings:
        print('  [aviso] No se pudieron obtener standings de Segunda España')
        return []
    grupo = standings[0] if standings else []
    ids = []
    for equipo in grupo[:TOP_ESPANA_SEGUNDA]:
        team = equipo.get('team', {})
        ids.append(team.get('id'))
        print(f'  Top {len(ids)} Segunda España: {team.get("name")} (id={team.get("id")})')
    return ids


def buscar_jugadores_liga(api, liga_config):
    """Busca candidatos de una liga usando top_scorers + top_assists."""
    liga_id = liga_config['liga_id']
    nombre_liga = liga_config['nombre']
    temporadas = liga_config.get('temporadas', [TEMPORADA_ACTUAL, TEMPORADA_ACTUAL - 1])
    usar_top_equipos = liga_config.get('usar_top_equipos', False)

    jugadores_vistos = set()
    jugadores_stats = []

    for season in temporadas:
        print(f'  {nombre_liga} season {season}...')

        tops = []
        try:
            tops += api.top_scorers(liga_id, season)
        except Exception as e:
            print(f'    [error] top_scorers: {e}')

        try:
            tops += api.top_assists(liga_id, season)
        except Exception as e:
            print(f'    [error] top_assists: {e}')

        for item in tops:
            player = item.get('player', {})
            pid = player.get('id')
            if pid and pid not in jugadores_vistos:
                jugadores_vistos.add(pid)

                stats_list = item.get('statistics', [])
                if isinstance(stats_list, list) and stats_list:
                    st = stats_list[0]
                    team_id = (st.get('team') or {}).get('id')
                else:
                    team_id = None

                if usar_top_equipos and team_id:
                    team_ids_top = liga_config.get('_team_ids_top', [])
                    if team_ids_top and team_id not in team_ids_top:
                        continue

                jugadores_stats.append(item)

    return jugadores_stats


def main():
    api_key = os.getenv('API_KEY')
    if not api_key:
        raise ValueError('API_KEY no encontrada en secrets/.env')
    api = ApiFootball(api_key)

    print('=== Scouting de mercado ===')
    print(f'Temporadas: {TEMPORADA_ACTUAL}, {TEMPORADA_ACTUAL - 1}')
    print(f'Minimo partidos trayectoria: {MIN_PARTIDOS}')
    print(f'Umbral ADN Boca: {UMBRAL_ADN}')

    todos_stats = []
    for liga in LIGAS:
        print(f'\n--- {liga["nombre"]} ---')
        if liga.get('usar_top_equipos'):
            ids_top = cargar_ids_equipos_top_segunda(api)
            liga['_team_ids_top'] = ids_top
        stats = buscar_jugadores_liga(api, liga)
        print(f'  Candidatos encontrados: {len(stats)}')
        todos_stats.extend(stats)

    print(f'\nTotal jugadores candidatos (antes de dedup): {len(todos_stats)}')
    seen = set()
    unicos = []
    for s in todos_stats:
        pid = s.get('player', {}).get('id')
        if pid and pid not in seen:
            seen.add(pid)
            unicos.append(s)
    print(f'Después de dedup: {len(unicos)}')

    print('\n--- Construyendo features ---')
    df_features = construir_features_batch(unicos)
    print(f'Features construidas: {len(df_features)} jugadores')

    print('\n--- Calculando trayectoria ---')
    info_trayectoria = calcular_trayectoria_desde_records(unicos)

    df_filtrado = filtrar_por_trayectoria(df_features, info_trayectoria, MIN_PARTIDOS)
    print(f'Con trayectoria >= {MIN_PARTIDOS}: {len(df_filtrado)} jugadores')

    if df_filtrado.empty:
        print('\nNingún jugador cumple el mínimo de partidos.')
        return pd.DataFrame()

    print('\n--- Aplicando modelo ADN Boca ---')
    df_resultado = aplicar_modelo(df_filtrado)
    df_resultado = df_resultado.sort_values('probabilidad', ascending=False).reset_index(drop=True)
    df_pasaron = df_resultado[df_resultado['probabilidad'] >= UMBRAL_ADN].copy()
    print(f'ADN Boca >= {UMBRAL_ADN}: {len(df_pasaron)} jugadores')

    cols_salida = ['nombre', 'player_id', 'club', 'liga', 'posicion', 'edad',
                   'partidos_por_temporada', 'trayectoria_total', 'probabilidad']
    cols_existentes = [c for c in cols_salida if c in df_pasaron.columns]
    df_pasaron = df_pasaron[cols_existentes].copy()

    out_path = os.path.join(DATA_DIR, 'candidatos_adn.csv')
    df_pasaron.to_csv(out_path, index=False, encoding='utf-8-sig')
    print(f'\nGuardado: {out_path} ({len(df_pasaron)} candidatos con ADN >= {UMBRAL_ADN})')

    print('\n=== TOP 10 ADN BOCA ===')
    print(df_pasaron.head(10).to_string(index=False))

    return df_pasaron


if __name__ == '__main__':
    main()
