"""
Motor de sentimiento en espanol para la hinchada.

Escala de salida: -50 (muy negativo) a +50 (muy positivo), 0 neutral.

Dos componentes:
  1. VADER (lexico, rapido) + lexico espanol propio del proyecto.
  2. BERT espanol (pysentimiento/robertuito-sentiment-analysis) para jerga
     de redes/hinchada que el lexico no capta.

El resultado final es un promedio ponderado de ambas secciones normalizado a
[-50, +50]. La carga del BERT es perezosa (solo cuando se pide) para no frenar
pipelines que solo usan VADER.
"""

import os
import unicodedata

# --- Lexico espanol propio (terminos de hincha de futbol) ---
LEXICO_HINCHADA = {
    # positivos
    'crack': 3.5, 'figura': 2.5, 'goleador': 2.5, 'ídolo': 3.0, 'idolo': 3.0,
    'fenomeno': 2.5, 'talento': 1.5, 'joya': 2.5, 'promesa': 1.5, 'maquina': 2.5,
    'genio': 3.0, 'monstruo': 2.8, 'bestia': 1.5, 'animal': 1.2, 'caño': 2.5,
    'gambeta': 1.8, 'gladiador': 2.5, 'león': 1.5, 'leon': 1.5, 'torero': 2.0,
    'rompe': 2.0, 'destroza': 2.2, 'garra': 2.0, 'huevos': 2.0, 'corazón': 1.8,
    'corazon': 1.8, 'clase': 1.5, 'jerarquía': 1.5, 'jerarquia': 1.5,
    'brutal': 2.0, 'tremendo': 1.8, 'bárbaro': 1.8, 'barbaro': 1.8,
    'espectacular': 2.5, 'sensacional': 2.5, 'imparable': 2.8, 'letal': 2.2,
    'piolín': 1.5, 'piolin': 1.5, 'zaffaroni': 1.5, 'riquelme': 2.5,
    # negativos
    'burro': -2.5, 'muerto': -2.2, 'negreado': -2.5, 'negreado': -2.5,
    'pecho frío': -3.0, 'pecho frio': -3.0, 'frío': -1.8, 'frio': -1.8,
    'mufa': -2.0, 'mufado': -1.5, 'tímido': -1.5, 'timido': -1.5,
    'flojo': -1.8, 'blandito': -2.0, 'tortuga': -1.8, 'lento': -1.8,
    'horrible': -2.5, 'desastre': -2.8, 'pésimo': -2.5, 'pesimo': -2.5,
    'fracaso': -2.8, 'chantaje': -1.8, 'berretín': -2.2, 'berretin': -2.2,
    'muertas': -2.0, 'acarrea': -1.5, 'elefante': -1.8, 'chambón': -2.2,
    'chambon': -2.2, 'blanco': -1.5, 'débil': -1.8, 'debil': -1.8,
    'vende humo': -2.5, 'vendehumo': -2.5, 'humo': -1.5, 'chanta': -2.0,
    'mentiroso': -2.0,
}


def _normalizar(texto):
    texto = unicodedata.normalize('NFKD', texto)
    texto = ''.join(c for c in texto if not unicodedata.combining(c))
    return texto.lower()


def clasificar_vader(texto):
    from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer
    analyzer = SentimentIntensityAnalyzer()
    comp = analyzer.polarity_scores(texto)['compound']
    return comp


def ajustar_lexico_hinchada(texto, comp):
    """Corrige el compound segun terminos propios del lexico de hinchada."""
    norm = _normalizar(texto)
    delta = 0.0
    for termino, peso in LEXICO_HINCHADA.items():
        if termino in norm:
            delta += peso * 0.08
    comp = max(-1.0, min(1.0, comp + delta * 0.3))
    return comp


class SentimientoEngine:
    """Motor combinado VADER + BERT espanol -> -50 a +50."""

    def __init__(self, usar_bert=True, bert_model='pysentimiento/robertuito-sentiment-analysis'):
        self.usar_bert = usar_bert
        self.bert_model = bert_model
        self._pipe = None

    def _cargar_bert(self):
        if self._pipe is None:
            from transformers import pipeline
            self._pipe = pipeline(
                'sentiment-analysis',
                model=self.bert_model,
                truncation=True,
                max_length=128,
            )
        return self._pipe

    def bert_score(self, texto):
        if not self.usar_bert:
            return 0.0
        try:
            pipe = self._cargar_bert()
            out = pipe(texto)[0]
            label = out['label'].upper()
            score = float(out['score'])
            if 'NEG' in label:
                return -score
            if 'POS' in label:
                return score
            return 0.0
        except Exception:
            return 0.0

    def puntuar(self, texto):
        """Devuelve valor en [-50, +50]."""
        if not texto:
            return 0.0
        comp = clasificar_vader(texto)
        comp = ajustar_lexico_hinchada(texto, comp)
        vader_norm = comp

        bert_norm = self.bert_score(texto)

        mezcla = 0.55 * vader_norm + 0.45 * bert_norm
        return mezcla * 50.0

    def puntuar_lote(self, textos):
        return [self.puntuar(t) for t in textos]
