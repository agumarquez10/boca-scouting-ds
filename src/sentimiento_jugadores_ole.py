"""
Sentimiento comercial por jugador desde notas de prensa (Olé como fuente).

Usa Google News RSS filtrado por sitio (site:ole.com.ar) para capturar como
habla la prensa deportiva del candidato como posible fichaje. Google News
indexa las notas de Olé de forma estable (a diferencia del buscador interno
de ole.com.ar, que es JS-only y no se puede scrapear de forma confiable).

Escala de salida por jugador: -50 a +50.
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
MAX_TITULARES = 12


def _filtro_ole(texto):
    """Quita el sufijo ' - Fuente' que agrega Google News al titulo."""
    return re.sub(r'\s+-\s+[^-]{1,40}$', '', texto).strip()


def _sin_tildes(texto):
    texto = unicodedata.normalize('NFKD', texto)
    return ''.join(c for c in texto if not unicodedata.combining(c)).lower()


def _es_basura(titulo):
    bajo = _sin_tildes(titulo)
    return (
        'google noticias' in bajo
        or 'site:ole.com.ar' in bajo
        or 'google news' in bajo
    )


def _items_rss(url):
    try:
        r = requests.get(url, timeout=25, headers=UA)
        r.raise_for_status()
    except requests.RequestException:
        return []
    titulos = re.findall(r'<title>(.*?)</title>', r.text, re.S)
    descs = re.findall(r'<description>(.*?)</description>', r.text, re.S)
    textos = []
    for t in titulos:
        t = _filtro_ole(t)
        if t and not _es_basura(t):
            textos.append(t)
    # descripciones (a veces vacias o html-encoded); tomamos texto plano
    for d in descs:
        d = re.sub(r'<[^>]+>', '', d)
        d = _filtro_ole(d)
        if d and d not in textos and not _es_basura(d):
            textos.append(d)
    return textos[:MAX_TITULARES]


def notas_ole(nombre, club=''):
    base = nombre
    if club:
        base = f'{nombre} {club}'
    consulta = f'{base} Boca site:ole.com.ar'
    url = ('https://news.google.com/rss/search?q='
           + urllib.parse.quote(consulta)
           + '&hl=es-419&gl=AR&ceid=AR:es-419')
    return _items_rss(url)


def sentimiento_jugador_ole(nombre, club='', engine=None):
    engine = engine or SentimientoEngine()
    textos = notas_ole(nombre, club)
    if not textos:
        return {'ok': False, 'error': 'sin notas Ole', 'valor': 0.0, 'n_notas': 0}
    puntajes = engine.puntuar_lote(textos)
    return {
        'ok': True,
        'valor': round(sum(puntajes) / len(puntajes), 1),
        'n_notas': len(textos),
        'error': '',
    }
