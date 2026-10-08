"""Ranking historico: agrega apariciones en el top 5 de los rankings semanales.

Lee los `data/ranking_jugadores_fecha_YYYY-Www.csv` y consolida por
`player_id_fotmob` (identidad estable, no por nombre).

Criterio: contar solo el top 5 crudo favorece a las ligas con mas TOTW (Brasil
aporta ~60% de las apariciones). Por eso se reporta tambien `tasa_top5`, la
fraccion de semanas en que la liga principal del jugador tuvo TOTW y el jugador
entro al top 5. `apariciones_totw` suma las selecciones de FotMob de las semanas.
Los goles/asistencias son acumulados de temporada: se toman de la ultima
aparicion, NO se suman entre semanas.
"""

import os
import re

import pandas as pd

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(os.path.dirname(SCRIPT_DIR), 'data')

PATRON_RANKING = re.compile(r'ranking_jugadores_fecha_(\d{4})-W(\d{2})\.csv$')


def cargar_rankings(directorio=DATA_DIR, anio=None):
    """Concatena los rankings semanales con columnas `semana` y `anio`."""
    registros = []
    for nombre in sorted(os.listdir(directorio)):
        match = PATRON_RANKING.match(nombre)
        if not match:
            continue
        year, week = int(match.group(1)), int(match.group(2))
        if anio is not None and year != anio:
            continue
        df = pd.read_csv(os.path.join(directorio, nombre), encoding='utf-8-sig')
        if df.empty:
            continue
        df['semana'] = f'{year}-W{week:02d}'
        df['anio'] = year
        registros.append(df)
    if not registros:
        return pd.DataFrame()
    return pd.concat(registros, ignore_index=True)


def _mejores_por_semana(df):
    """Una fila por jugador-semana: conserva la mejor posicion si hay duplicados."""
    return (df.sort_values('ranking')
              .drop_duplicates(subset=['player_id_fotmob', 'semana'], keep='first')
              .reset_index(drop=True))


def agregar_apariciones(df, top=5):
    """Consolida por jugador: apariciones en top N, tasa normalizada y score."""
    if df.empty:
        return pd.DataFrame()
    df = _mejores_por_semana(df)
    semanas_por_liga = df.groupby('liga')['semana'].nunique().to_dict()

    filas = []
    for pid, grupo in df.groupby('player_id_fotmob', sort=False):
        grupo = grupo.sort_values('ranking')
        liga_principal = grupo['liga'].value_counts().idxmax()
        semanas_liga = int(semanas_por_liga.get(liga_principal, grupo['semana'].nunique()))
        en_top = int((grupo['ranking'] <= top).sum())
        mejor = grupo.iloc[0]
        ultima = grupo.sort_values('semana').iloc[-1]
        apariciones_totw = None
        if 'apariciones_totw_semana' in grupo.columns:
            conteos_totw = pd.to_numeric(grupo['apariciones_totw_semana'], errors='coerce')
            if conteos_totw.notna().all():
                apariciones_totw = int(conteos_totw.sum())
        prob = (float(grupo['probabilidad_adn'].mean())
                if 'probabilidad_adn' in grupo.columns else float('nan'))
        filas.append({
            'player_id_fotmob': pid,
            'nombre': mejor['nombre'],
            'liga_principal': liga_principal,
            'clubes': ', '.join(sorted(grupo['club'].dropna().astype(str).unique())),
            'apariciones_top5': en_top,
            'apariciones_totw': apariciones_totw,
            'semanas_en_ranking': int(grupo['semana'].nunique()),
            'semanas_activas_liga': semanas_liga,
            'tasa_top5': round(en_top / semanas_liga, 4) if semanas_liga else 0.0,
            'mejor_posicion': int(mejor['ranking']),
            'score_max': round(float(grupo['score_adn_boca'].max()), 6),
            'score_medio': round(float(grupo['score_adn_boca'].mean()), 6),
            'probabilidad_adn_media': round(prob, 6) if prob == prob else float('nan'),
            'goles': int(ultima['goles']) if pd.notna(ultima['goles']) else None,
            'asistencias': int(ultima['asistencias']) if pd.notna(ultima['asistencias']) else None,
            'ultima_semana': ultima['semana'],
        })

    out = pd.DataFrame(filas).sort_values(
        ['apariciones_top5', 'tasa_top5', 'score_max'], ascending=False).reset_index(drop=True)
    out.insert(0, 'posicion_historica', range(1, len(out) + 1))
    return out


def resumen_por_liga(df, top=5):
    """Apariciones top N agregadas por liga para el analisis anual."""
    if df.empty:
        return pd.DataFrame()
    df = _mejores_por_semana(df)
    filas = []
    for liga, grupo in df.groupby('liga'):
        top_liga = grupo[grupo['ranking'] <= top]
        filas.append({
            'liga': liga,
            'semanas_activas': int(grupo['semana'].nunique()),
            'jugadores_distintos': int(grupo['player_id_fotmob'].nunique()),
            'apariciones_top5': int(len(top_liga)),
            'jugadores_top5_distintos': int(top_liga['player_id_fotmob'].nunique()),
        })
    return (pd.DataFrame(filas)
            .sort_values('apariciones_top5', ascending=False).reset_index(drop=True))


def main():
    df = cargar_rankings()
    if df.empty:
        print('No hay rankings semanales en data/.')
        return None
    acumulado = agregar_apariciones(df)
    ruta = os.path.join(DATA_DIR, 'ranking_historico_acumulado.csv')
    acumulado.to_csv(ruta, index=False, encoding='utf-8-sig')
    print(f'{ruta} ({len(acumulado)} jugadores, {df["semana"].nunique()} semanas)')
    cols = ['posicion_historica', 'nombre', 'liga_principal', 'apariciones_top5',
            'apariciones_totw', 'tasa_top5', 'score_max']
    print(acumulado.head(10)[cols].to_string(index=False))
    return acumulado


if __name__ == '__main__':
    main()
