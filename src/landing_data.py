"""Construye `web/data.js` para la landing del radar: una lectura, sin recalcular.

Toma los rankings semanales, el sentimiento ya cacheado y el ranking historico
acumulado y los vuelca como un objeto global (`window.RADAR_DATA`) para que la
pagina se abra con doble click en `file://` sin servidor.

Offline por diseno: no consulta la API ni toca el modelo. Los borradores de
tweet se recomponen con `automatizacion.componer_tweet` sobre los CSV ya
guardados, usando solo el sentimiento cacheado de esa semana (faltante queda
como "sin datos", nunca 0).

    python src/landing_data.py
"""

import json
import os
import sys
from datetime import date

import joblib
import pandas as pd

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, SCRIPT_DIR)

from automatizacion import _macro_posicion, componer_tweet, seleccionar_por_puesto
from posiciones import agrupar_posicion
from ranking_historico import (PATRON_RANKING, agregar_apariciones, cargar_rankings,
                               resumen_por_liga)
from rutas import dir_datos, dir_models, dir_raiz
from sentimiento_radar import top_por_sentimiento

WEB_DIR = os.path.join(dir_raiz(), 'web')
DATA_JS = os.path.join(WEB_DIR, 'data.js')
TOP_PLANILLA = 5


def _num(valor, decimales=4):
    """float limpio para JSON: NaN -> None."""
    try:
        n = float(valor)
    except (TypeError, ValueError):
        return None
    if pd.isna(n):
        return None
    return round(n, decimales)


def _int(valor):
    try:
        n = int(valor)
    except (TypeError, ValueError):
        return None
    return n if pd.notna(valor) else None


def _rango_semana(clave):
    """'2026-W39' -> (inicio, fin) en ISO; el formato lo resuelve la pagina."""
    anio, semana = int(clave[:4]), int(clave[6:])
    return (date.fromisocalendar(anio, semana, 1).isoformat(),
            date.fromisocalendar(anio, semana, 7).isoformat())


def _sentimiento_semana(semana, directorio):
    """Registros cacheados de la semana; lista vacia si no se midio esa semana."""
    ruta = os.path.join(directorio, f'sentimiento_radar_{semana}.csv')
    if not os.path.exists(ruta):
        return []
    df = pd.read_csv(ruta, encoding='utf-8-sig')
    registros = []
    for f in df.to_dict('records'):
        valor = f.get('sentimiento')
        registros.append({
            'nombre': f['nombre'],
            'club': f.get('club'),
            'sentimiento': _num(valor, 1),
            'n_fuentes': _int(f.get('n_fuentes')) or 0,
            'fuentes': f.get('fuentes') if isinstance(f.get('fuentes'), str) else '',
            'youtube_valor': _num(f.get('youtube_valor'), 1),
            'prensa_valor': _num(f.get('prensa_valor'), 1),
        })
    return registros


def _jugador(fila, lugar=None):
    return {
        'lugar': lugar,
        'nombre': fila['nombre'],
        'club': fila['club'],
        'liga': fila['liga'],
        'posicion': fila['posicion'],
        'puesto': _macro_posicion(fila['posicion']) or agrupar_posicion(fila['posicion']),
        'edad': _int(fila.get('edad')),
        'goles': _int(fila.get('goles')),
        'asistencias': _int(fila.get('asistencias')),
        'partidos_temporada': _int(fila.get('partidos_temporada')),
        'torneos': fila.get('torneos_stats') if isinstance(fila.get('torneos_stats'), str) else '',
    }


