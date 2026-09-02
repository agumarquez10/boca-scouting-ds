from dotenv import load_dotenv
import os
load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'secrets', '.env'))
from api_football import ApiFootball
api = ApiFootball(os.getenv('API_KEY'))

for season in [2026, 2025]:
    for lid, nombre in [(128, 'ARG'), (140, 'ESP'), (71, 'BRA'), (268, 'URU'), (262, 'MEX')]:
        data = api.get('players/topscorers', {'league': lid, 'season': season})
        n = data.get('results', 0)
        errs = data.get('errors', [])
        resp = data.get('response', [])
        print(f'{nombre} {season}: results={n} len_resp={len(resp)} errors={errs}')
        if resp:
            p = resp[0].get('player', {})
            print(f'  top: {p.get("name")} (id={p.get("id")})')
