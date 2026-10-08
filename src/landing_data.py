"""Construye `web/data.js` para la landing del radar: una lectura, sin recalcular.

Toma los rankings semanales, el sentimiento ya cacheado y el ranking historico
acumulado y los vuelca como un objeto global (`window.RADAR_DATA`) para que la
pagina se abra con doble click en `file://` sin servidor.

Offline por diseno: no consulta la API ni toca el modelo. Publica el corte por
puesto que despues usa `automatizacion` para componer el tweet (top 3 de cada
grupo DEL/MED/DEF) y el top 3 por sentimiento entre esos nueve; faltante queda
como None y la pagina reserva el lugar, nunca 0.

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

from automatizacion import ORDEN_PUESTOS, _macro_posicion, seleccionar_por_puesto
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
    """(nombre, club) -> registro de la cache semanal; vacio si no se midio."""
    ruta = os.path.join(directorio, f'sentimiento_radar_{semana}.csv')
    if not os.path.exists(ruta):
        return []
    df = pd.read_csv(ruta, encoding='utf-8-sig')
    return [{'nombre': f['nombre'],
             'club': f.get('club'),
             'sentimiento': _num(f.get('sentimiento'), 1),
             'n_fuentes': _int(f.get('n_fuentes')) or 0,
             'youtube': _num(f.get('youtube_valor'), 1),
             'prensa': _num(f.get('prensa_valor'), 1),
             'youtube_n_comentarios': _int(f.get('youtube_n_comentarios')),
             'prensa_n_textos': _int(f.get('prensa_n_textos'))}
            for f in df.to_dict('records')]


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


def _puestos(df, registros):
    """Top 3 de cada grupo de puesto con el sentimiento cacheado de la semana.

    Es el corte que despues usa `automatizacion` para componer el tweet: los
    grupos siempre en orden DEL/MED/DEF, con lo que haya cacheado de esa semana.
    Un grupo sin candidatos se devuelve vacio, no se omite.
    """
    cache = {(r['nombre'], r['club']): r for r in registros}
    seleccion = seleccionar_por_puesto(df)
    salida = []
    for macro in ORDEN_PUESTOS:
        grupo = seleccion.get(macro)
        jugadores = []
        if grupo is not None and not grupo.empty:
            for fila in grupo.itertuples():
                found = cache.get((fila.nombre, fila.club))
                jugadores.append({
                    'nombre': fila.nombre,
                    'club': fila.club,
                    'liga': fila.liga,
                    'goles': _int(fila.goles),
                    'asistencias': _int(fila.asistencias),
                    'sentimiento': _num(found['sentimiento'], 1) if found else None,
                    'n_fuentes': found['n_fuentes'] if found else 0,
                    'youtube': found['youtube'] if found else None,
                    'prensa': found['prensa'] if found else None,
                    'youtube_n_comentarios': (found['youtube_n_comentarios']
                                              if found else None),
                    'prensa_n_textos': found['prensa_n_textos'] if found else None,
                })
        salida.append({'macro': macro, 'jugadores': jugadores})
    return salida


def _top_sentimiento(puestos):
    """Top 3 por sentimiento entre los candidatos del corte por puesto.

    Mismo criterio que la linea SENT del tweet: solo los que tienen dato
    cacheado, ordenados de mayor a menor. Sin cache la lista queda vacia.
    """
    registros = [{'nombre': j['nombre'], 'club': j['club'], 'sentimiento': j['sentimiento'],
                   'goles': j['goles'], 'asistencias': j['asistencias'],
                   'n_fuentes': j['n_fuentes'], 'youtube': j['youtube'],
                   'prensa': j['prensa'],
                   'youtube_n_comentarios': j['youtube_n_comentarios'],
                   'prensa_n_textos': j['prensa_n_textos']}
                  for p in puestos for j in p['jugadores']]
    return [{'nombre': r['nombre'], 'club': r['club'],
              'goles': r['goles'], 'asistencias': r['asistencias'],
              'sentimiento': _num(r['sentimiento'], 1),
              'n_fuentes': r['n_fuentes'], 'youtube': r['youtube'], 'prensa': r['prensa'],
              'youtube_n_comentarios': _int(r.get('youtube_n_comentarios')),
              'prensa_n_textos': _int(r.get('prensa_n_textos'))}
             for r in top_por_sentimiento(registros, 3)]


def construir_semanas(directorio):
    """Una entrada por semana ISO con la planilla del top 5 y el corte por puesto."""
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

        puestos = _puestos(df, _sentimiento_semana(clave, directorio))
        inicio, fin = _rango_semana(clave)
        semanas.append({
            'clave': clave,
            'inicio': inicio,
            'fin': fin,
            'jugadores': len(df),
            'ligas': sorted(df['liga'].dropna().unique().tolist()),
            'top': [_jugador(f, n) for n, f in enumerate(df.head(TOP_PLANILLA).to_dict('records'), 1)],
            'puestos': puestos,
            'sentimiento': _top_sentimiento(puestos),
            'medidos': sum(1 for p in puestos for j in p['jugadores']
                           if j['sentimiento'] is not None),
            'seleccionados': sum(len(p['jugadores']) for p in puestos),
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


def construir_sentimiento(directorio):
    """Historial de sentimiento que deja `sentimiento_historico.py`.

    Solo lee los CSV que ese script ya escribio (no recalcula ni consulta la
    API): el detalle por jugador-semana y el consolidado por jugador. El
    breakdown de fuentes se arma del detalle porque el acumulado no lo guarda.
    """
    detalle = []
    ruta = os.path.join(directorio, 'sentimiento_historico.csv')
    if os.path.exists(ruta):
        df = pd.read_csv(ruta, encoding='utf-8-sig')
        for f in df.to_dict('records'):
            detalle.append({
                'semana': f['semana'],
                'puesto': f['puesto'],
                'nombre': f['nombre'],
                'club': f.get('club'),
                'sentimiento': _num(f.get('sentimiento'), 1),
                'n_fuentes': _int(f.get('n_fuentes')) or 0,
                'youtube': _num(f.get('youtube_valor'), 1),
                'prensa': _num(f.get('prensa_valor'), 1),
                'youtube_n_comentarios': _int(f.get('youtube_n_comentarios')),
                'prensa_n_textos': _int(f.get('prensa_n_textos')),
            })

    fuentes = {}
    for f in detalle:
        vistas = fuentes.setdefault(f['nombre'], set())
        if f['prensa'] is not None:
            vistas.add('prensa')
        if f['youtube'] is not None:
            vistas.add('youtube')

    acumulado = []
    ruta = os.path.join(directorio, 'sentimiento_historico_acumulado.csv')
    if os.path.exists(ruta):
        df = pd.read_csv(ruta, encoding='utf-8-sig')
        for f in df.to_dict('records'):
            vistas = fuentes.get(f['nombre'], set())
            acumulado.append({
                'posicion': len(acumulado) + 1,
                'nombre': f['nombre'],
                'club': f.get('club'),
                'semanas_medidas': _int(f['semanas_medidas']),
                'sentimiento_medio': _num(f['sentimiento_medio'], 2),
                'sentimiento_max': _num(f['sentimiento_max'], 1),
                'sentimiento_min': _num(f['sentimiento_min'], 1),
                'primera_semana': f['primera_semana'],
                'ultima_semana': f['ultima_semana'],
                'fuentes': len(vistas),
            })
    return detalle, acumulado


def construir_datos(directorio=None, modelos=None):
    directorio = directorio or dir_datos()
    modelos = modelos or dir_models()
    semanas = construir_semanas(directorio)
    historico, por_liga = construir_historico(directorio)
    detalle, sentimiento = construir_sentimiento(directorio)
    return {
        'generado': date.today().isoformat(),
        'modelo': construir_modelo(),
        'semanas': list(reversed(semanas)),
        'historico': historico,
        'por_liga': por_liga,
        'sentimiento': {
            'mediciones': len(detalle),
            'jugadores': len(sentimiento),
            'acumulado': sentimiento,
            'detalle': detalle,
        },
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
    print(f"  sentimiento: {datos['sentimiento']['mediciones']} mediciones, "
          f"{datos['sentimiento']['jugadores']} jugadores")
    return datos


if __name__ == '__main__':
    main()
