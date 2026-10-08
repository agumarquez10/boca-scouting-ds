"""Sentimiento por jugador del radar TOTW (hinchada + medios).

Combina YouTube (comentarios de la gente) y prensa deportiva multi-medio
(AR/PE/CL/PY + internacionales via Google News RSS) con prioridad a los medios.
Escala -50 a +50. Cachea por jugador en `data/sentimiento_radar_YYYY-Www.csv`
para no repetir consultas.

Los pesos 60/40 son una heuristica provisional, no validada con etiquetas de
sentimiento. Si solo hay una fuente disponible, se usa su valor completo.

La cobertura es despareja y los medios en portugues quedan fuera (el motor es
en espanol). Los jugadores sin ninguna fuente no entran al top (faltante != 0).
"""

import os
import sys

import pandas as pd

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, SCRIPT_DIR)

from rutas import dir_datos

DATA_DIR = dir_datos()
# Pesos heurísticos provisionales: todavía no se validaron con etiquetas.
PESO_MEDIOS = 0.6
PESO_GENTE = 0.4


def combinar_fuentes(yt, prensa):
    """Mezcla 60/40 cuando hay ambas fuentes; usa al 100% la única disponible."""
    aportes = []
    if prensa.get('ok'):
        aportes.append((prensa['valor'], PESO_MEDIOS, 'prensa'))
    if yt.get('ok'):
        aportes.append((yt['valor'], PESO_GENTE, 'youtube'))
    if not aportes:
        return None, []
    total = sum(peso for _, peso, _ in aportes)
    valor = sum(v * peso for v, peso, _ in aportes) / total
    return round(valor, 1), [fuente for _, _, fuente in aportes]


def sentimiento_jugador(nombre, club, engine=None):
    """Sentimiento ponderado de un jugador; `sentimiento` es None si no hay fuentes."""
    from nlp_engine import SentimientoEngine
    from sentimiento_jugadores_prensa import sentimiento_jugador_prensa
    from sentimiento_jugadores_youtube import sentimiento_jugador_youtube

    engine = engine or SentimientoEngine(usar_bert=False)
    yt = sentimiento_jugador_youtube(nombre, club, engine=engine)
    prensa = sentimiento_jugador_prensa(nombre, club, engine=engine)
    valor, fuentes = combinar_fuentes(yt, prensa)
    return {
        'nombre': nombre,
        'club': club,
        'sentimiento': valor,
        'n_fuentes': len(fuentes),
        'fuentes': ','.join(fuentes),
        'youtube_valor': yt.get('valor') if yt.get('ok') else None,
        'prensa_valor': prensa.get('valor') if prensa.get('ok') else None,
        'youtube_n_comentarios': yt.get('n_comentarios'),
        'prensa_n_textos': prensa.get('n_textos'),
    }


def _clave(nombre, club):
    return f'{nombre}|{club}'


def _guardar_cache(cache, cache_path):
    pd.DataFrame(list(cache.values())).to_csv(
        cache_path, index=False, encoding='utf-8-sig')


def calcular_sentimiento(jugadores, engine=None, cache_path=None, calcular=None):
    """Calcula sentimiento de [(nombre, club)] reutilizando la cache semanal.

    `calcular` permite inyectar el calculo (tests sin red). Cachea tambien los
    jugadores sin datos para no reintentar la cuota en la misma semana.

    La cache se escribe incrementalmente (un jugador por vez) para que una
    corrida interrumpida no pierda el trabajo hecho ni la cuota ya consumida.
    """
    calcular = calcular or sentimiento_jugador
    cache = {}
    if cache_path and os.path.exists(cache_path):
        previo = pd.read_csv(cache_path, encoding='utf-8-sig')
        cache = {_clave(f['nombre'], f['club']): f
                 for f in previo.to_dict('records')}

    registros = []
    for nombre, club in jugadores:
        clave = _clave(nombre, club)
        if clave in cache:
            registros.append(cache[clave])
            continue
        registro = calcular(nombre, club, engine=engine)
        cache[clave] = registro
        registros.append(registro)
        if cache_path:
            _guardar_cache(cache, cache_path)

    if cache_path and cache:
        _guardar_cache(cache, cache_path)
    return registros


def top_por_sentimiento(registros, n=3):
    """Top N por sentimiento; excluye jugadores sin datos."""
    if not registros:
        return []
    df = pd.DataFrame(registros)
    df = df[df['sentimiento'].notna()]
    if df.empty:
        return []
    return (df.sort_values('sentimiento', ascending=False)
              .head(n).to_dict('records'))
