"""Sentimiento por jugador desde prensa deportiva multi-medio (Google News RSS).

Generaliza el enfoque de Olé: consulta en una sola query `site:` una lista de
medios deportivos (Argentina, Peru, Chile, Paraguay + internacionales) y
promedia el sentimiento de títulos y descripciones del RSS. Escala -50 a +50.

Gratis y sin API key. Limitacion: el motor de sentimiento es en espanol, por eso
no se incluyen medios en portugues (Brasil) para no meter ruido.
"""

import os
import re
import sys
import unicodedata
import urllib.parse

import requests

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, SCRIPT_DIR)

from nlp_engine import SentimientoEngine

UA = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}
MAX_TITULARES = 25

MEDIOS_PRENSA = [
    {'dominio': 'ole.com.ar', 'pais': 'AR'},
    {'dominio': 'tycsports.com', 'pais': 'AR'},
    {'dominio': 'bolavip.com', 'pais': 'AR'},
    {'dominio': 'dobleamarilla.com.ar', 'pais': 'AR'},
    {'dominio': 'depor.com', 'pais': 'PE'},
    {'dominio': 'libero.pe', 'pais': 'PE'},
    {'dominio': 'elcomercio.pe', 'pais': 'PE'},
    {'dominio': 'redgol.cl', 'pais': 'CL'},
    {'dominio': 'encancha.cl', 'pais': 'CL'},
    {'dominio': 'abc.com.py', 'pais': 'PY'},
    {'dominio': 'd10.paraguay.com', 'pais': 'PY'},
    {'dominio': 'espn.com.ar', 'pais': 'INT'},
    {'dominio': 'marca.com', 'pais': 'INT'},
    {'dominio': 'as.com', 'pais': 'INT'},
]


def _dominios(medios):
    return [m['dominio'] if isinstance(m, dict) else m for m in medios]


def _filtro_fuente(texto):
    """Quita el sufijo ' - Fuente' que agrega Google News al titulo."""
    return re.sub(r'\s+-\s+[^-]{1,60}$', '', texto).strip()


def _sin_tildes(texto):
    texto = unicodedata.normalize('NFKD', texto)
    return ''.join(c for c in texto if not unicodedata.combining(c)).lower()


def _es_basura(titulo):
    bajo = _sin_tildes(titulo)
    return (
        'google noticias' in bajo
        or 'google news' in bajo
        or 'site:' in bajo
    )


def _parsear_rss(html, max_titulares=MAX_TITULARES):
    titulos = re.findall(r'<title>(.*?)</title>', html, re.S)
    descs = re.findall(r'<description>(.*?)</description>', html, re.S)
    textos = []
    for t in titulos:
        t = _filtro_fuente(t)
        if t and not _es_basura(t):
            textos.append(t)
    for d in descs:
        d = re.sub(r'<[^>]+>', '', d)
        d = _filtro_fuente(d)
        if d and d not in textos and not _es_basura(d):
            textos.append(d)
    return textos[:max_titulares]


def _items_rss(url, max_titulares=MAX_TITULARES):
    try:
        r = requests.get(url, timeout=25, headers=UA)
        r.raise_for_status()
    except requests.RequestException:
        return []
    return _parsear_rss(r.text, max_titulares)


def _url_prensa(nombre, club, dominios):
    base = f'{nombre} {club}'.strip()
    sites = ' OR '.join(f'site:{d}' for d in dominios)
    consulta = f'{base} Boca ({sites})'
    return ('https://news.google.com/rss/search?q='
            + urllib.parse.quote(consulta)
            + '&hl=es-419&gl=AR&ceid=AR:es-419')


def notas_prensa(nombre, club='', medios=None):
    """Titulares de los medios configurados para el jugador."""
    dominios = _dominios(medios if medios is not None else MEDIOS_PRENSA)
    return _items_rss(_url_prensa(nombre, club, dominios))


def sentimiento_jugador_prensa(nombre, club='', engine=None, medios=None):
    engine = engine or SentimientoEngine(usar_bert=False)
    textos = notas_prensa(nombre, club, medios)
    if not textos:
        return {'ok': False, 'error': 'sin textos', 'valor': 0.0, 'n_textos': 0}
    puntajes = engine.puntuar_lote(textos)
    return {
        'ok': True,
        'valor': round(sum(puntajes) / len(puntajes), 1),
        'n_textos': len(textos),
        'error': '',
    }