def construir_semanas(directorio):
    """Una entrada por semana ISO con la planilla del top 5 y su borrador de tweet."""
    archivos = sorted(n for n in os.listdir(directorio) if PATRON_RANKING.match(n))
    semanas = []
    for nombre in archivos:
        anio, iso = (int(g) for g in PATRON_RANKING.match(nombre).groups())
        clave = f'{anio}-W{iso:02d}'
        df = pd.read_csv(os.path.join(directorio, nombre), encoding='utf-8-sig')
        if df.empty:
            continue
        df = df.sort_values('score_adn_boca', ascending=False)
        df = df.drop_duplicates(subset=['player_id_fotmob'], keep='first')

        seleccionados = seleccionar_por_puesto(df)
        del_tweet = [f for grupo in seleccionados.values()
                     for f in grupo.to_dict('records')]
        registros = _sentimiento_semana(clave, directorio)
        indice_sent = {(r['nombre'], r['club']): r for r in registros}
        sentiment_tweet = []
        for f in del_tweet:
            found = indice_sent.get((f['nombre'], f['club']))
            if found:
                sentiment_tweet.append(found)

        inicio, fin = _rango_semana(clave)
        semanas.append({
            'clave': clave,
            'inicio': inicio,
            'fin': fin,
            'jugadores': len(df),
            'ligas': sorted(df['liga'].dropna().unique().tolist()),
            'top': [_jugador(f, n) for n, f in enumerate(df.head(TOP_PLANILLA).to_dict('records'), 1)],
            'tweet': {
                'texto': componer_tweet(seleccionados,
                                        top_por_sentimiento(sentiment_tweet, 3)),
                'medidos': len(sentiment_tweet),
                'seleccionados': len(del_tweet),
                'sentimiento': sentiment_tweet,
            },
        })
    return semanas


def construir_historico(directorio):
    """Histórico recalculado desde los rankings semanales + resumen por liga."""
    df = cargar_rankings(directorio)
    if df.empty:
        return [], []
    acumulado = agregar_apariciones(df)
    filas = []
    for f in acumulado.to_dict('records'):
        filas.append({
            'posicion': _int(f['posicion_historica']),
            'nombre': f['nombre'],
            'liga': f['liga_principal'],
            'clubes': f['clubes'],
            'apariciones_top5': _int(f['apariciones_top5']),
            'semanas_en_ranking': _int(f['semanas_en_ranking']),
            'semanas_activas_liga': _int(f['semanas_activas_liga']),
            'tasa_top5': _num(f['tasa_top5'], 3),
            'mejor_posicion': _int(f['mejor_posicion']),
            'goles': _int(f.get('goles')),
            'asistencias': _int(f.get('asistencias')),
            'ultima_semana': f['ultima_semana'],
        })
    por_liga = [{'liga': f['liga'],
                 'semanas_activas': _int(f['semanas_activas']),
                 'jugadores_distintos': _int(f['jugadores_distintos']),
                 'apariciones_top5': _int(f['apariciones_top5'])} for f in resumen_por_liga(df).to_dict('records')]
    return filas, por_liga


def construir_modelo():
    """Metadatos leidos de los artefactos, sin recalcular el modelo."""
    modelos = dir_models()
    config = joblib.load(os.path.join(modelos, 'config.pkl'))
    features = joblib.load(os.path.join(modelos, 'features_list.pkl'))
    estimador = joblib.load(os.path.join(modelos, 'modelo_adn_boca.pkl'))
    params = estimador.get_params()
    return {
        'features': list(features),
        'grupos_posicion': [f for f in features if f.startswith('pos_')],
        'penalty': params.get('penalty'),
        'solver': params.get('solver'),
        'C': params.get('C'),
        'class_weight': params.get('class_weight'),
        'calibracion': 'Platt (sigmoid) sobre el OOF agrupado por jugador',
        'orden_ranking': 'score crudo del modelo; el calibrador es monotonico y no reordena',
    }


def construir_datos(directorio=None, modelos=None):
    directorio = directorio or dir_datos()
    modelos = modelos or dir_models()
    semanas = construir_semanas(directorio)
    historico, por_liga = construir_historico(directorio)
    return {
        'generado': date.today().isoformat(),
        'modelo': construir_modelo(),
        'semanas': list(reversed(semanas)),
        'historico': historico,
        'por_liga': por_liga,
    }


def escribir_js(datos, ruta=DATA_JS):
    os.makedirs(os.path.dirname(ruta), exist_ok=True)
    with open(ruta, 'w', encoding='utf-8') as f:
        f.write('window.RADAR_DATA = ')
        json.dump(datos, f, ensure_ascii=False, separators=(',', ':'))
        f.write(';\n')
    return ruta


def main():
    datos = construir_datos()
    ruta = escribir_js(datos)
    print(f'{ruta} ({os.path.getsize(ruta) / 1024:.1f} KB)')
    print(f"  semanas: {len(datos['semanas'])} "
          f"[{datos['semanas'][-1]['clave']}..{datos['semanas'][0]['clave']}]")
    print(f"  historico: {len(datos['historico'])} jugadores")
    return datos


if __name__ == '__main__':
    main()