import json
import os

import pandas as pd
import pytest

from landing_data import (
    construir_datos,
    construir_historico,
    construir_semanas,
    escribir_js,
)


def fila(pid, nombre, liga, club, posicion, ranking, score, prob, goles, asistencias):
    return {
        'player_id_fotmob': pid,
        'nombre': nombre,
        'liga': liga,
        'club': club,
        'posicion': posicion,
        'ranking': ranking,
        'score_adn_boca': score,
        'probabilidad_adn': prob,
        'goles': goles,
        'asistencias': asistencias,
        'edad': 27,
        'partidos_temporada': 20,
        'torneos_stats': 'Liga Profesional, Copa Argentina',
        'rating_totw': 8.5,
    }


def escribir(directorio, year, week, filas):
    pd.DataFrame(filas).to_csv(
        directorio / f'ranking_jugadores_fecha_{year}-W{week:02d}.csv',
        index=False, encoding='utf-8-sig')


@pytest.fixture
def semanas_tmp(tmp_path):
    escribir(tmp_path, 2026, 39, [
        fila(1, 'Ronaldo Martinez', 'Argentina', 'Velez', 'Centre-Forward', 2, 0.8, 0.7, 6, 1),
        fila(2, 'Bruno Vega', 'Argentina', 'Talleres', 'Right Winger', 1, 0.95, 0.9, 9, 2),
    ])
    escribir(tmp_path, 2026, 40, [
        fila(2, 'Bruno Vega', 'Argentina', 'Talleres', 'Right Winger', 1, 0.9, 0.85, 10, 3),
    ])
    return tmp_path


def test_semanas_ordenadas_y_con_rango_iso(semanas_tmp):
    semanas = construir_semanas(semanas_tmp)
    assert [s['clave'] for s in semanas] == ['2026-W39', '2026-W40']
    assert semanas[0]['inicio'] == '2026-09-21'
    assert semanas[0]['fin'] == '2026-09-27'


def test_planilla_ordena_por_score_y_no_por_ranking(semanas_tmp):
    semana = construir_semanas(semanas_tmp)[0]
    assert [j['lugar'] for j in semana['top']] == [1, 2]
    assert [j['nombre'] for j in semana['top']] == ['Bruno Vega', 'Ronaldo Martinez']
    assert semana['top'][0]['puesto'] == 'DEL'


def test_borrador_usa_el_compositor_y_omite_sentimiento_sin_cache(semanas_tmp):
    semana = construir_semanas(semanas_tmp)[0]
    assert semana['tweet']['texto'].startswith('ADN Boca - Top por puesto (G+A)')
    assert 'DEL: Bruno Vega (Talleres) 9+2' in semana['tweet']['texto']
    assert semana['tweet']['medidos'] == 0
    assert 'SENT' not in semana['tweet']['texto']


def test_sentimiento_cacheado_entra_al_borrador(tmp_path):
    escribir(tmp_path, 2026, 41, [
        fila(1, 'Uno', 'Peru', 'Alianza', 'Centre-Forward', 1, 0.9, 0.8, 5, 1),
    ])
    pd.DataFrame([
        {'nombre': 'Uno', 'club': 'Alianza', 'sentimiento': 4.2, 'n_fuentes': 2,
         'fuentes': 'prensa,youtube', 'youtube_valor': 3.0, 'prensa_valor': 5.0},
    ]).to_csv(tmp_path / 'sentimiento_radar_2026-W41.csv', index=False, encoding='utf-8-sig')

    semana = construir_semanas(tmp_path)[0]
    assert semana['tweet']['medidos'] == 1
    assert semana['tweet']['sentimiento'][0]['sentimiento'] == 4.2
    assert 'SENT (hinchada+medios): Uno (Alianza) +4.2' in semana['tweet']['texto']


def test_historico_consolida_por_identidad(semanas_tmp):
    historico, por_liga = construir_historico(semanas_tmp)
    assert len(historico) == 2
    assert historico[0]['nombre'] == 'Bruno Vega'
    assert historico[0]['apariciones_top5'] == 2
    assert historico[0]['semanas_activas_liga'] == 2
    assert por_liga[0]['liga'] == 'Argentina'
    assert por_liga[0]['apariciones_top5'] == 3


def test_historico_vacio_sin_rankings(tmp_path):
    assert construir_historico(tmp_path) == ([], [])


def test_escribir_js_produce_json_serializable(tmp_path, semanas_tmp):
    datos = construir_datos(directorio=semanas_tmp, modelos='models')
    ruta = escribir_js(datos, str(tmp_path / 'data.js'))

    contenido = open(ruta, encoding='utf-8').read()
    assert contenido.startswith('window.RADAR_DATA = ')
    assert contenido.rstrip().endswith(';')
    payload = json.loads(contenido.split('=', 1)[1].strip().rstrip(';'))
    assert payload['modelo']['features'][0] == 'goles'
    assert 'rating' not in payload['modelo']['features']
    assert len(payload['semanas']) == 2
    assert payload['historico'][0]['posicion'] == 1


def test_web_data_js_esta_actualizado():
    raiz = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    ruta = os.path.join(raiz, 'web', 'data.js')
    if not os.path.exists(ruta):
        pytest.skip('todavia no se genero web/data.js')
    contenido = open(ruta, encoding='utf-8').read()
    payload = json.loads(contenido.split('=', 1)[1].strip().rstrip(';'))
    assert payload['semanas']
    assert payload['historico']
    assert payload['modelo']['penalty'] == 'l1'