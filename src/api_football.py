import json
import os
import sqlite3
import time

import requests

BASE_URL = 'https://v3.football.api-sports.io'
DEFAULT_DB = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'data', 'boca_juniors.db'
)


class ApiFootball:
    """Cliente de api-sports football v3 con cache en SQLite.

    El plan Free limita a ~100 requests/dia. Cachea respuestas en la tabla
    `api_cache` para no gastar cuota repitiendo consultas identicas.
    """

    _TIMEOUT = 30

    def __init__(self, api_key, cache_db=DEFAULT_DB):
        if not api_key:
            raise ValueError('API_KEY requerida (secrets/.env)')
        self.api_key = api_key
        self.session = requests.Session()
        self.session.headers.update({'x-apisports-key': api_key})
        self.cache_db = cache_db
        self._nueva_calls = 0
        self._init_cache()

    def _init_cache(self):
        con = sqlite3.connect(self.cache_db)
        con.execute('''
            CREATE TABLE IF NOT EXISTS api_cache (
                clave TEXT PRIMARY KEY,
                payload TEXT NOT NULL,
                creado TEXT DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        con.commit()
        con.close()

    def _clave(self, endpoint, params):
        qs = '&'.join(f'{k}={v}' for k, v in sorted(params.items()))
        return f'{endpoint}|{qs}'

    def _get_cache(self, clave):
        try:
            con = sqlite3.connect(self.cache_db)
            row = con.execute('SELECT payload FROM api_cache WHERE clave=?', (clave,)).fetchone()
            con.close()
            return row[0] if row else None
        except sqlite3.Error:
            return None

    def _set_cache(self, clave, payload):
        try:
            con = sqlite3.connect(self.cache_db)
            con.execute(
                'INSERT OR REPLACE INTO api_cache (clave, payload) VALUES (?, ?)',
                (clave, payload),
            )
            con.commit()
            con.close()
        except sqlite3.Error:
            pass

    def get(self, endpoint, params=None, use_cache=True):
        """GET a la API. Devuelve el dict completo de la respuesta JSON."""
        params = params or {}
        clave = self._clave(endpoint, params)
        if use_cache:
            cached = self._get_cache(clave)
            if cached is not None:
                return json.loads(cached)
        for intento in range(3):
            try:
                r = self.session.get(f'{BASE_URL}/{endpoint}', params=params, timeout=self._TIMEOUT)
                if r.status_code == 429:
                    time.sleep(12)
                    continue
                r.raise_for_status()
                break
            except requests.exceptions.RequestException:
                if intento == 2:
                    raise
                time.sleep(8)
        time.sleep(8)
        data = r.json()
        self._nueva_calls += 1
        if use_cache:
            self._set_cache(clave, json.dumps(data))
        return data

    def response(self, endpoint, params=None, use_cache=True):
        """Devuelve la lista `response` del JSON (con manejo de paginacion)."""
        data = self.get(endpoint, params, use_cache)
        return data.get('response', [])

    def status(self):
        r = self.session.get(f'{BASE_URL}/status', timeout=self._TIMEOUT)
        return r.json().get('response', {}).get('requests', {})

    # ---------------------------------------------------------------
    # Endpoints de alto nivel
    # ---------------------------------------------------------------

    def resolver_ligas(self, pais):
        """IDs de ligas de un pais (solo tipo 'League')."""
        data = self.get('leagues', {'country': pais if isinstance(pais, str) else pais})
        ligas = []
        for item in data.get('response', []):
            l = item['league']
            if l.get('type') == 'League':
                ligas.append({'id': l['id'], 'name': l['name']})
        return ligas

    def top_scorers(self, league_id, season):
        data = self.get('players/topscorers', {'league': league_id, 'season': season})
        return data.get('response', [])

    def top_assists(self, league_id, season):
        data = self.get('players/topassists', {'league': league_id, 'season': season})
        return data.get('response', [])

    def stats_jugador(self, player_id, season):
        data = self.get('players', {'id': player_id, 'season': season})
        return data.get('response', [])

    def standings(self, league_id, season):
        data = self.get('standings', {'league': league_id, 'season': season})
        resp = data.get('response', [])
        if not resp:
            return []
        return resp[0].get('league', {}).get('standings', [])
