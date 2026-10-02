"""Corrida semanal del radar con gate de ligas: TOTW -> sentimiento -> tweet -> web.

Es el punto de entrada para correr la semana a mano o desde el programador de tareas
de Windows. El gate evita escribir una semana incompleta: hace falta que al menos
`MIN_LIGAS_MIN` ligas hayan publicado TOTW de verdad (tener fixtures en la semana no
alcanza, porque FotMob publica la fecha con dias de atraso). Si el gate no se
cumple no se escribe ni el ranking, ni el tweet, ni la landing: la semana anterior
queda intacta y el siguiente intento reevalua lo mismo.

Uso:
    python src/corrida_semanal.py
    python src/corrida_semanal.py --forzar            # ignora el gate
    python src/corrida_semanal.py --min-ligas 4       # gate mas exigente
    python src/corrida_semanal.py --sin-sentimiento   # solo ranking, sin cuota de YouTube

Como FotMob publica el TOTW con dias de atraso, conviene correrlo mas de una vez por
semana: si el gate no se cumple no pasa nada y el siguiente intento reevalua la misma
semana (mismo bloque semanal cerrado).

Codigos de salida (para que el scheduler distinga los casos):
    0  corrida completa: ranking, borrador de tweet y landing regenerada
    2  no se produjo salida: gate no cumplido o sin jugadores puntuables
    1  error inesperado (el traceback queda en el log)
"""

import argparse
import logging
import os
import sys
from logging.handlers import RotatingFileHandler

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, SCRIPT_DIR)

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


def _logger(nombre=NOMBRE_LOG):
    """Log a stdout y a `outputs/logs/<nombre>` rotando por tamaño."""
    directorio = os.path.join(dir_outputs(), 'logs')
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


def corrida(min_ligas=MIN_LIGAS_MIN, forzar=False, con_sentimiento=True):
    """Corre la semana completa. Devuelve el codigo de salida."""
    log = _logger()
    log.info('=' * 60)
    detalle = {}
    log.info('Paso 1: radar semanal TOTW (FotMob)')
    ranking, no_resueltos, inicio = _radar(detalle)

    semana = detalle.get('semana', '?')
    con_totw = detalle.get('ligas_con_totw', [])
    sin_totw = detalle.get('ligas_sin_totw', [])
    log.info(f"Semana {semana} ({detalle.get('inicio')} a {detalle.get('fin')})")
    log.info(f'Ligas con TOTW publicado ({len(con_totw)}): '
             f'{", ".join(con_totw) or "ninguna"}')
    log.info(f'Ligas sin TOTW en la semana ({len(sin_totw)}): '
             f'{", ".join(sin_totw) or "ninguna"}')

    n_ligas = int(detalle.get('n_ligas_con_totw', 0))
    if not cumple_gate(detalle, min_ligas):
        log.info(f'GATE NO CUMPLIDO: hacen falta {min_ligas} ligas con TOTW y hay '
                 f'{n_ligas}. No se escribe nada; se reintenta en la proxima corrida. '
                 f'(--forzar ignora el gate)')
        if not forzar:
            return EXIT_SIN_SALIDA

    if ranking is None or ranking.empty:
        log.info('Sin jugadores puntuables: no se genera borrador de tweet.')
        return EXIT_SIN_SALIDA

    log.info('Paso 2: ranking semanal de la semana')
    ranking_path, no_resueltos_path = guardar_resultados(ranking, no_resueltos, inicio)
    log.info(f'Ranking: {ranking_path} ({len(ranking)} jugadores)')
    log.info(f'No resueltos: {no_resueltos_path}')

    if not con_sentimiento:
        log.info('Pasos 3/4 omitidos (--sin-sentimiento): no se genera el tweet.')
        return EXIT_SIN_SALIDA

    log.info('Paso 3: sentimiento (hinchada + medios) y borrador de tweet')
    resultado = generar_borrador(ranking, semana=semana,
                                  cache_path=os.path.join(
                                      dir_datos(), f'sentimiento_radar_{semana}.csv'))
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

    log.info(f'Corrida completa para {semana}')
    return EXIT_OK


def main():
    parser = argparse.ArgumentParser(description='Corrida semanal del radar ADN Boca')
    parser.add_argument('--min-ligas', type=int, default=MIN_LIGAS_MIN,
                        help=f'ligas con TOTW requeridas (default {MIN_LIGAS_MIN})')
    parser.add_argument('--forzar', action='store_true',
                        help='genera la salida aunque el gate no se cumpla')
    parser.add_argument('--sin-sentimiento', action='store_true',
                        help='guarda el ranking y omite el sentimiento y el tweet '
                             '(no consume cuota de YouTube)')
    args = parser.parse_args()

    try:
        return corrida(min_ligas=args.min_ligas, forzar=args.forzar,
                       con_sentimiento=not args.sin_sentimiento)
    except Exception as exc:
        logging.getLogger('corrida_semanal').exception('Corrida fallida')
        print(f'Error inesperado: {type(exc).__name__}: {exc}')
        return EXIT_ERROR


if __name__ == '__main__':
    sys.exit(main())