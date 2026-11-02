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

Con `--semana YYYY-Www` reprocesa una semana ya cerrada (backfill): el bloque
semanal es siempre [lunes 00:00 UTC, lunes siguiente).

Uso:
    python src/corrida_semanal.py
    python src/corrida_semanal.py --forzar            # ignora el gate y el marcador
    python src/corrida_semanal.py --min-ligas 4       # gate mas exigente
    python src/corrida_semanal.py --sin-sentimiento   # solo ranking, sin cuota de YouTube
    python src/corrida_semanal.py --log-dir logs      # otro destino para el log
    python src/corrida_semanal.py --semana 2026-W40   # reprocesa una semana pasada
    python src/corrida_semanal.py --diaria            # automatica: revisa 3 semanas, tope YouTube

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
from datetime import timedelta
from logging.handlers import RotatingFileHandler

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, SCRIPT_DIR)

import pandas as pd

from automatizacion import generar_borrador
from fotmob_api import FotMobApi
from scouting_pipeline import (bloque_semana_cerrada, generar_ranking_semanal,
                               guardar_resultados, ultimo_bloque_semanal_completo)

from rutas import dir_datos, dir_outputs

MIN_LIGAS_MIN = 3
CUOTA_YOUTUBE_DIARIA = 1000
SEMANAS_REVISION = 3
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


def _semana_del_bloque(inicio):
    """Clave ISO de la semana a la que corresponde un bloque semanal."""
    iso = inicio.isocalendar()
    return f'{iso.year}-W{iso.week:02d}'


def _refrescar_landing(log):
    from landing_data import main as landing_main
    datos = landing_main()
    log.info(f'Landing regenerada: {len(datos["semanas"])} semanas, '
             f'{len(datos["historico"])} jugadores en el historico')


def _refrescar_historicos(log, directorio=None):
    """Regenera el ranking y el sentimiento historicos que lee la landing.

    Sin esto la seccion "El pulso de las menciones" queda congelada: la landing
    lee `sentimiento_historico.csv` y ese archivo solo lo escribe este script.
    """
    from ranking_historico import main as ranking_main
    from sentimiento_historico import main as sentimiento_main

    directorio = directorio or dir_datos()
    acumulado = ranking_main(directorio=directorio)
    if acumulado is not None:
        log.info(f'Ranking historico: {len(acumulado)} jugadores consolidados')
    consolidado = sentimiento_main(directorio=directorio)
    if consolidado is not None:
        log.info(f'Sentimiento historico: {len(consolidado)} jugadores consolidados')


def _radar(detalle, inicio=None, fin=None):
    """Consulta FotMob y puntua la semana. No escribe nada en disco: decide el gate."""
    if inicio is None:
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


def _ultima_semana_cerrada():
    inicio, _ = ultimo_bloque_semanal_completo()
    return _semana_del_bloque(inicio)


def _firma(df):
    """Jugadores y scores del ranking, para saber si una revision cambio algo."""
    if df is None or df.empty:
        return ()
    ids = df['player_id_fotmob'].astype(str)
    scores = df['score_adn_boca'].round(6).astype(str)
    return tuple(sorted(zip(ids, scores)))


def _revisar(semana, marcador, inicio, fin, detalle, directorio_datos, log):
    """Revisa una semana ya completa contra FotMob.

    Devuelve (ranking, no_resueltos, inicio) si hay que reescribirla por ligas
    tardias o por una correccion del calculo; None si no cambio nada o si una
    liga dejo de publicar (en ese caso no se reescribe, por las dudas).
    """
    ranking, no_resueltos, inicio = _radar(detalle, inicio, fin)
    detalle.setdefault('semana', semana)
    antes = set(marcador.get('ligas_con_totw', []))
    ahora = set(detalle.get('ligas_con_totw', []))
    nuevas = sorted(ahora - antes)
    perdidas = sorted(antes - ahora)
    guardado = _leer_ranking_guardado(semana, directorio=directorio_datos)
    if not nuevas and _firma(ranking) == _firma(guardado):
        log.info(f'Revision {semana}: sin cambios.')
        return None
    if perdidas:
        log.warning(f'Revision {semana}: ligas que ya no publican TOTW {perdidas}; '
                    f'no se reescribe la semana.')
        return None
    log.info(f'Revision {semana}: ligas nuevas {nuevas or "ninguna"}; se reescribe el ranking.')
    return ranking, no_resueltos, inicio


