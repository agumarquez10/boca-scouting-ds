"""
Scouting de mercado: busqueda de candidatos via 11 ideal de FotMob.

Pipeline completo:
  1. ranking_acumulado → 11 ideal historico (TODAS las posiciones)
  2. Dedup por jugador (mejor rating) + filtro edad < 32
  3. aplicar_modelo → probabilidad ADN Boca (0.0-1.0)
  4. Filtro binario: probabilidad >= UMBRAL_ADN (0.50)
  5. Resolver club desde el TOTW (get_player/primaryTeam) para nombres faltantes
  6. Guarda data/candidatos_adn.csv y top diverso (max 1 por posicion)

Fuente: FotMob Team of the Week (11 ideal de cada fecha de cada liga).
Trajectory: minimo 30 partidos en 2 temporadas (validado en ranking_acumulado).
"""

import os
import sys

import pandas as pd

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, SCRIPT_DIR)

from ranking_acumulado import main as acumular_11ideal
from construir_features import aplicar_modelo
from ligas import ligas_saltadas, ligas_activas
from fotmob_api import FotMobApi

DATA_DIR = os.path.join(SCRIPT_DIR, '..', 'data')
UMBRAL_ADN = 0.50
MIN_PARTIDOS = 30
MAX_EDAD = 32


def dedup_por_jugador(df):
    """Un jugador puede aparecer en varios rounds. Conservamos el de mayor
    rating_toot para representarlo."""
    if df.empty or 'rating_toot' not in df.columns:
        return df
    df = df.dropna(subset=['rating_toot'])
    idx = df.groupby('id_fotmob')['rating_toot'].idxmax()
    return df.loc[idx].copy()


def _club_de_jugador(p):
    """Mejor esfuerzo para el club actual de un get_player de FotMob."""
    prim = p.get('primaryTeam') or {}
    nombre = prim.get('teamName') or prim.get('name') or ''
    if nombre:
        return nombre
    ch = (p.get('careerHistory') or {}).get('careerItems') or {}
    senior = ch.get('senior') or {}
    entries = senior.get('seasonEntries') or []
    if entries:
        t = entries[-1].get('team') or ''
        if isinstance(t, dict):
            return t.get('name') or t.get('shortName') or ''
        return str(t)
    return ''


def resolver_club(api, df):
    """Completa el club de los candidatos sin nombre usando get_player cacheado.

    Fuente preferida: primaryTeam.teamName del get_player; fallback en la
    ultima entrada del careerHistory (club mas reciente).
    """
    if df.empty or 'club' not in df.columns:
        return df
    df = df.copy()
    faltan = df['club'].isna() | (df['club'] == '')
    if not faltan.any():
        return df
    ids = df.loc[faltan, 'id_fotmob'].unique().tolist()
    nombre_por_id = {}
    for pid in ids:
        try:
            p = api.jugador(int(pid))
            nombre_por_id[pid] = _club_de_jugador(p)
        except Exception:
            nombre_por_id[pid] = ''
    df['club'] = df.apply(
        lambda r: r['club'] if (r['club'] and not pd.isna(r['club'])) else nombre_por_id.get(r['id_fotmob'], ''),
        axis=1,
    )
    return df


def seleccionar_top_diverso(df, n=5, por_posicion='grupo_posicion'):
    """Maximo 1 jugador por posicion (grupo), ordenado por probabilidad desc."""
    df = df.copy()
    if por_posicion not in df.columns:
        return df.head(n)
    top = []
    usadas = set()
    rank = df.sort_values('probabilidad', ascending=False)
    for _, fila in rank.iterrows():
        pos = fila.get(por_posicion)
        if pos is None or pos in usadas:
            continue
        usadas.add(pos)
        top.append(fila)
        if len(top) >= n:
            break
    return pd.DataFrame(top)


