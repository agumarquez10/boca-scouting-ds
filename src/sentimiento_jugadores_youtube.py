"""
Sentimiento comercial por jugador desde YouTube (comentarios de videos
relacionados al candidato + Boca).

Usa la API de YouTube Data v3. Clave: YOUTUBE_API_KEY en secrets/.env.
Escala de salida por jugador: -50 a +50 (promedio de comentarios).
"""

import json
import os
import sys
from datetime import datetime, timezone

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, SCRIPT_DIR)

from dotenv import load_dotenv

from nlp_engine import SentimientoEngine
from relevancia import filtrar_relevantes, suficientes
from rutas import dir_secrets

load_dotenv(os.path.join(dir_secrets(), '.env'))

YOUTUBE_API_KEY = os.getenv('YOUTUBE_API_KEY', '')
MAX_VIDEOS_POR_JUGADOR = 3
MAX_COMENTARIOS_POR_VIDEO = 20
MAX_COMENTARIOS_POR_JUGADOR = 40
CUOTA_BUSQUEDA = 100
CUOTA_COMENTARIOS = 1
_cuota = {'ruta': None, 'tope': None, 'agotada': False}


def configurar_cuota(directorio, tope):
    """Tope diario de unidades de YouTube. El consumo del dia queda en `directorio`/estado.

    `directorio=None, tope=None` desactiva el control (uso manual y tests).
    """
    hoy = datetime.now(timezone.utc).date().isoformat()
    ruta = os.path.join(directorio, 'estado', f'cuota_youtube_{hoy}.json') if directorio else None
    _cuota.update(ruta=ruta, tope=tope, agotada=False)


def cuota_usada():
    ruta = _cuota['ruta']
    if not ruta or not os.path.exists(ruta):
        return 0
    with open(ruta, encoding='utf-8') as f:
        return int(json.load(f).get('usado', 0))


def cuota_disponible(unidades):
    if _cuota['agotada']:
        return False
    tope = _cuota['tope']
    return tope is None or cuota_usada() + unidades <= tope


def _gastar(unidades):
    ruta = _cuota['ruta']
    if not ruta:
        return
    usado = cuota_usada() + unidades
    os.makedirs(os.path.dirname(ruta), exist_ok=True)
    with open(ruta, 'w', encoding='utf-8') as f:
        json.dump({'usado': usado}, f)


def _marcar_si_cuota(exc):
    """YouTube responde quotaExceeded: no tiene sentido seguir pidiendo en esta corrida."""
    if 'quota' in str(exc).lower():
        _cuota['agotada'] = True


def _cliente():
    from googleapiclient.discovery import build
    if not YOUTUBE_API_KEY:
        raise RuntimeError('Falta YOUTUBE_API_KEY en secrets/.env')
    return build('youtube', 'v3', developerKey=YOUTUBE_API_KEY)


def buscar_videos(youtube, nombre, club=''):
    """Busca videos del jugador. Devuelve [] si falla (cuota agotada o red)."""
    query = f'{nombre} Boca'
    if club:
        query = f'{nombre} {club} Boca'
    try:
        resultado = youtube.search().list(
            q=query, part='id,snippet', type='video',
            maxResults=MAX_VIDEOS_POR_JUGADOR, relevanceLanguage='es',
        ).execute()
    except Exception as exc:
        _marcar_si_cuota(exc)
        return []
    _gastar(CUOTA_BUSQUEDA)
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
    except Exception as exc:
        _marcar_si_cuota(exc)
        return []
    _gastar(CUOTA_COMENTARIOS)
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
        return {'ok': False, 'error': 'Sin API key', 'valor': 0.0, 'n_comentarios': 0,
                'textos': []}
    engine = engine or SentimientoEngine()
    if not cuota_disponible(CUOTA_BUSQUEDA):
        return {'ok': False, 'error': 'cuota_agotada', 'valor': 0.0, 'n_comentarios': 0,
                'textos': []}
    try:
        youtube = _cliente()
    except Exception as exc:
        return {'ok': False, 'error': f'cliente: {type(exc).__name__}',
                'valor': 0.0, 'n_comentarios': 0, 'textos': []}
    videos = buscar_videos(youtube, nombre, club)
    textos = []
    cortado = False
    for vid in videos:
        if not cuota_disponible(CUOTA_COMENTARIOS):
            cortado = True
            break
        textos.extend(filtrar_relevantes(comentarios_de_video(youtube, vid), nombre, club))
        if len(textos) >= MAX_COMENTARIOS_POR_JUGADOR:
            break
    textos = textos[:MAX_COMENTARIOS_POR_JUGADOR]
    if not suficientes(textos):
        return {'ok': False, 'error': 'cuota_agotada' if cortado else 'pocos comentarios relevantes',
                'valor': 0.0, 'n_comentarios': len(textos), 'textos': []}
    puntajes = engine.puntuar_lote(textos)
    return {
        'ok': True,
        'valor': round(sum(puntajes) / len(puntajes), 1),
        'n_comentarios': len(textos),
        'error': '',
        'textos': textos,
    }
