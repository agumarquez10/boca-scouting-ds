"""Corrida semanal del radar con gate de ligas: TOTW -> sentimiento -> tweet -> web.

Es el punto de entrada para correr la semana a mano o desde el programador de tareas
de Windows. El gate evita escribir una semana incompleta: hace falta que al menos
`MIN_LIGAS_MIN` ligas hayan publicado TOTW de verdad (tener fixtures en la semana no
alcanza, porque FotMob publica la fecha con dias de atraso). Si el gate no se
cumple no se escribe ni el ranking, ni el tweet, ni la landing: la semana anterior
queda intacta y el siguiente intento reevalua lo mismo.

La corrida es idempotente: guarda un marcador por semana en `data/estado/`. Si la
semana ya esta completa no vuelve a pegarle a FotMob; si tiene el ranking pero le
falta el tweet, retoma desde ahi. Asi una tarea programada diaria no re-consume
cuota ni pisa una semana ya publicada.

Uso:
    python src/corrida_semanal.py
    python src/corrida_semanal.py --forzar            # ignora el gate y el marcador
    python src/corrida_semanal.py --min-ligas 4       # gate mas exigente
    python src/corrida_semanal.py --sin-sentimiento   # solo ranking, sin cuota de YouTube
    python src/corrida_semanal.py --log-dir logs      # otro destino para el log

Como FotMob publica el TOTW con dias de atraso, conviene correrlo mas de una vez por
semana: si el gate no se cumple no pasa nada y el siguiente intento reevalua la misma
semana (mismo bloque semanal cerrado).

Codigos de salida (para que el scheduler distinga los casos):
    0  corrida completa: ranking, borrador de tweet y landing regenerada
    1  error inesperado (el traceback queda en el log)
    2  no se produjo salida: gate no cumplido o sin jugadores puntuables
    3  corrida parcial: ranking escrito, pero sin sentimiento ni tweet
"""

import argparse
import json
import logging
import os
import sys
from logging.handlers import RotatingFileHandler

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, SCRIPT_DIR)

import pandas as pd

from automatizacion import generar_borrador
from fotmob_api import FotMobApi
from scouting_pipeline import (generar_ranking_semanal, guardar_resultados,
                               ultimo_bloque_semanal_completo)

from rutas import dir_datos, dir_outputs

MIN_LIGAS_MIN = 3
NOMBRE_LOG = 'corrida_semanal.log'
MAX_BYTES_LOG = 512 * 1024
RESPALDOS_LOG = 3

EXIT_OK = 0
EXIT_ERROR = 1
EXIT_SIN_SALIDA = 2
EXIT_PARCIAL = 3

ESTADO_RANKING = 'ranking'
ESTADO_COMPLETA = 'completa'


def _logger(nombre=NOMBRE_LOG, directorio=None):
    """Log a stdout y a `directorio/<nombre>` rotando por tamaño."""
    directorio = directorio or os.path.join(dir_outputs(), 'logs')
    os.makedirs(directorio, exist_ok=True)
    log = logging.getLogger('corrida_semanal')
    log.setLevel(logging.INFO)
    for handler in log.handlers[:]:
        log.removeHandler(handler)
        handler.close()
    formato = logging.Formatter('%(asctime)s %(levelname)s %(message)s')

    archivo = RotatingFileHandler(os.path.join(directorio, nombre),
                                  maxBytes=MAX_BYTES_LOG,
                                  backupCount=RESPALDOS_LOG, encoding='utf-8')
    archivo.setFormatter(formato)
    log.addHandler(archivo)

    consola = logging.StreamHandler(sys.stdout)
    consola.setFormatter(logging.Formatter('%(message)s'))
    log.addHandler(consola)
    return log


def cumple_gate(detalle, min_ligas=MIN_LIGAS_MIN):
    """True si suficientes ligas publican TOTW en la semana."""
    return int(detalle.get('n_ligas_con_totw', 0)) >= min_ligas


def ruta_marcador(semana, directorio=None):
    """Ruta del marcador de estado de la semana."""
    directorio = directorio or dir_datos()
    return os.path.join(directorio, 'estado', f'corrida_{semana}.json')


def leer_marcador(semana, directorio=None):
    """Estado guardado de la semana; None si todavia no se corrio."""
    ruta = ruta_marcador(semana, directorio)
    if not os.path.exists(ruta):
        return None
    try:
        with open(ruta, encoding='utf-8') as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError):
        return None