def corrida(min_ligas=MIN_LIGAS_MIN, forzar=False, con_sentimiento=True,
            directorio_log=None, directorio_datos=None, semana=None,
            con_historicos=True, revisar=False, cuota_youtube=CUOTA_YOUTUBE_DIARIA):
    """Corre la semana completa. Devuelve el codigo de salida.

    `revisar=True` consulta de nuevo una semana ya completa: reescribe solo si
    aparecio una liga nueva o si el ranking cambio.
    """
    log = _logger(directorio=directorio_log)
    log.info('=' * 60)
    detalle = {}

    if semana:
        inicio, fin = bloque_semana_cerrada(semana)
    else:
        inicio, fin = ultimo_bloque_semanal_completo()
    semana = _semana_del_bloque(inicio)
    if not forzar:
        marcador = leer_marcador(semana, directorio=directorio_datos)
    else:
        marcador = None
    consultado = None
    if marcador and marcador.get('estado') == ESTADO_COMPLETA:
        if not revisar:
            log.info(f"Semana {marcador.get('semana')} ya estaba completa "
                     f'({marcador.get("generado")}). No se reprocesa '
                     f'(--forzar lo ignora).')
            return EXIT_OK
        consultado = _revisar(semana, marcador, inicio, fin, detalle, directorio_datos, log)
        if consultado is None:
            return EXIT_OK
        marcador = None

    log.info('Paso 1: radar semanal TOTW (FotMob)')
    retomar = bool(marcador) and marcador.get('estado') == ESTADO_RANKING
    if retomar:
        ranking = _leer_ranking_guardado(semana, directorio=directorio_datos)
        log.info(f'Se retoma la semana {semana}: el ranking ya estaba escrito, '
                 f'no se vuelve a consultar FotMob.')
        detalle.update({'semana': semana,
                        'n_ligas_con_totw': marcador.get('n_ligas_con_totw', 0),
                        'ligas_con_totw': marcador.get('ligas_con_totw', []),
                        'inicio': marcador.get('inicio'), 'fin': marcador.get('fin')})
        no_resueltos = pd.DataFrame()
        gate_previo = bool(marcador.get('gate_forzado', False))
    else:
        gate_previo = False
        if consultado is None:
            ranking, no_resueltos, inicio = _radar(detalle, inicio, fin)
            detalle.setdefault('semana', semana)
        else:
            ranking, no_resueltos, inicio = consultado
        forzar = forzar or consultado is not None

    log.info(f"Semana {semana} ({detalle.get('inicio')} a {detalle.get('fin')})")
    con_totw = detalle.get('ligas_con_totw', [])
    sin_totw = detalle.get('ligas_sin_totw', [])
    log.info(f'Ligas con TOTW publicado ({len(con_totw)}): '
             f'{", ".join(con_totw) or "ninguna"}')
    log.info(f'Ligas sin TOTW en la semana ({len(sin_totw)}): '
             f'{", ".join(sin_totw) or "ninguna"}')

    n_ligas = int(detalle.get('n_ligas_con_totw', 0))
    gate_forzado = gate_previo
    if not cumple_gate(detalle, min_ligas):
        if retomar:
            log.info('Se retoma una semana ya puntuada: no se vuelve a evaluar el gate.')
        else:
            log.info(f'GATE NO CUMPLIDO: hacen falta {min_ligas} ligas con TOTW y hay '
                     f'{n_ligas}. No se escribe nada; se reintenta en la proxima corrida. '
                     f'(--forzar ignora el gate)')
            if not forzar:
                return EXIT_SIN_SALIDA
            gate_forzado = True
            log.warning(f'Gate FORZADO: la semana {semana} se escribe con {n_ligas} '
                        f'liga(s) de {min_ligas} requeridas. Queda marcada en el marcador.')

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
            'jugadores': len(ranking), 'gate_forzado': gate_forzado,
        }, directorio=directorio_datos)

    if not con_sentimiento:
        log.info('Pasos 3/4 omitidos (--sin-sentimiento): no se genera el tweet.')
        return EXIT_PARCIAL

    log.info('Paso 3: sentimiento (hinchada + medios) y borrador de tweet')
    datos = directorio_datos or dir_datos()
    from sentimiento_jugadores_youtube import configurar_cuota, cuota_usada
    configurar_cuota(datos, cuota_youtube)
    resultado = generar_borrador(ranking, semana=semana,
                                  cache_path=os.path.join(
                                      datos, f'sentimiento_radar_{semana}.csv'),
                                  tweet_path=os.path.join(datos, f'tweet_{semana}.txt'),
                                  escribir_principal=semana == _ultima_semana_cerrada())
    log.info(f'Cuota YouTube del dia: {cuota_usada()}/{cuota_youtube} unidades')
    log.info(f'Sentimiento: {resultado["con_datos"]}/{len(resultado["jugadores"])} '
             f'jugadores con datos')
    log.info(f'Tweet ({len(resultado["texto"])} caracteres):')
    for linea in resultado['texto'].splitlines():
        log.info(f'  {linea}')

    log.info('Paso 4: historicos (ranking acumulado y sentimiento historico)')
    if con_historicos:
        try:
            _refrescar_historicos(log, directorio=directorio_datos)
        except Exception as exc:
            log.error(f'No se pudieron refrescar los historicos: '
                      f'{type(exc).__name__}: {exc}')
            return EXIT_ERROR
    else:
        log.info('Historicos omitidos (--sin-historicos).')

    log.info('Paso 5: landing web/data.js')
    try:
        _refrescar_landing(log)
    except Exception as exc:
        log.error(f'No se pudo refrescar la landing: {type(exc).__name__}: {exc}')
        return EXIT_ERROR

    guardar_marcador(semana, ESTADO_COMPLETA, {
        'inicio': str(inicio), 'fin': detalle.get('fin'),
        'ligas_con_totw': con_totw, 'n_ligas_con_totw': n_ligas,
        'jugadores': len(ranking), 'con_sentimiento': True,
        'con_historicos': con_historicos, 'gate_forzado': gate_forzado,
        'tweet_caracteres': len(resultado['texto']),
    }, directorio=directorio_datos)

    log.info(f'Corrida completa para {semana}')
    return EXIT_OK


