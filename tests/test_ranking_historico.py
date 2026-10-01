import pandas as pd
import pytest

from ranking_historico import (
    agregar_apariciones,
    cargar_rankings,
    resumen_por_liga,
)


def fila(pid, nombre, liga, club, ranking, score, prob, goles, asistencias):
    return {
        'player_id_fotmob': pid,
        'nombre': nombre,
        'liga': liga,
        'club': club,
        'ranking': ranking,
        'score_adn_boca': score,
        'probabilidad_adn': prob,
        'goles': goles,
        'asistencias': asistencias,
    }


def escribir(directorio, year, week, filas):
    df = pd.DataFrame(filas)
    df.to_csv(directorio / f'ranking_jugadores_fecha_{year}-W{week:02d}.csv',
              index=False, encoding='utf-8-sig')


@pytest.fixture
def rankings_tmp(tmp_path):
    escribir(tmp_path, 2026, 34, [
        fila(1, 'Uno', 'A', 'ClubA', 1, 0.9, 0.8, 5, 1),
        fila(2, 'Dos', 'A', 'ClubA', 6, 0.5, 0.4, 3, 0),
        fila(3, 'Tres', 'B', 'ClubB', 1, 0.95, 0.9, 7, 2),
    ])
    escribir(tmp_path, 2026, 35, [
        fila(1, 'Uno', 'A', 'ClubA', 3, 0.8, 0.7, 10, 2),
    ])
    escribir(tmp_path, 2026, 36, [
        fila(2, 'Dos', 'A', 'ClubA', 2, 0.7, 0.6, 4, 1),
    ])
    (tmp_path / 'ranking_historico_acumulado.csv').write_text('x', encoding='utf-8')
    (tmp_path / 'otro.csv').write_text('x', encoding='utf-8')
    return tmp_path


def test_cargar_rankings_lee_patron_y_agrega_semana(rankings_tmp):
    df = cargar_rankings(rankings_tmp)
    assert set(df['semana']) == {'2026-W34', '2026-W35', '2026-W36'}
    assert df['anio'].eq(2026).all()
    assert len(df) == 5


def test_cargar_rankings_filtra_por_anio(rankings_tmp):
    escribir(rankings_tmp, 2025, 10, [fila(9, 'Viejo', 'A', 'ClubA', 1, 0.9, 0.8, 1, 1)])
    df = cargar_rankings(rankings_tmp, anio=2026)
    assert df['anio'].eq(2026).all()
    assert 9 not in set(df['player_id_fotmob'])


def test_agregar_apariciones_cuenta_top5_y_tasa_normalizada(rankings_tmp):
    acumulado = agregar_apariciones(cargar_rankings(rankings_tmp))
    por_id = acumulado.set_index('player_id_fotmob')

    uno = por_id.loc[1]
    assert uno['apariciones_top5'] == 2
    assert uno['semanas_en_ranking'] == 2
    assert uno['semanas_activas_liga'] == 3
    assert uno['tasa_top5'] == pytest.approx(2 / 3, abs=1e-4)

    dos = por_id.loc[2]
    assert dos['apariciones_top5'] == 1
    assert dos['tasa_top5'] == pytest.approx(1 / 3, abs=1e-4)

    tres = por_id.loc[3]
    assert tres['apariciones_top5'] == 1
    assert tres['semanas_activas_liga'] == 1
    assert tres['tasa_top5'] == 1.0


def test_agregar_apariciones_ordena_por_top5(rankings_tmp):
    acumulado = agregar_apariciones(cargar_rankings(rankings_tmp))
    assert list(acumulado['player_id_fotmob'])[0] == 1
    assert list(acumulado['posicion_historica']) == list(range(1, len(acumulado) + 1))


def test_agregar_apariciones_goles_de_ultima_semana_no_suma(rankings_tmp):
    acumulado = agregar_apariciones(cargar_rankings(rankings_tmp))
    uno = acumulado.set_index('player_id_fotmob').loc[1]
    assert uno['goles'] == 10
    assert uno['asistencias'] == 2
    assert uno['ultima_semana'] == '2026-W35'


def test_agregar_apariciones_deduplica_jugador_semana(tmp_path):
    escribir(tmp_path, 2026, 20, [
        fila(1, 'Uno', 'A', 'ClubA', 7, 0.4, 0.3, 1, 0),
        fila(1, 'Uno', 'A', 'ClubA', 2, 0.8, 0.7, 2, 1),
    ])
    acumulado = agregar_apariciones(cargar_rankings(tmp_path))
    assert len(acumulado) == 1
    assert acumulado.loc[0, 'mejor_posicion'] == 2
    assert acumulado.loc[0, 'apariciones_top5'] == 1


def test_resumen_por_liga(rankings_tmp):
    resumen = resumen_por_liga(cargar_rankings(rankings_tmp)).set_index('liga')
    assert resumen.loc['A', 'semanas_activas'] == 3
    assert resumen.loc['A', 'jugadores_distintos'] == 2
    assert resumen.loc['A', 'apariciones_top5'] == 3
    assert resumen.loc['B', 'semanas_activas'] == 1
    assert resumen.loc['B', 'apariciones_top5'] == 1


def test_vacio_sin_archivos(tmp_path):
    assert cargar_rankings(tmp_path).empty
    assert agregar_apariciones(pd.DataFrame()).empty
    assert resumen_por_liga(pd.DataFrame()).empty