def guardar_marcador(semana, estado, detalle=None, directorio=None):
    """Deja el estado de la semana para que la proxima corrida sepa donde quedo.

    El marcador guarda `n_ligas_con_totw` (conteo) y `ligas_con_totw` (nombres).
    """
    from datetime import datetime, timezone

    datos = {
        'semana': semana,
        'estado': estado,
        'generado': datetime.now(timezone.utc).isoformat(timespec='seconds'),
    }
    datos.update(detalle or {})
    if 'n_ligas_con_totw' not in datos:
        datos['n_ligas_con_totw'] = len(datos.get('ligas_con_totw', []))
    ruta = ruta_marcador(semana, directorio)
    os.makedirs(os.path.dirname(ruta), exist_ok=True)
    with open(ruta, 'w', encoding='utf-8') as f:
        json.dump(datos, f, ensure_ascii=False, indent=2)
    return ruta


def _semana_del_bloque():
    """Clave ISO de la semana cerrada que corresponde al bloque actual."""
    inicio, _ = ultimo_bloque_semanal_completo()
    iso = inicio.isocalendar()
    return f'{iso.year}-W{iso.week:02d}'


def _refrescar_landing(log):
    from landing_data import main as landing_main
    datos = landing_main()
    log.info(f'Landing regenerada: {len(datos["semanas"])} semanas, '
             f'{len(datos["historico"])} jugadores en el historico')


def _radar(detalle):
    """Consulta FotMob y puntua la semana. No escribe nada en disco: decide el gate."""
    inicio, fin = ultimo_bloque_semanal_completo()
    fotmob = FotMobApi()
    try:
        ranking, no_resueltos, avisos = generar_ranking_semanal(
            fotmob, inicio, fin, detalle=detalle)
    finally:
        fotmob.close()
    for aviso in avisos:
        print(f'[aviso] {aviso}')
    return ranking, no_resueltos, inicio


def _leer_ranking_guardado(semana, directorio=None):
    """Relee el ranking ya escrito de una corrida anterior de la misma semana."""
    directorio = directorio or dir_datos()
    ruta = os.path.join(directorio, f'ranking_jugadores_fecha_{semana}.csv')
    if not os.path.exists(ruta):
        return None
    df = pd.read_csv(ruta, encoding='utf-8-sig')
    return None if df.empty else df


