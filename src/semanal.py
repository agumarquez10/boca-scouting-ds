"""
Automatiizacion semanal: ranking final (ADN + sentimiento) y tweet top-5.

Combina:
  - data/candidatos_adn.csv       (probabilidad ADN Boca, 0.0-1.0)
  - data/sentimiento_jugadores.csv(sentimiento hinchada, -50 a +50)

Genera:
  - data/ranking_semanal.csv
  - data/tweet_top5.txt (+ publica si hay credenciales de Twitter)

El top 5 sale del ranking por ADN con maximo 1 jugador por posicion (grupo),
y muestra el sentimiento como metrica independiente.
"""

import os
import sys

import pandas as pd

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, SCRIPT_DIR)

from rutas import dir_datos, dir_secrets

DATA_DIR = dir_datos()
TOP_N = 5


def combinar(candidatos_path, sentimiento_path):
    cand = pd.read_csv(candidatos_path, encoding='utf-8-sig')
    if os.path.exists(sentimiento_path):
        sent = pd.read_csv(sentimiento_path, encoding='utf-8-sig')
        df = cand.merge(
            sent[['nombre', 'sentimiento', 'n_fuentes', 'youtube_valor', 'ole_valor']],
            on='nombre', how='left',
        )
    else:
        df = cand.copy()
        df['sentimiento'] = None
        df['n_fuentes'] = 0
    df['sentimiento'] = df['sentimiento'].fillna(0.0)
    return df


def top_diverso(df, n=TOP_N, por_posicion='grupo_posicion'):
    """Maximo 1 jugador por posicion (grupo), ordenado por ADN desc."""
    if por_posicion not in df.columns:
        return df.sort_values('probabilidad', ascending=False).head(n).copy()
    top = []
    usadas = set()
    rank = df.sort_values('probabilidad', ascending=False)
    for _, fila in rank.iterrows():
        pos = fila.get(por_posicion)
        if pos is None or pos in usadas:
            continue
        usadas.add(pos)
        top.append(fila)
        if len(top) >= n:
            break
    return pd.DataFrame(top)


def _fmt_sentimiento(v, n):
    if not n:
        return 's/d'
    return f'{v:+.1f}'


def componer_tweet(top):
    lineas = []
    for i, r in enumerate(top.itertuples(), 1):
        nom = getattr(r, 'nombre')
        club = getattr(r, 'club')
        liga = getattr(r, 'liga')
        adn = getattr(r, 'probabilidad')
        sent = getattr(r, 'sentimiento')
        nf = getattr(r, 'n_fuentes')
        context = f'{club} · {liga}' if club else str(liga)
        lineas.append(
            f"{i}) {nom} ({context})\n"
            f"   ADN Boca {adn:.0%} | Sentimiento {_fmt_sentimiento(sent, nf)}"
        )
    return '\n'.join(lineas)


def main():
    cand_path = os.path.join(DATA_DIR, 'candidatos_adn.csv')
    sent_path = os.path.join(DATA_DIR, 'sentimiento_jugadores.csv')
    if not os.path.exists(cand_path):
        raise FileNotFoundError('Falta candidatos_adn.csv. Corré scouting_mercado.py')

    df = combinar(cand_path, sent_path)

    ranking = df.sort_values('probabilidad', ascending=False).reset_index(drop=True)
    ranking_out = os.path.join(DATA_DIR, 'ranking_semanal.csv')
    ranking.to_csv(ranking_out, index=False, encoding='utf-8-sig')

    top = top_diverso(df, TOP_N)
    top_out = os.path.join(DATA_DIR, 'ranking_top5.csv')
    top.to_csv(top_out, index=False, encoding='utf-8-sig')

    texto = (
        'Ranking semanal ADN Boca (11 ideal)\n'
        'TOP 5 candidatos con ADN Boca y sentimiento de la hinchada:\n\n'
        + componer_tweet(top)
        + '\n\nADN Boca: probabilidad modelo (0-100) | Sentimiento: -50 a +50 '
        '(YouTube + Olé). Más de 30 partidos en 2 temporadas, menores de 32.\n'
        '#Boca #MercadoDePases #Fichajes'
    )

    tweet_path = os.path.join(DATA_DIR, 'tweet_top5.txt')
    with open(tweet_path, 'w', encoding='utf-8') as f:
        f.write(texto + '\n')

    print('=== RANKING SEMANAL TOP 5 ===')
    print(texto)
    print(f'\nGuardado: {ranking_out}, {top_out}, {tweet_path}')

    publicar_tweet(texto)
    return top


def publicar_tweet(texto):
    from dotenv import load_dotenv
    load_dotenv(os.path.join(dir_secrets(), '.env'))
    api_key = os.getenv('TWITTER_API_KEY')
    api_secret = os.getenv('TWITTER_API_SECRET')
    access_token = os.getenv('TWITTER_ACCESS_TOKEN')
    access_secret = os.getenv('TWITTER_ACCESS_TOKEN_SECRET')
    if not all([api_key, api_secret, access_token, access_secret]):
        print('[aviso] Sin credenciales de Twitter: tweet guardado en data/tweet_top5.txt')
        return False
    try:
        from requests_oauthlib import OAuth1
        import requests
    except ImportError:
        print('[aviso] requests-oauthlib no instalado: tweet guardado en archivo')
        return False
    auth = OAuth1(api_key, api_secret, access_token, access_secret)
    r = requests.post('https://api.twitter.com/2/tweets', auth=auth, json={'text': texto})
    if r.status_code in (200, 201):
        print('Tweet publicado:', r.json().get('data', {}).get('id'))
        return True
    print(f'[error] Twitter respondió {r.status_code}: {r.text[:300]}')
    return False


if __name__ == '__main__':
    main()
