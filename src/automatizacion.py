"""Automatizacion semanal: radar TOTW -> top 3 por puesto -> borrador de tweet.

Corre el pipeline semanal (FotMob TOTW -> L1 calibrada), arma un top 3 de
delanteros, mediocampistas y defensores (para dar variedad de puestos) y guarda
el borrador en `data/tweet_top5.txt`. NO publica: el envio real a Twitter queda
para cuando esten las credenciales y `requests-oauthlib` (fuera del alcance).

El sentimiento (hoy global, no por jugador) esta desacoplado del tweet:
`hype_actual`/`clasificar_hype`/`cargar_hype` quedan disponibles para reactivar
la linea de hype cuando exista sentimiento real por jugador.
"""

import os
import sys

import numpy as np
import pandas as pd

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, SCRIPT_DIR)

from posiciones import agrupar_posicion

DATA_DIR = os.path.join(SCRIPT_DIR, '..', 'data')
SENTIMIENTO_CSV = os.path.join(DATA_DIR, 'sentimiento_hinchada.csv')
TWEET_TXT = os.path.join(DATA_DIR, 'tweet_top5.txt')
TOP_POR_PUESTO = 3

MACRO_POSICION = {
    'Delantero': 'DEL',
    'Extremo': 'DEL',
    'Mediocampista_ofensivo': 'MED',
    'Mediocampista_central': 'MED',
    'Lateral': 'DEF',
    'Defensor_central': 'DEF',
}
ORDEN_PUESTOS = ['DEL', 'MED', 'DEF']


def correr_scouting():
    from scouting_pipeline import main as scouting_main
    return scouting_main()


def hype_actual(sent):
    """Hype global: neto + positividad de la ultima semana con datos."""
    sent = sent.copy()
    sent['fecha'] = pd.to_datetime(sent['fecha'])
    ultima = sent['fecha'].max()
    semana = sent[sent['fecha'] >= ultima - pd.Timedelta(days=7)]
    if semana.empty:
        return None
    neto = semana['compound'].mean()
    positividad = (semana['clasificacion'] == 'positivo').mean()
    atenuacion = min(1.0, np.log1p(len(semana)) / 3.0)
    return float((0.6 * neto + 0.4 * positividad) * atenuacion)


def clasificar_hype(valor):
    if valor is None:
        return 'sin datos'
    if valor > 0.15:
        return 'hinchada eufórica'
    if valor > 0.05:
        return 'clima positivo'
    if valor < -0.05:
        return 'clima negativo'
    return 'clima neutral'


def cargar_hype(ruta=SENTIMIENTO_CSV):
    if not os.path.exists(ruta):
        return None
    return hype_actual(pd.read_csv(ruta, encoding='utf-8-sig'))


def _macro_posicion(posicion):
    return MACRO_POSICION.get(agrupar_posicion(posicion))


def seleccionar_por_puesto(ranking, n=TOP_POR_PUESTO):
    """Top N por puesto (DEL/MED/DEF) ordenado por score ADN."""
    if ranking is None or ranking.empty:
        return {}
    col = 'score_adn_boca' if 'score_adn_boca' in ranking.columns else 'probabilidad'
    df = ranking.copy()
    df['_macro'] = df['posicion'].map(_macro_posicion)
    seleccion = {}
    for macro in ORDEN_PUESTOS:
        grupo = df[df['_macro'] == macro].sort_values(col, ascending=False).head(n)
        if not grupo.empty:
            seleccion[macro] = grupo.reset_index(drop=True)
    return seleccion


def _goles_asistencias(fila):
    goles = getattr(fila, 'goles', None)
    asistencias = getattr(fila, 'asistencias', None)
    faltante = lambda v: v is None or (isinstance(v, float) and np.isnan(v))
    if faltante(goles) or faltante(asistencias):
        return 's/d'
    return f'{int(goles)}+{int(asistencias)}'


def _linea_puesto(macro, grupo):
    partes = []
    for fila in grupo.itertuples():
        club = getattr(fila, 'club', '')
        contexto = f' ({club})' if club else ''
        partes.append(f'{getattr(fila, "nombre")}{contexto} {_goles_asistencias(fila)}')
    return f'{macro}: ' + ' | '.join(partes)


def componer_tweet(seleccion, hype=None):
    """Arma el borrador: top por puesto con club y goles+asistencias.

    `hype` queda opcional para reactivar la linea de sentimiento cuando exista
    una metrica real por jugador; por defecto no se incluye.
    """
    encabezado = 'ADN Boca - Top por puesto (G+A)'
    lineas = [_linea_puesto(m, g) for m, g in seleccion.items()]
    cola = []
    if hype is not None:
        cola.append(f'Hype: {hype:+.2f} ({clasificar_hype(hype)})')
    cola.append('#Boca #MercadoDePases #Fichajes')
    return '\n'.join([encabezado, *lineas, *cola])


def main():
    print('== Paso 1: radar semanal TOTW ==')
    ranking = correr_scouting()
    if ranking is None or ranking.empty:
        print('[aviso] Sin jugadores puntuables: no se genera borrador de tweet.')
        return None

    print('\n== Paso 2: borrador de tweet ==')
    seleccion = seleccionar_por_puesto(ranking)
    texto = componer_tweet(seleccion)
    with open(TWEET_TXT, 'w', encoding='utf-8') as f:
        f.write(texto + '\n')
    print(texto)
    print(f'\n({len(texto)} caracteres) guardado en {TWEET_TXT}')
    return texto


if __name__ == '__main__':
    main()
