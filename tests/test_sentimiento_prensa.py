from sentimiento_jugadores_prensa import (
    _dominios,
    _es_basura,
    _filtro_fuente,
    _parsear_rss,
    _url_prensa,
    sentimiento_jugador_prensa,
)


HTML = """<rss><channel>
<title>Boca busca a Juan Perez - Ole</title>
<item>
  <title>Juan Perez suena fuerte - TyC Sports</title>
  <description>&lt;a&gt;El crack llegaria libre&lt;/a&gt;</description>
</item>
<item><title>Google Noticias</title><description></description></item>
</channel></rss>"""


def test_dominios_acepta_dicts_y_strings():
    assert _dominios([{'dominio': 'a.com'}, 'b.com']) == ['a.com', 'b.com']


def test_filtro_fuente_quita_sufijo():
    assert _filtro_fuente('Juan Perez suena fuerte - TyC Sports') == 'Juan Perez suena fuerte'


def test_es_basura():
    assert _es_basura('Google Noticias')
    assert _es_basura('site:ole.com.ar')
    assert not _es_basura('Juan Perez suena fuerte')


def test_parsear_rss_extrae_y_filtra():
    textos = _parsear_rss(HTML)
    assert 'Juan Perez suena fuerte' in textos
    assert 'Boca busca a Juan Perez' in textos
    assert not any('Google Noticias' in t for t in textos)


def test_url_prensa_incluye_sites():
    url = _url_prensa('Juan Perez', 'Boca', ['ole.com.ar', 'tycsports.com'])
    assert 'site%3Aole.com.ar' in url
    assert 'site%3Atycsports.com' in url
    assert 'Juan%20Perez' in url


def test_sentimiento_jugador_prensa_promedia(monkeypatch):
    import sentimiento_jugadores_prensa as modulo

    monkeypatch.setattr(modulo, 'notas_prensa',
                        lambda nombre, club='', medios=None: ['crack', 'pecho frio'])

    class FakeEngine:
        def puntuar_lote(self, textos):
            return [10.0, -10.0]

    r = modulo.sentimiento_jugador_prensa('X', 'Y', engine=FakeEngine())
    assert r['ok'] and r['n_notas'] == 2 and r['valor'] == 0.0


def test_sentimiento_jugador_prensa_sin_notas(monkeypatch):
    import sentimiento_jugadores_prensa as modulo

    monkeypatch.setattr(modulo, 'notas_prensa',
                        lambda nombre, club='', medios=None: [])
    r = modulo.sentimiento_jugador_prensa('X', 'Y')
    assert not r['ok'] and r['n_notas'] == 0