def corrida(min_ligas=MIN_LIGAS_MIN, forzar=False, con_sentimiento=True,
            directorio_log=None, directorio_datos=None):
    """Corre la semana completa. Devuelve el codigo de salida."""
    log = _logger(directorio=directorio_log)
    log.info('=' * 60)
    detalle = {}

    marcador = None if forzar else leer_marcador(
        _semana_del_bloque(), directorio=directorio_datos)
    if marcador and marcador.get('estado') == ESTADO_COMPLETA:
        log.info(f"Semana {marcador.get('semana')} ya estaba completa "
                 f'({marcador.get("generado")}). No se reprocesa '
                 f'(--forzar lo ignora).')
        return EXIT_OK

    log.info('Paso 1: radar semanal TOTW (FotMob)')
    retomar = bool(marcador) and marcador.get('estado') == ESTADO_RANKING
    if retomar:
        semana = marcador['semana']
        ranking = _leer_ranking_guardado(semana, directorio=directorio_datos)
        log.info(f'Se retoma la semana {semana}: el ranking ya estaba escrito, '
                 f'no se vuelve a consultar FotMob.')
        detalle.update({'semana': semana,
                        'n_ligas_con_totw': marcador.get('n_ligas_con_totw', 0),
                        'ligas_con_totw': marcador.get('ligas_con_totw', []),
                        'inicio': marcador.get('inicio'), 'fin': marcador.get('fin')})
        no_resueltos = pd.DataFrame()
        inicio = marcador.get('inicio')
    else:
        ranking, no_resueltos, inicio = _radar(detalle)
        semana = detalle.get('semana', '?')

    log.info(f"Semana {semana} ({detalle.get('inicio')} a {detalle.get('fin')})")
    con_totw = detalle.get('ligas_con_totw', [])
    sin_totw = detalle.get('ligas_sin_totw', [])
    log.info(f'Ligas con TOTW publicado ({len(con_totw)}): '
             f'{", ".join(con_totw) or "ninguna"}')
    log.info(f'Ligas sin TOTW en la semana ({len(sin_totw)}): '
             f'{", ".join(sin_totw) or "ninguna"}')

    n_ligas = int(detalle.get('n_ligas_con_totw', 0))
    if not cumple_gate(detalle, min_ligas):
        if retomar:
            log.info('Se retoma una semana ya puntuada: no se vuelve a evaluar el gate.')
        else:
            log.info(f'GATE NO CUMPLIDO: hacen falta {min_ligas} ligas con TOTW y hay '
                     f'{n_ligas}. No se escribe nada; se reintenta en la proxima corrida. '
                     f'(--forzar ignora el gate)')
            if not forzar:
                return EXIT_SIN_SALIDA

    if ranking is None or ranking.empty:
        log.info('Sin jugadores puntuables: no se genera borrador de tweet.')
        return EXIT_SIN_SALIDA

    log.info('Paso 2: ranking semanal de la semana')
    if retomar:
        log.info(f'Ranking ya guardado ({len(ranking)} jugadores); no se reescribe.')
    else:
        ranking_path, no_resueltos_path = guardar_resultados(
            ranking, no_resueltos, inicio,
            directorio=directorio_datos or dir_datos())
        log.info(f'Ranking: {ranking_path} ({len(ranking)} jugadores)')
        log.info(f'No resueltos: {no_resueltos_path}')
        guardar_marcador(semana, ESTADO_RANKING, {
            'inicio': str(inicio), 'fin': detalle.get('fin'),
            'ligas_con_totw': con_totw, 'n_ligas_con_totw': n_ligas,
            'jugadores': len(ranking),
        }, directorio=directorio_datos)

    if not con_sentimiento:
        log.info('Pasos 3/4 omitidos (--sin-sentimiento): no se genera el tweet.')
        return EXIT_PARCIAL

    log.info('Paso 3: sentimiento (hinchada + medios) y borrador de tweet')
    resultado = generar_borrador(ranking, semana=semana,
                                  cache_path=os.path.join(
                                      directorio_datos or dir_datos(),
                                      f'sentimiento_radar_{semana}.csv'))
    log.info(f'Sentimiento: {resultado["con_datos"]}/{len(resultado["jugadores"])} '
             f'jugadores con datos')
    log.info(f'Tweet ({len(resultado["texto"])} caracteres):')
    for linea in resultado['texto'].splitlines():
        log.info(f'  {linea}')

    log.info('Paso 4: landing web/data.js')
    try:
        _refrescar_landing(log)
    except Exception as exc:
        log.error(f'No se pudo refrescar la landing: {type(exc).__name__}: {exc}')
        return EXIT_ERROR

    guardar_marcador(semana, ESTADO_COMPLETA, {
        'inicio': str(inicio), 'fin': detalle.get('fin'),
        'ligas_con_totw': con_totw, 'n_ligas_con_totw': n_ligas,
        'jugadores': len(ranking), 'con_sentimiento': True,
        'tweet_caracteres': len(resultado['texto']),
    }, directorio=directorio_datos)

    log.info(f'Corrida completa para {semana}')
    return EXIT_OK


def main():
    parser = argparse.ArgumentParser(description='Corrida semanal del radar ADN Boca')
    parser.add_argument('--min-ligas', type=int, default=MIN_LIGAS_MIN,
                        help=f'ligas con TOTW requeridas (default {MIN_LIGAS_MIN})')
    parser.add_argument('--forzar', action='store_true',
                        help='genera la salida aunque el gate no se cumpla y aunque '
                             'la semana ya este marcada como completa')
    parser.add_argument('--sin-sentimiento', action='store_true',
                        help='guarda el ranking y omite el sentimiento y el tweet '
                             '(no consume cuota de YouTube)')
    parser.add_argument('--log-dir', default=None,
                        help='directorio del log (default outputs/logs)')
    args = parser.parse_args()

    try:
        return corrida(min_ligas=args.min_ligas, forzar=args.forzar,
                       con_sentimiento=not args.sin_sentimiento,
                       directorio_log=args.log_dir)
    except Exception as exc:
        logging.getLogger('corrida_semanal').exception('Corrida fallida')
        print(f'Error inesperado: {type(exc).__name__}: {exc}')
        return EXIT_ERROR


if __name__ == '__main__':
    sys.exit(main())
