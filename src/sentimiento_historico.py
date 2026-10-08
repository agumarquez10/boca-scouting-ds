"""Sentimiento por jugador en todas las semanas registradas (top 3 por puesto).

Barre los `data/ranking_jugadores_fecha_YYYY-Www.csv`, aplica el mismo corte que
va al tweet (top 3 de delanteros, mediocampistas y defensores por score ADN) y
calcula el sentimiento de la hinchada con la cache semanal de `sentimiento_radar`.
Es idempotente: la cache evita repetir consultas y la cuota de YouTube.

Limite metodologico: el sentimiento se consulta en el momento de correr el script,
no se guardó en la fecha de cada semana. El ranking mide como se menciona hoy a los
jugadores de esos TOTW, no el clima de hincharia de aquella fecha.
"""

import os
import re

import pandas as pd

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(os.path.dirname(SCRIPT_DIR), 'data')

PATRON_RANKING = re.compile(r'ranking_jugadores_fecha_(\d{4})-W(\d{2})\.csv$')
TOP_POR_PUESTO = 3
CSV_SALIDA = 'sentimiento_historico.csv'


def semanas_registradas(directorio=DATA_DIR):
    """Semanas con ranking guardado, en orden cronologico."""
    found = []
    for nombre in os.listdir(directorio):
        match = PATRON_RANKING.match(nombre)
        if not match:
            continue
        anio, semana = int(match.group(1)), int(match.group(2))
        ruta = os.path.join(directorio, nombre)
        if pd.read_csv(ruta, encoding='utf-8-sig', usecols=['ranking']).empty:
            continue
        found.append((f'{anio}-W{semana:02d}', ruta))
    return sorted(found)


def jugadores_de_semana(ranking, n=TOP_POR_PUESTO):
    """Los (nombre, club, puesto) del corte por puesto, en el orden del tweet."""
    from automatizacion import seleccionar_por_puesto
    filas = []
    for macro, grupo in seleccionar_por_puesto(ranking, n=n).items():
        for fila in grupo.itertuples():
            filas.append((getattr(fila, 'nombre'), getattr(fila, 'club', ''), macro))
    return filas


def _registro_de_sentimiento(semana, nombre, club, registro, puesto):
    return {
        'semana': semana,
        'puesto': puesto,
        'nombre': nombre,
        'club': club,
        'sentimiento': registro.get('sentimiento'),
        'n_fuentes': registro.get('n_fuentes', 0),
        'fuentes': registro.get('fuentes', ''),
        'youtube_valor': registro.get('youtube_valor'),
        'prensa_valor': registro.get('prensa_valor'),
        'youtube_n_comentarios': registro.get('youtube_n_comentarios'),
        'prensa_n_textos': registro.get('prensa_n_textos'),
    }


def barrer_semanas(directorio=DATA_DIR, calcular=None, verbose=True):
    """Calcula el sentimiento del top por puesto de cada semana registrada."""
    from sentimiento_radar import calcular_sentimiento

    filas = []
    for semana, ruta in semanas_registradas(directorio):
        ranking = pd.read_csv(ruta, encoding='utf-8-sig')
        jugadores = jugadores_de_semana(ranking)
        if not jugadores:
            if verbose:
                print(f'{semana}: sin corte por puesto, se omite')
            continue
        cache_path = os.path.join(directorio, f'sentimiento_radar_{semana}.csv')
        registros = calcular_sentimiento(
            [(nombre, club) for nombre, club, _ in jugadores],
            cache_path=cache_path, calcular=calcular)
        puestos = {(nombre, club): macro for nombre, club, macro in jugadores}
        con_datos = sum(1 for r in registros if r.get('sentimiento') is not None)
        if verbose:
            print(f'{semana}: {len(registros)} jugadores, {con_datos} con datos')
        for registro in registros:
            nombre = registro['nombre']
            club = registro.get('club', '')
            filas.append(_registro_de_sentimiento(
                semana, nombre, club, registro, puestos.get((nombre, club), '')))
    return pd.DataFrame(filas)


COLUMNAS_ACUMULADO = ['nombre', 'club', 'semanas_medidas', 'sentimiento_medio',
                      'sentimiento_max', 'sentimiento_min', 'primera_semana',
                      'ultima_semana']


def consolidar(df):
    """Ranking global: promedio, maximo y cobertura de cada jugador."""
    if df.empty:
        return pd.DataFrame(columns=COLUMNAS_ACUMULADO)
    con_datos = df[df['sentimiento'].notna()]
    if con_datos.empty:
        return pd.DataFrame(columns=COLUMNAS_ACUMULADO)
    filas = []
    for nombre, grupo in con_datos.groupby('nombre', sort=False):
        mejor = grupo.sort_values('semana').iloc[-1]
        filas.append({
            'nombre': nombre,
            'club': mejor['club'],
            'semanas_medidas': int(grupo['semana'].nunique()),
            'sentimiento_medio': round(float(grupo['sentimiento'].mean()), 2),
            'sentimiento_max': round(float(grupo['sentimiento'].max()), 2),
            'sentimiento_min': round(float(grupo['sentimiento'].min()), 2),
            'primera_semana': grupo.sort_values('semana')['semana'].iloc[0],
            'ultima_semana': mejor['semana'],
        })
    return (pd.DataFrame(filas, columns=COLUMNAS_ACUMULADO)
            .sort_values(['sentimiento_max', 'sentimiento_medio'], ascending=False)
            .reset_index(drop=True))


def top_por_semana(df, n=3):
    """Top N de sentimiento dentro de cada semana."""
    if df.empty:
        return {}
    out = {}
    for semana, grupo in df.groupby('semana'):
        con_datos = grupo[grupo['sentimiento'].notna()]
        out[semana] = con_datos.sort_values(
            'sentimiento', ascending=False).head(n).to_dict('records')
    return out


def main():
    df = barrer_semanas()
    if df.empty:
        print('No hay semanas con ranking en data/.')
        return None
    ruta = os.path.join(DATA_DIR, CSV_SALIDA)
    df.to_csv(ruta, index=False, encoding='utf-8-sig')
    print(f'\n{ruta} ({len(df)} filas jugador-semana)')

    print('\n== Top 3 por sentimiento de cada semana ==')
    for semana, filas in sorted(top_por_semana(df).items()):
        if not filas:
            print(f'{semana}: sin datos')
            continue
        texto = ' | '.join(f"{f['nombre']} ({f['club']}) {f['sentimiento']:+.1f}"
                           for f in filas)
        print(f'{semana}: {texto}')

    acumulado = consolidar(df)
    ruta_acum = os.path.join(DATA_DIR, 'sentimiento_historico_acumulado.csv')
    acumulado.to_csv(ruta_acum, index=False, encoding='utf-8-sig')
    print(f'\n{ruta_acum}')
    print(acumulado.head(15).to_string(index=False))
    return acumulado


if __name__ == '__main__':
    main()
