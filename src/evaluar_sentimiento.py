"""Evalua el motor de sentimiento contra etiquetas humanas (Fase 3).

Lee la muestra de `etiquetado_sentimiento.py` y las etiquetas de `etiquetas.csv`
(id, etiqueta con -1, 0 o +1; las no etiquetadas se ignoran), y compara:

- lexico: solo el lexicon de hinchada.
- vader: solo VADER (ingles), sin lexicon.
- actual: VADER + lexicon, que es lo que usa el radar (BERT apagado).
- bert (opcional, --bert): el mismo motor con BERT encendido. Requiere descargar
  el modelo; no se corre por defecto.

Metricas por variante: correlacion de Spearman entre el puntaje y la etiqueta
(ordinal, no depende de un umbral) y F1 macro / accuracy con dos umbrales de
clasificacion (0 y `--umbral`, por defecto 5 sobre la escala de +-50). Tambien
reporta Spearman por fuente (youtube / prensa).

Limite: la mezcla 60/40 entre fuentes se decide por jugador, no por texto; esta
evaluacion no la puede medir. Solo dice que fuente y que motor concuerdan con
las etiquetas humanas.

Uso:
    python src/evaluar_sentimiento.py
    python src/evaluar_sentimiento.py --bert
"""

import argparse
import json
import os
import sys

import pandas as pd
from sklearn.metrics import accuracy_score, f1_score

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, SCRIPT_DIR)

from rutas import dir_datos

DIR_ETIQUETADO = os.path.join(dir_datos(), 'etiquetado')
MINIMO_ETIQUETAS = 30
CLASES = [-1, 0, 1]


def clasificar(puntajes, umbral):
    """-1 / 0 / +1 segun el puntaje supere +-umbral (en la escala de +-50)."""
    return [1 if p > umbral else (-1 if p < -umbral else 0) for p in puntajes]


def metricas(etiquetas, puntajes, umbral):
    """Spearman entre puntaje y etiqueta; F1 macro y accuracy con el umbral dado."""
    serie_p = pd.Series(puntajes, dtype=float)
    serie_e = pd.Series(etiquetas, dtype=float)
    rho = serie_p.corr(serie_e, method='spearman') if len(serie_p) > 2 else float('nan')
    pred = clasificar(puntajes, umbral)
    return {
        'n': len(etiquetas),
        'spearman': None if pd.isna(rho) else round(float(rho), 4),
        f'f1_macro_umbral_{umbral:g}': round(float(f1_score(
            etiquetas, pred, labels=CLASES, average='macro', zero_division=0)), 4),
        f'accuracy_umbral_{umbral:g}': round(float(accuracy_score(etiquetas, pred)), 4),
    }


def evaluar(df, variantes, umbral=5.0):
    """`df` trae columnas fuente, etiqueta, texto. `variantes`: nombre -> fn(texto)."""
    resultados = {}
    for nombre, fn in variantes.items():
        puntajes = [float(fn(t)) for t in df['texto']]
        resultados[nombre] = {
            'todas': metricas(df['etiqueta'].tolist(), puntajes, umbral),
            'por_fuente': {},
        }
        for fuente in sorted(df['fuente'].unique()):
            mascara = (df['fuente'] == fuente).tolist()
            sub_p = [p for p, m in zip(puntajes, mascara) if m]
            sub_e = [e for e, m in zip(df['etiqueta'].tolist(), mascara) if m]
            resultados[nombre]['por_fuente'][fuente] = metricas(sub_e, sub_p, umbral)
    return resultados


def cargar(directorio):
    muestra = pd.read_csv(os.path.join(directorio, 'muestra.csv'), encoding='utf-8-sig',
                          dtype={'id': str})
    ruta_etiquetas = os.path.join(directorio, 'etiquetas.csv')
    if not os.path.exists(ruta_etiquetas):
        return pd.DataFrame(columns=['id', 'fuente', 'texto', 'etiqueta'])
    etiquetas = pd.read_csv(ruta_etiquetas, encoding='utf-8-sig', dtype={'id': str})
    df = muestra.merge(etiquetas, on='id', how='inner')
    df = df[df['etiqueta'].isin(CLASES)].copy()
    df['etiqueta'] = df['etiqueta'].astype(int)
    return df


def variantes_del_motor(bert=False):
    from nlp_engine import ESCALA, SentimientoEngine, _ajuste_lexico, _tokens, clasificar_vader

    def lexico(texto):
        return max(-1.0, min(1.0, _ajuste_lexico(_tokens(texto)) * 0.3)) * ESCALA

    def vader(texto):
        return clasificar_vader(texto) * ESCALA

    actual = SentimientoEngine(usar_bert=False)
    variantes = {'lexico': lexico, 'vader': vader, 'actual': actual.puntuar}
    if bert:
        variantes['bert'] = SentimientoEngine(usar_bert=True).puntuar
    return variantes


def main():
    parser = argparse.ArgumentParser(description='Evalua el sentimiento contra etiquetas')
    parser.add_argument('--umbral', type=float, default=5.0)
    parser.add_argument('--bert', action='store_true',
                        help='incluye la variante con BERT (descarga el modelo)')
    parser.add_argument('--directorio', default=DIR_ETIQUETADO)
    args = parser.parse_args()

    df = cargar(args.directorio)
    print(f'Etiquetas usadas: {len(df)} (fuentes: {df["fuente"].value_counts().to_dict()})')
    if len(df) < MINIMO_ETIQUETAS:
        print(f'No alcanza: hacen falta al menos {MINIMO_ETIQUETAS} textos etiquetados. '
              f'No se calcula nada todavia.')
        return 2

    resultados = evaluar(df, variantes_del_motor(bert=args.bert), umbral=args.umbral)
    for nombre, r in resultados.items():
        t = r['todas']
        print(f"{nombre:8s} spearman {t['spearman']}  f1 {t[f'f1_macro_umbral_{args.umbral:g}']}  "
              f"acc {t[f'accuracy_umbral_{args.umbral:g}']}")
        for fuente, rf in r['por_fuente'].items():
            print(f"           {fuente:8s} n={rf['n']:3d} spearman {rf['spearman']}")
    ruta = os.path.join(args.directorio, 'evaluacion.json')
    with open(ruta, 'w', encoding='utf-8') as f:
        json.dump({'n_etiquetas': len(df), 'umbral': args.umbral,
                   'resultados': resultados}, f, ensure_ascii=False, indent=2)
    print(f'-> {ruta}')
    return 0


if __name__ == '__main__':
    sys.exit(main())