def corrida_diaria(cuota_youtube=CUOTA_YOUTUBE_DIARIA, directorio_log=None,
                   directorio_datos=None, semanas=SEMANAS_REVISION):
    """Corrida automatica: la ultima semana cerrada y las anteriores, revisadas.

    Revisar las ultimas semanas cierra dos huecos: ligas que FotMob publica con
    atraso y correcciones del calculo. Devuelve el codigo de la semana mas
    reciente; si alguna semana fallo con error, devuelve EXIT_ERROR.
    """
    inicio, _ = ultimo_bloque_semanal_completo()
    codigos = []
    for k in range(semanas):
        semana = _semana_del_bloque(inicio - timedelta(days=7 * k))
        codigos.append(corrida(semana=semana, revisar=True, cuota_youtube=cuota_youtube,
                               directorio_log=directorio_log,
                               directorio_datos=directorio_datos))
    if EXIT_ERROR in codigos:
        return EXIT_ERROR
    return codigos[0]


def main():
    parser = argparse.ArgumentParser(description='Corrida semanal del radar ADN Boca')
    parser.add_argument('--diaria', action='store_true',
                        help='corrida automatica: revisa las ultimas semanas cerradas '
                             f'({SEMANAS_REVISION}) y respeta el tope de cuota de YouTube')
    parser.add_argument('--revisar', action='store_true',
                        help='con --semana: consulta una semana ya completa y la reescribe '
                             'solo si aparecio una liga nueva o cambio el ranking')
    parser.add_argument('--cuota-youtube', type=int, default=CUOTA_YOUTUBE_DIARIA,
                        help=f'tope de unidades de YouTube por dia (default {CUOTA_YOUTUBE_DIARIA})')
    parser.add_argument('--min-ligas', type=int, default=MIN_LIGAS_MIN,
                        help=f'ligas con TOTW requeridas (default {MIN_LIGAS_MIN})')
    parser.add_argument('--forzar', action='store_true',
                        help='genera la salida aunque el gate no se cumpla y aunque '
                             'la semana ya este marcada como completa')
    parser.add_argument('--sin-sentimiento', action='store_true',
                        help='guarda el ranking y omite el sentimiento y el tweet '
                             '(no consume cuota de YouTube)')
    parser.add_argument('--sin-historicos', action='store_true',
                        help='no regenera el ranking ni el sentimiento historicos')
    parser.add_argument('--semana', default=None,
                        help='semana ISO a reprocesar (YYYY-Www); por defecto, '
                             'la ultima semana cerrada')
    parser.add_argument('--log-dir', default=None,
                        help='directorio del log (default outputs/logs)')
    args = parser.parse_args()

    try:
        if args.diaria:
            return corrida_diaria(cuota_youtube=args.cuota_youtube,
                                  directorio_log=args.log_dir)
        return corrida(min_ligas=args.min_ligas, forzar=args.forzar,
                       con_sentimiento=not args.sin_sentimiento,
                       directorio_log=args.log_dir, semana=args.semana,
                       con_historicos=not args.sin_historicos,
                       revisar=args.revisar, cuota_youtube=args.cuota_youtube)
    except ValueError as exc:
        print(f'Error: {exc}')
        return EXIT_ERROR
    except Exception as exc:
        logging.getLogger('corrida_semanal').exception('Corrida fallida')
        print(f'Error inesperado: {type(exc).__name__}: {exc}')
        return EXIT_ERROR


if __name__ == '__main__':
    sys.exit(main())
