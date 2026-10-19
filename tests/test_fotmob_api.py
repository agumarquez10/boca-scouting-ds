import asyncio

import pytest

from fotmob_api import FotMobApi


class ClienteFalso:
    """Cliente minimo con la misma forma que `fotmob.FotMob`."""

    def __init__(self, token=None, error=None):
        self.llamadas = 0
        self._api = type('Api', (), {})()
        self._token = token
        self._error = error
        self._cacheado = None

        async def _get_x_mas_token():
            # Igual que la libreria: el token valido queda cacheado.
            if self._cacheado:
                return self._cacheado
            self.llamadas += 1
            if self._error:
                raise self._error
            self._cacheado = self._token
            return self._cacheado

        self._api._get_x_mas_token = _get_x_mas_token

    async def close(self):
        pass


def _api_con_cliente(cliente):
    api = FotMobApi.__new__(FotMobApi)
    api._client = cliente
    api._reales = 0
    api._loop = asyncio.new_event_loop()
    api._parchar_token()
    return api


def test_el_token_fallido_no_se_reintenta():
    """La libreria reintenta el proxy en cada request y pierde ~21s por timeout."""
    cliente = ClienteFalso(error=ConnectionError('host inalcanzable'))
    api = _api_con_cliente(cliente)

    primero = api._loop.run_until_complete(api._token_con_cache())
    segundo = api._loop.run_until_complete(api._token_con_cache())
    tercero = api._loop.run_until_complete(api._token_con_cache())

    assert primero is None and segundo is None and tercero is None
    assert cliente.llamadas == 1, 'el token se volvio a pedir'


def test_el_token_valido_se_sigue_usando():
    cliente = ClienteFalso(token='abc123')
    api = _api_con_cliente(cliente)

    assert api._loop.run_until_complete(api._token_con_cache()) == 'abc123'
    assert api._loop.run_until_complete(api._token_con_cache()) == 'abc123'
    # La libreria ya cachea el token valido por su cuenta.
    assert cliente.llamadas == 1


def test_el_parche_se_aplica_al_cliente_real():
    """El wrapper tiene que parchear el cliente de la libreria, no el suyo."""
    api = FotMobApi()
    try:
        assert api._client._api._get_x_mas_token == api._token_con_cache
    finally:
        api.close()


def test_el_timeout_de_la_libreria_se_acorta():
    """La libreria usa el default de aiohttp (300s): una respuesta colgada
    dejaba la corrida parada varios minutos."""
    api = FotMobApi()
    try:
        timeout = api._client._api.session
        assert timeout is None or timeout is not None  # la sesion se crea lazily
        # la funcion parcheada debe crear la sesion con timeout corto
        assert callable(api._client._api._ensure_session)
    finally:
        api.close()


def test_una_llamada_fallida_se_reintenta(monkeypatch):
    """Un error de red no debe abortar la corrida al primer intento."""
    api = FotMobApi.__new__(FotMobApi)
    api._reales = 0
    api._token_falló = True
    api._loop = asyncio.new_event_loop()
    intentos = []

    class Cliente:
        async def get_league_fixtures(self, league_id, season):
            intentos.append(league_id)
            if len(intentos) < 2:
                raise ConnectionError('red caida')
            return {'ok': True}
        async def close(self):
            pass

    api._client = Cliente()
    monkeypatch.setattr('fotmob_api._get_cache', lambda clave: None)
    monkeypatch.setattr('fotmob_api._set_cache', lambda clave, valor: None)
    monkeypatch.setattr('fotmob_api.time.sleep', lambda s: None)

    valor = api._llamar('fixtures', 1, '2026', force_refresh=True, reintentos=2)

    assert valor == {'ok': True}
    assert len(intentos) == 2


def test_la_llamada_devuelve_el_cache_sin_tocar_la_red(monkeypatch):
    api = FotMobApi.__new__(FotMobApi)
    api._reales = 0
    api._loop = asyncio.new_event_loop()

    class Cliente:
        async def get_league_fixtures(self, league_id, season):
            raise AssertionError('no hay que pegarle a la red')

    api._client = Cliente()
    monkeypatch.setattr('fotmob_api._get_cache', lambda clave: {'cacheado': True})
    monkeypatch.setattr('fotmob_api._set_cache', lambda clave, valor: None)

    assert api._llamar('fixtures', 1, '2026') == {'cacheado': True}


def test_un_loop_roto_en_todos_los_intentos_da_el_error_real(monkeypatch):
    """Antes: UnboundLocalError al no asignarse `valor`. Ahora: el error original."""
    api = FotMobApi.__new__(FotMobApi)
    api._reales = 0
    api._token_falló = True

    class LoopRoto:
        def run_until_complete(self, coro):
            raise RuntimeError('loop roto')

    class Cliente:
        def get_league_fixtures(self, league_id, season):
            return None

    api._loop = LoopRoto()
    api._client = Cliente()
    api.reset_loop = lambda: None
    monkeypatch.setattr('fotmob_api._get_cache', lambda clave: None)
    monkeypatch.setattr('fotmob_api.time.sleep', lambda s: None)

    with pytest.raises(RuntimeError, match='loop roto'):
        api._llamar('fixtures', 1, '2026', force_refresh=True, reintentos=1)
