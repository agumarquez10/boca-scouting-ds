"""
Sentimiento comercial por jugador desde YouTube (comentarios de videos
relacionados al candidato + Boca).

Usa la API de YouTube Data v3. Clave: YOUTUBE_API_KEY en secrets/.env.
Escala de salida por jugador: -50 a +50 (promedio de comentarios).
"""

import os
import sys

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, SCRIPT_DIR)

from dotenv import load_dotenv

from nlp_engine import SentimientoEngine
from rutas import dir_secrets

load_dotenv(os.path.join(dir_secrets(), '.env'))

YOUTUBE_API_KEY = os.getenv('YOUTUBE_API_KEY', '')
MAX_VIDEOS_POR_JUGADOR = 3
MAX_COMENTARIOS_POR_VIDEO = 20
MAX_COMENTARIOS_POR_JUGADOR = 40


def _cliente():
    from googleapiclient.discovery import build
    if not YOUTUBE_API_KEY:
        raise RuntimeError('Falta YOUTUBE_API_KEY en secrets/.env')
    return build('youtube', 'v3', developerKey=YOUTUBE_API_KEY)


def buscar_videos(youtube, nombre, club=''):
    query = f'{nombre} Boca'
    if club:
        query = f'{nombre} {club} Boca'
    resultado = youtube.search().list(
        q=query, part='id,snippet', type='video',
        maxResults=MAX_VIDEOS_POR_JUGADOR, relevanceLanguage='es',
    ).execute()
    return [item['id']['videoId'] for item in resultado.get('items', [])
            if item.get('id', {}).get('videoId')]


def comentarios_de_video(youtube, video_id, max_result=MAX_COMENTARIOS_POR_VIDEO):
    """Trae comentarios top de un video. Devuelve lista de textos."""
    try:
        respuesta = youtube.commentThreads().list(
            part='snippet', videoId=video_id,
            maxResults=max_result, order='relevance',
            textFormat='plainText',
        ).execute()
    except Exception:
        return []
    textos = []
    for item in respuesta.get('items', []):
        sn = item.get('snippet', {}).get('topLevelComment', {}).get('snippet', {})
        texto = sn.get('textDisplay', '')
        if texto:
            textos.append(texto)
    return textos


def sentimiento_jugador_youtube(nombre, club='', engine=None):
    """Calcula el sentimiento promedio de los comentarios de YouTube de un jugador."""
    if not YOUTUBE_API_KEY:
        return {'ok': False, 'error': 'Sin API key', 'valor': 0.0, 'n_comentarios': 0}
    engine = engine or SentimientoEngine()
    youtube = _cliente()
    videos = buscar_videos(youtube, nombre, club)
    textos = []
    for vid in videos:
        textos.extend(comentarios_de_video(youtube, vid))
        if len(textos) >= MAX_COMENTARIOS_POR_JUGADOR:
            break
    textos = textos[:MAX_COMENTARIOS_POR_JUGADOR]
    if not textos:
        return {'ok': False, 'error': 'sin comentarios', 'valor': 0.0, 'n_comentarios': 0}
    puntajes = engine.puntuar_lote(textos)
    return {
        'ok': True,
        'valor': round(sum(puntajes) / len(puntajes), 1),
        'n_comentarios': len(textos),
        'error': '',
    }
