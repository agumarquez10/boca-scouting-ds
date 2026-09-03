"""
Pipeline de sentimiento comercial por jugador.

Calcula el sentimiento de la hinchada hacia los principales candidatos ADN
(por defecto el top 20) sumando dos fuentes:
  - YouTube (comentarios de videos relacionados al jugador + Boca)
  - Olé / prensa (titulares de notas via Google News site:ole.com.ar)

Combina ambas en un unico valor por jugador en escala -50 a +50 y guarda
data/sentimiento_jugadores.csv
"""

import os
import sys

import pandas as pd

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, SCRIPT_DIR)

from nlp_engine import SentimientoEngine
from sentimiento_jugadores_youtube import sentimiento_jugador_youtube
from sentimiento_jugadores_ole import sentimiento_jugador_ole
from rutas import dir_datos

DATA_DIR = dir_datos()

TOP_CANDIDATOS = 20


def sentimiento_jugador(nombre, club, engine):
    yt = sentimiento_jugador_youtube(nombre, club, engine=engine)
    ole_ = sentimiento_jugador_ole(nombre, club, engine=engine)

    # Combinar: promedio de fuentes disponibles. Si solo hay una, esa pesa.
    valores = []
    fuentes = []
    if yt.get('ok'):
        valores.append(yt['valor'])
        fuentes.append('youtube')
    if ole_.get('ok'):
        valores.append(ole_['valor'])
        fuentes.append('ole')

    if not valores:
        return {
            'ok': False, 'valor': 0.0, 'n_fuentes': 0,
            'yt': yt, 'ole': ole_, 'fuentes': [],
        }
    return {
        'ok': True,
        'valor': round(sum(valores) / len(valores), 1),
        'n_fuentes': len(valores),
        'fuentes': fuentes,
        'yt': yt, 'ole': ole_,
    }


def main(top_n=TOP_CANDIDATOS):
    ruta_candidatos = os.path.join(DATA_DIR, 'candidatos_adn.csv')
    if not os.path.exists(ruta_candidatos):
        raise FileNotFoundError('Corré primero scouting_mercado.py (falta candidatos_adn.csv)')

    df = pd.read_csv(ruta_candidatos, encoding='utf-8-sig')
    df = df.sort_values('probabilidad', ascending=False).head(top_n).copy()
    print(f'=== Sentimiento por jugador (top {top_n} ADN) ===')

    engine = SentimientoEngine()
    registros = []
    for _, fila in df.iterrows():
        nombre = fila['nombre']
        club = fila['club'] if not pd.isna(fila['club']) else ''
        print(f'  {nombre} ({club})...', end=' ', flush=True)
        r = sentimiento_jugador(nombre, club, engine)
        registros.append({
            'nombre': nombre,
            'club': club,
            'adn': round(float(fila['probabilidad']), 4),
            'sentimiento': r['valor'],
            'n_fuentes': r['n_fuentes'],
            'fuentes': ','.join(r['fuentes']),
            'youtube_valor': r['yt'].get('valor') if r['yt'].get('ok') else None,
            'youtube_n': r['yt'].get('n_comentarios') if r['yt'].get('ok') else 0,
            'ole_valor': r['ole'].get('valor') if r['ole'].get('ok') else None,
            'ole_n': r['ole'].get('n_notas') if r['ole'].get('ok') else 0,
        })
        print(r['valor'])

    salida = pd.DataFrame(registros).sort_values('adn', ascending=False).reset_index(drop=True)
    out_path = os.path.join(DATA_DIR, 'sentimiento_jugadores.csv')
    salida.to_csv(out_path, index=False, encoding='utf-8-sig')
    print(f'\nGuardado: {out_path} ({len(salida)} jugadores)')
    return salida


if __name__ == '__main__':
    main()
