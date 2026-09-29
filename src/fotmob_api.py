"""
Cliente FotMob (scraping) con cache en SQLite.

FotMob no expone API con key: la libreria `fotmob` pasa por su endpoint interno.
Para no repetir miles de llamadas (un `get_player` por candidato del TOTW),
cacheamos las respuestas en la tabla SQLite `api_cache` (clave con prefijo
`fotmob|` para no chocar con la cache de api_football).
"""

import asyncio
import json
import os
import sqlite3

CACHE_DB = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'data', 'boca_juniors.db'
)

_PREFIX = 'fotmob|'


def _con():
    con = sqlite3.connect(CACHE_DB)
    con.execute('''
        CREATE TABLE IF NOT EXISTS api_cache (
            clave TEXT PRIMARY KEY,
            payload TEXT NOT NULL,
            creado TEXT DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    con.commit()
    return con


def _get_cache(clave):
    try:
        con = _con()
        row = con.execute('SELECT payload FROM api_cache WHERE clave=?', (clave,)).fetchone()
        con.close()
        return json.loads(row[0]) if row else None
    except (sqlite3.Error, json.JSONDecodeError):
        return None


def _set_cache(clave, valor):
    try:
        con = _con()
        con.execute(
            'INSERT OR REPLACE INTO api_cache (clave, payload) VALUES (?, ?)',
            (clave, json.dumps(valor)),
        )
        con.commit()
        con.close()
    except (sqlite3.Error, TypeError):
        pass


class FotMobApi:
    """Wrapper con cache sobre la libreria async `fotmob.FotMob`."""

    def __init__(self, cache_db=CACHE_DB, loop=None):
        from fotmob import FotMob
        self._FotMob = FotMob
        self.cache_db = cache_db
        self._loop = loop or asyncio.new_event_loop()
        self._client = self._FotMob()
        self._reales = 0

    @staticmethod
    def _clave(tipo, *args):
        return _PREFIX + tipo + '|' + '|'.join(str(a) for a in args)

    _METODOS = {
        'rounds': 'totw_rounds',
        'totw': 'totw',
        'fixtures': 'get_league_fixtures',
        'current_season': 'get_league_current_season',
        'player': 'get_player',
        'team': 'get_team',
    }

    def _llamar(self, tipo, *args, force_refresh=False):
        if tipo not in self._METODOS:
            raise ValueError(f'tipo desconocido: {tipo}')
        clave = self._clave(tipo, *args)
        valor = None if force_refresh else _get_cache(clave)
        if valor is not None:
            return valor
        coro = getattr(self._client, self._METODOS[tipo])(*args)
        try:
            valor = self._loop.run_until_complete(coro)
        except RuntimeError:
            self._loop = asyncio.new_event_loop()
            self._client = self._FotMob()
            coro = getattr(self._client, self._METODOS[tipo])(*args)
            valor = self._loop.run_until_complete(coro)
        self._reales += 1
        if valor is not None:
            _set_cache(clave, valor)
        return valor

    def totw_rounds(self, league_id, season, force_refresh=False):
        return self._llamar('rounds', league_id, season, force_refresh=force_refresh)

    def totw(self, league_id, season, roundnum, force_refresh=False):
        return self._llamar('totw', league_id, season, roundnum, force_refresh=force_refresh)

    def fixtures(self, league_id, season, force_refresh=False):
        return self._llamar('fixtures', league_id, season, force_refresh=force_refresh)

    def temporada_actual(self, league_id, force_refresh=False):
        return self._llamar('current_season', league_id, force_refresh=force_refresh)

    def jugador(self, player_id, force_refresh=False):
        return self._llamar('player', player_id, force_refresh=force_refresh)

    def stats_torneo(self, player_id, season_id, force_refresh=False):
        """Stats de UN jugador en UN torneo (`season_id` tipo '0-0' del perfil).

        Se llama directo con requests porque el wrapper async de la libreria
        devuelve None para este endpoint. Cache con la misma clave por jugador
        y torneo; `force_refresh` la refresca semanalmente.
        """
        import requests

        clave = self._clave('stats', player_id, season_id)
        if not force_refresh:
            cached = _get_cache(clave)
            if cached is not None:
                return cached
        url = 'https://www.fotmob.com/api/data/playerStats'
        r = requests.get(url, params={
            'playerId': player_id, 'seasonId': season_id,
            'isFirstSeason': 'false',
        }, headers={'User-Agent': 'Mozilla/5.0'}, timeout=30)
        r.raise_for_status()
        valor = r.json()
        self._reales += 1
        if valor is not None:
            _set_cache(clave, valor)
        return valor

    def equipo(self, team_id, ccode3=''):
        """Devuelve el perfil de un equipo. `ccode3` opcional (si se conoce)."""
        return self._llamar('team', team_id, ccode3 or 'GBR')

    def close(self):
        """Cierra la sesion HTTP del cliente para liberar recursos."""
        try:
            self._loop.run_until_complete(self._client.close())
        except Exception:
            pass

    def reset_loop(self):
        self._loop = asyncio.new_event_loop()
        self._client = self._FotMob()