def main():
    print('=== Scouting de mercado (11 ideal FotMob) ===')
    print(f'Umbral ADN Boca: {UMBRAL_ADN} (binario)')
    print(f'Minimo partidos trayectoria: {MIN_PARTIDOS}')
    print(f'Edad maxima: < {MAX_EDAD}')

    # 1) Acumular 11 ideal historico de todas las ligas
    df_hist = acumular_11ideal()

    if df_hist.empty:
        print('\nSin datos de 11 ideal. Abortando.')
        return pd.DataFrame()

    # 1b) Excluir ligas saltadas (ej. Espana por costos, Uruguay sin TOTW).
    # El historico acumulado puede contener filas de ligas que ya no estan activas.
    if 'liga' in df_hist.columns:
        activas = {l['nombre'] for l in ligas_activas()}
        antes = len(df_hist)
        df_hist = df_hist[df_hist['liga'].isin(activas)].copy()
        print(f'Excluidas ligas inactivas: {antes} -> {len(df_hist)} registros')

    # 2) Filtrar trayectoria
    df_hist = df_hist[df_hist['trayectoria_total'] >= MIN_PARTIDOS].copy()
    print(f'\nDespues de filtro trayectoria >= {MIN_PARTIDOS}: {len(df_hist)} registros')

    # 2b) Filtrar edad < 32
    df_hist = df_hist[df_hist['edad'] < MAX_EDAD].copy()
    print(f'Despues de filtro edad < {MAX_EDAD}: {len(df_hist)} registros')

    if df_hist.empty:
        print('Ningun jugador cumple los filtros.')
        return pd.DataFrame()

    # 3) Dedup por jugador (mejor rating)
    df_unique = dedup_por_jugador(df_hist)
    print(f'Despues de dedup: {len(df_unique)} jugadores unicos')

    # 3b) Imputar pases_precisos faltantes con la mediana del batch.
    if 'pases_precisos' in df_unique.columns:
        df_unique['pases_faltante'] = (df_unique['pases_precisos'] == 0.0) | df_unique['pases_precisos'].isna()
        mediana = df_unique.loc[~df_unique['pases_faltante'], 'pases_precisos'].median()
        faltantes = int(df_unique['pases_faltante'].sum())
        print(f'  pases_precisos faltantes: {faltantes} -> imputados con mediana {mediana:.1f}')
        df_unique.loc[df_unique['pases_faltante'], 'pases_precisos'] = mediana

    # 4) Aplicar modelo ADN Boca
    print('\n--- Aplicando modelo ADN Boca ---')
    df_resultado = aplicar_modelo(df_unique)
    df_resultado = df_resultado.sort_values('probabilidad', ascending=False).reset_index(drop=True)

    # 5) Filtro binario
    df_pasaron = df_resultado[df_resultado['probabilidad'] >= UMBRAL_ADN].copy()
    print(f'ADN Boca >= {UMBRAL_ADN}: {len(df_pasaron)} candidatos')

    if df_pasaron.empty:
        print('\nNingun jugador supera el umbral de ADN Boca.')
        return pd.DataFrame()

    # 6) Resolver club faltante desde el TOTW (get_player / primaryTeam)
    api = FotMobApi()
    df_pasaron = resolver_club(api, df_pasaron)
    api.close()

    # 6b) Excluir jugadores que ya juegan o jugaron en Boca (no son fichajes de
    # mercado: el club resuelto puede quedar como 'Boca Juniors' por historial).
    if 'club' in df_pasaron.columns:
        es_boca = df_pasaron['club'].astype(str).str.lower().str.strip() == 'boca juniors'
        n_boca = int(es_boca.sum())
        df_pasaron = df_pasaron[~es_boca].copy()
        print(f'Excluidos {n_boca} jugadores de Boca Juniors (no son fichajes)')

    # 7) Guardar CSV de candidatos
    os.makedirs(DATA_DIR, exist_ok=True)
    cols_salida = ['id_fotmob', 'nombre', 'club', 'liga', 'posicion', 'grupo_posicion',
                   'edad', 'pases_precisos', 'partidos_por_temporada', 'trayectoria_total',
                   'n_temporadas', 'rating_toot', 'probabilidad', 'fecha_captura']
    cols_ok = [c for c in cols_salida if c in df_pasaron.columns]
    df_out = df_pasaron[cols_ok].copy()

    out_path = os.path.join(DATA_DIR, 'candidatos_adn.csv')
    df_out.to_csv(out_path, index=False, encoding='utf-8-sig')
    print(f'\nGuardado: {out_path} ({len(df_out)} candidatos)')

    print('\n=== TOP 15 CANDIDATOS ADN BOCA ===')
    print(df_out.head(15).to_string(index=False))

    # 8) Top diverso (max 1 por posicion)
    top5 = seleccionar_top_diverso(df_out, n=5)
    print('\n=== TOP 5 DIVERSO (max 1 por posicion) ===')
    print(top5[['nombre', 'club', 'liga', 'posicion', 'edad', 'probabilidad']].to_string(index=False))

    # 9) Avisar ligas saltadas
    saltadas = ligas_saltadas()
    if saltadas:
        print('\n=== Ligas sin TOTW (se omitieron) ===')
        for l in saltadas:
            print(f"  - {l['nombre']}: {l.get('razon_skip', '')}")

    return df_out


if __name__ == '__main__':
    main()
