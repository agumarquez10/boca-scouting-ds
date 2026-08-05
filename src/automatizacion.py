import os
import subprocess
import sys

import pandas as pd

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, SCRIPT_DIR)

DATA_DIR = os.path.join(SCRIPT_DIR, '..', 'data')
OUTPUTS_DIR = os.path.join(SCRIPT_DIR, '..', 'outputs')
NOTEBOOK_NLP = os.path.join(SCRIPT_DIR, 'sentimiento_hinchada.ipynb')
RANKING_CSV = os.path.join(DATA_DIR, 'scouting_resultado.csv')
SENTIMIENTO_CSV = os.path.join(DATA_DIR, 'sentimiento_hinchada.csv')
TWEET_TXT = os.path.join(DATA_DIR, 'tweet_top5.txt')
TOP_N = 5


def correr_scouting():
    from scouting_pipeline import main as scouting_main
    return scouting_main()


def correr_nlp():
    out = os.path.join(OUTPUTS_DIR, '_sentimiento_ejecutado.ipynb')
    subprocess.run(
        [sys.executable, '-m', 'papermill', NOTEBOOK_NLP, out],
        check=True, capture_output=True,
    )
    if not os.path.exists(SENTIMIENTO_CSV):
        raise FileNotFoundError('sentimiento_hinchada.csv no se generó')
    return pd.read_csv(SENTIMIENTO_CSV)


def hype_actual(sent):
    sent['fecha'] = pd.to_datetime(sent['fecha'])
    ultima = sent['fecha'].max()
    semana = sent[sent['fecha'] >= ultima - pd.Timedelta(days=7)]
    if semana.empty:
        return None
    neto = semana['compound'].mean()
    positividad = (semana['clasificacion'] == 'positivo').mean()
    volumen = len(semana)
    atenuacion = min(1.0, __import__('numpy').log1p(volumen) / 3.0)
    return (0.6 * neto + 0.4 * positividad) * atenuacion


def clasificar_hype(valor):
    if valor is None:
        return 'sin datos'
    if valor > 0.15:
        return 'hinchada eufórica'
    if valor > 0.05:
        return 'clima positivo'
    if valor < -0.05:
        return 'clima negativo'
    return 'clima neutral'


def componer_tweet(ranking, hype):
    top = ranking.head(TOP_N)
    lineas = [f'{i + 1}) {r.nombre} ({r.club_actual}) — prob. {r.probabilidad:.3f}'
              for i, r in top.iterrows()]
    texto = [
        'Ranking semanal ADN Boca',
        *lineas,
        f'Hype hinchada: {hype:.3f} ({clasificar_hype(hype)})',
        '#Boca #MercadoDePases #Fichajes',
    ]
    return '\n'.join(texto)


def publicar_tweet(texto):
    api_key = os.getenv('TWITTER_API_KEY')
    api_secret = os.getenv('TWITTER_API_SECRET')
    access_token = os.getenv('TWITTER_ACCESS_TOKEN')
    access_secret = os.getenv('TWITTER_ACCESS_TOKEN_SECRET')
    if not all([api_key, api_secret, access_token, access_secret]):
        with open(TWEET_TXT, 'w', encoding='utf-8') as f:
            f.write(texto + '\n')
        print(f'[aviso] Sin credenciales de Twitter: tweet guardado en {TWEET_TXT}')
        return False
    try:
        from requests_oauthlib import OAuth1
        import requests
    except ImportError:
        with open(TWEET_TXT, 'w', encoding='utf-8') as f:
            f.write(texto + '\n')
        print('[aviso] requests-oauthlib no instalado: tweet guardado en archivo')
        return False
    auth = OAuth1(api_key, api_secret, access_token, access_secret)
    r = requests.post(
        'https://api.twitter.com/2/tweets', auth=auth,
        json={'text': texto},
    )
    if r.status_code in (200, 201):
        print('Tweet publicado:', r.json().get('data', {}).get('id'))
        return True
    print(f'[error] Twitter respondió {r.status_code}: {r.text[:300]}')
    return False


def main():
    from dotenv import load_dotenv
    load_dotenv(os.path.join(SCRIPT_DIR, '..', 'secrets', '.env'))

    print('== Paso 1: ranking de candidatos ==')
    correr_scouting()
    ranking = pd.read_csv(RANKING_CSV)

    print('\n== Paso 2: sentimiento de la hinchada ==')
    sent = correr_nlp()
    hype = hype_actual(sent)

    print('\n== Paso 3: tweet top-5 ==')
    texto = componer_tweet(ranking, hype)
    print('--- borrador ---')
    print(texto)
    print('----------------')
    publicar_tweet(texto)


if __name__ == '__main__':
    main()
