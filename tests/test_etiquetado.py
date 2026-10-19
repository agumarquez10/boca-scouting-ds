import json

import pandas as pd

from etiquetado_sentimiento import (
    COLUMNAS,
    construir_pool,
    escribir_muestra,
    muestrear,
    recolectar_textos,
)


def fila(fuente, texto, puntaje):
    return {'fuente': fuente, 'nombre': 'X', 'club': 'Y', 'texto': texto, 'puntaje': puntaje}


def test_construir_pool_quita_duplicados_y_cortos():
    textos = {'Ana|Club': {
        'youtube': ['Gran partido de Ana hoy', 'gran partido de ana  hoy!', 'corto'],
        'prensa': ['Ana suena para el club', 'Ana suena para el club'],
    }}
    pool = construir_pool(textos)
    assert len(pool) == 2
    assert {f['fuente'] for f in pool} == {'youtube', 'prensa'}
    assert all(len(f['texto']) >= 20 for f in pool)


def test_muestrear_es_reproducible_y_reparte_por_fuente():
    pool = [fila('youtube', f'comentario {i}', float(i)) for i in range(100)]
    pool += [fila('prensa', f'titular {i}', float(-i)) for i in range(100)]
    a = muestrear(pool, 50, semilla=7)
    b = muestrear(pool, 50, semilla=7)
    assert [f['texto'] for f in a] == [f['texto'] for f in b]
    assert sum(1 for f in a if f['fuente'] == 'youtube') == 50
    assert sum(1 for f in a if f['fuente'] == 'prensa') == 50
    assert [f['id'] for f in a] == [f'{i:04d}' for i in range(1, len(a) + 1)]


def test_muestrear_cubre_el_rango_de_puntajes():
    pool = [fila('youtube', f'comentario {i}', float(i)) for i in range(200)]
    muestra = muestrear(pool, 50, semilla=1)
    puntajes = [f['puntaje'] for f in muestra]
    assert min(puntajes) < 40 and max(puntajes) > 160


def test_escribir_muestra_es_ciega(tmp_path):
    muestra = muestrear([fila('prensa', f'titular numero {i}', float(i)) for i in range(40)],
                        20, semilla=3)
    for i, f in enumerate(muestra, 1):
        f['id'] = f'{i:04d}'
    escribir_muestra(muestra, {'X|Y': {'prensa': ['t'], 'youtube': []}}, directorio=str(tmp_path))

    df = pd.read_csv(tmp_path / 'muestra.csv', encoding='utf-8-sig')
    assert list(df.columns) == COLUMNAS
    js = (tmp_path / 'muestra.js').read_text(encoding='utf-8')
    filas = json.loads(js.split('=', 1)[1].strip().rstrip(';'))
    assert all(set(f) == set(COLUMNAS) for f in filas)
    assert (tmp_path / 'textos_crudos.json').exists()


def test_recolectar_textos_limita_youtube_y_usa_prensa_para_todos():
    jugadores = [(f'J{i}', 'C') for i in range(10)]
    llamadas = {'youtube': 0, 'prensa': 0}

    def prensa(nombre, club):
        llamadas['prensa'] += 1
        return {'textos': [f'titular de {nombre}']}

    def youtube(nombre, club):
        llamadas['youtube'] += 1
        return {'textos': [f'comentario sobre {nombre}']}

    textos = recolectar_textos(jugadores, 3, prensa=prensa, youtube=youtube)
    assert llamadas == {'youtube': 3, 'prensa': 10}
    assert len(textos) == 10
    assert sum(1 for v in textos.values() if v['youtube']) == 3
