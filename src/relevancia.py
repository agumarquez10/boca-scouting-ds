"""Filtro de relevancia para los textos de sentimiento por jugador.

Antes de puntuar, un texto tiene que mencionar al jugador y estar en espanol.
Un nombre unico (p. ej. 'Mauricio') solo cuenta si el texto tambien menciona
el club, porque el nombre solo trae notas de otros jugadores. Una fuente con
menos de MIN_TEXTOS textos relevantes no se puntua (faltante != 0).
"""

import os
import sys

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, SCRIPT_DIR)

from nlp_engine import _tokens

MIN_TEXTOS = 3

_CLUB_GENERICO = {
    'club', 'fc', 'deportivo', 'deportiva', 'atletico', 'sporting', 'sport',
    'futbol', 'real', 'social', 'asociacion', 'union',
}
_ES = {'el', 'la', 'los', 'las', 'del', 'muy', 'pero', 'con', 'una', 'es',
       'son', 'hay', 'bien', 'ya', 'su', 'sus'}
_PT = {'nao', 'muito', 'ele', 'ela', 'eu', 'um', 'obrigado', 'jogo', 'tambem',
       'isso', 'meu', 'minha', 'voce', 'com', 'em'}


def _club_tokens(club):
    return [t for t in _tokens(club) if len(t) >= 4 and t not in _CLUB_GENERICO]


def es_espanol(texto):
    """Heuristica: descarta si hay mas marcadores de portugues que de espanol."""
    toks = _tokens(texto)
    es = sum(1 for t in toks if t in _ES)
    pt = sum(1 for t in toks if t in _PT)
    return pt <= es


def menciona(texto, nombre, club=''):
    partes = _tokens(nombre)
    if not partes:
        return False
    cuerpo = ' ' + ' '.join(_tokens(texto)) + ' '
    if len(partes) == 1:
        if f' {partes[0]} ' not in cuerpo:
            return False
        return any(f' {t} ' in cuerpo for t in _club_tokens(club))
    club_t = set(_club_tokens(club))
    if f' {" ".join(partes[-2:])} ' in cuerpo:
        return True
    apellido = partes[-1]
    if len(apellido) >= 4 and apellido not in club_t and f' {apellido} ' in cuerpo:
        return True
    return False


def filtrar_relevantes(textos, nombre, club=''):
    return [t for t in textos if menciona(t, nombre, club) and es_espanol(t)]


def suficientes(textos):
    return len(textos) >= MIN_TEXTOS
