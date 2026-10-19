"""Muestra etiquetable para validar el sentimiento del radar (Fase 3).

Reune los textos crudos (comentarios de YouTube y titulares de prensa) de los
jugadores del corte por puesto de las semanas registradas, quita duplicados y
arma una muestra estratificada por puntaje para que quien etiqueta vea textos
de todo el rango. La muestra se escribe en `data/etiquetado/` (no versionado):

- muestra.csv: id, fuente, nombre, club, texto (sin puntaje: etiquetado a ciegas).
- muestra.js: lo mismo como `window.MUESTRA`, para la herramienta `etiquetado/index.html`.
- textos_crudos.json: todos los textos recolectados, por jugador y fuente.

YouTube cobra 100 unidades de cuota por busqueda: `--max-youtube` limita a cuantos
jugadores se les buscan comentarios. La prensa (RSS) no tiene cuota.

Uso:
    python src/etiquetado_sentimiento.py --max-youtube 15 --n 150

Las etiquetas (-1, 0, +1) las pone una persona: este script no etiqueta nada.
"""

import argparse
import json
import os
import random
import re
import sys
import unicodedata

import pandas as pd

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, SCRIPT_DIR)

from rutas import dir_datos

DIR_ETIQUETADO = os.path.join(dir_datos(), 'etiquetado')
MIN_LARGO = 20
SEMILLA = 42
BINS = 5
COLUMNAS = ['id', 'fuente', 'nombre', 'club', 'texto']


def _clave_texto(texto):
    t = unicodedata.normalize('NFKD', str(texto))
    t = ''.join(c for c in t if not unicodedata.combining(c)).lower()
    return ' '.join(re.sub(r'[^a-z0-9]+', ' ', t).split())


def jugadores_de_semanas(directorio=None):
    """(nombre, club) del corte por puesto de cada semana registrada."""
    from sentimiento_historico import jugadores_de_semana, semanas_registradas

    vistos = []
    for _, ruta in semanas_registradas(directorio or dir_datos()):
        ranking = pd.read_csv(ruta, encoding='utf-8-sig')
        for nombre, club, _ in jugadores_de_semana(ranking):
            if (nombre, club) not in vistos:
                vistos.append((nombre, club))
    return vistos


def recolectar_textos(jugadores, max_youtube, prensa=None, youtube=None, semilla=SEMILLA):
    """Textos crudos por jugador. YouTube solo para `max_youtube` jugadores.

    `prensa` y `youtube` son las funciones que devuelven el dict de la fuente
    (inyectables para tests). Por defecto usan los modulos reales.
    """
    if prensa is None:
        from sentimiento_jugadores_prensa import sentimiento_jugador_prensa as prensa
    if youtube is None:
        from sentimiento_jugadores_youtube import sentimiento_jugador_youtube as youtube

    rng = random.Random(semilla)
    con_youtube = set(rng.sample(jugadores, min(max_youtube, len(jugadores))))
    textos = {}
    for nombre, club in jugadores:
        clave = f'{nombre}|{club}'
        entrada = {'prensa': prensa(nombre, club).get('textos', []), 'youtube': []}
        if (nombre, club) in con_youtube:
            entrada['youtube'] = youtube(nombre, club).get('textos', [])
        textos[clave] = entrada
    return textos


def construir_pool(textos_por_clave):
    """Filas (fuente, nombre, club, texto) sin duplicados ni textos cortos."""
    pool, vistos = [], set()
    for clave, fuentes in textos_por_clave.items():
        nombre, club = clave.split('|', 1)
        for fuente in ('youtube', 'prensa'):
            for texto in fuentes.get(fuente, []):
                texto = ' '.join(str(texto).split())
                norm = _clave_texto(texto)
                if len(norm) < MIN_LARGO or norm in vistos:
                    continue
                vistos.add(norm)
                pool.append({'fuente': fuente, 'nombre': nombre, 'club': club,
                             'texto': texto})
    return pool


def puntajes_del_pool(pool, engine):
    """Puntaje actual del motor para estratificar la muestra (no se muestra)."""
    for fila in pool:
        fila['puntaje'] = engine.puntuar(fila['texto'])
    return pool


def muestrear(pool, n_por_fuente, semilla=SEMILLA, bins=BINS):
    """Muestra estratificada por puntaje dentro de cada fuente.

    Divide el rango de puntajes de la fuente en `bins` tramos y toma la misma
    cantidad de textos de cada tramo (o todos si hay menos). Asi la muestra no
    queda concentrada en el puntaje neutro, que es lo mas comun.
    """
    rng = random.Random(semilla)
    muestra = []
    for fuente in ('youtube', 'prensa'):
        filas = [f for f in pool if f['fuente'] == fuente]
        if not filas:
            continue
        filas.sort(key=lambda f: f['puntaje'])
        tramos = [filas[i * len(filas) // bins:(i + 1) * len(filas) // bins]
                  for i in range(bins)]
        por_tramo = max(1, n_por_fuente // bins)
        elegidas = []
        for tramo in tramos:
            elegidas.extend(rng.sample(tramo, min(por_tramo, len(tramo))))
        muestra.extend(elegidas[:n_por_fuente])
    rng.shuffle(muestra)
    for i, fila in enumerate(muestra, 1):
        fila['id'] = f'{i:04d}'
    return muestra


def escribir_muestra(muestra, textos_por_clave, directorio=None):
    directorio = directorio or DIR_ETIQUETADO
    os.makedirs(directorio, exist_ok=True)
    df = pd.DataFrame(muestra)[COLUMNAS]
    df.to_csv(os.path.join(directorio, 'muestra.csv'), index=False, encoding='utf-8-sig')
    with open(os.path.join(directorio, 'textos_crudos.json'), 'w', encoding='utf-8') as f:
        json.dump(textos_por_clave, f, ensure_ascii=False, indent=1)
    ciega = [{'id': f['id'], 'fuente': f['fuente'], 'nombre': f['nombre'],
              'club': f['club'], 'texto': f['texto']} for f in muestra]
    with open(os.path.join(directorio, 'muestra.js'), 'w', encoding='utf-8') as f:
        f.write('window.MUESTRA = ')
        json.dump(ciega, f, ensure_ascii=False)
        f.write(';\n')
    return os.path.join(directorio, 'muestra.csv')


def main():
    from nlp_engine import SentimientoEngine

    parser = argparse.ArgumentParser(description='Muestra etiquetable del sentimiento')
    parser.add_argument('--max-youtube', type=int, default=15,
                        help='jugadores a los que se les buscan comentarios (100 u de cuota c/u)')
    parser.add_argument('--n', type=int, default=150,
                        help='textos por fuente en la muestra')
    args = parser.parse_args()

    jugadores = jugadores_de_semanas()
    print(f'Jugadores en el corte por puesto: {len(jugadores)}')
    textos = recolectar_textos(jugadores, args.max_youtube)
    pool = construir_pool(textos)
    print(f'Textos unicos: {len(pool)} '
          f'(youtube {sum(1 for f in pool if f["fuente"] == "youtube")}, '
          f'prensa {sum(1 for f in pool if f["fuente"] == "prensa")})')
    puntajes_del_pool(pool, SentimientoEngine(usar_bert=False))
    muestra = muestrear(pool, args.n)
    ruta = escribir_muestra(muestra, textos)
    print(f'Muestra: {len(muestra)} textos -> {ruta}')


if __name__ == '__main__':
    main()
