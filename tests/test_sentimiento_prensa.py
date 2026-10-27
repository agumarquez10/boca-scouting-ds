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
                        lambda nombre, club='', medios=None: [
                            'Juan Perez es un crack', 'Juan Perez tuvo una gran semana',
                            'Juan Perez falló el penal'])

    class FakeEngine:
        def puntuar_lote(self, textos):
            return [10.0, -10.0, 0.0]

    r = modulo.sentimiento_jugador_prensa('Juan Perez', 'Boca Juniors', engine=FakeEngine())
    assert r['ok'] and r['n_textos'] == 3 and r['valor'] == 0.0


def test_sentimiento_jugador_prensa_descarta_fuente_con_pocos_textos(monkeypatch):
    import sentimiento_jugadores_prensa as modulo

    monkeypatch.setattr(modulo, 'notas_prensa',
                        lambda nombre, club='', medios=None: [
                            'Juan Perez es un crack', 'Juan Perez tuvo una gran semana',
                            'Otro tema sin relacion el'])

    class FakeEngine:
        def puntuar_lote(self, textos):
            raise AssertionError('no debe puntuar con menos de 3 textos relevantes')

    r = modulo.sentimiento_jugador_prensa('Juan Perez', 'Boca Juniors', engine=FakeEngine())
    assert not r['ok'] and r['n_textos'] == 2


def test_parsear_rss_limpia_html_escapado_y_no_duplica_el_titular():
    rss = """<rss><channel><item>
      <title>Lapadula suena fuerte - Depor</title>
      <description>&lt;a href="https://news.google.com/x" target="_blank"&gt;Lapadula suena fuerte&lt;/a&gt;&amp;nbsp;&amp;nbsp;&lt;font color="#6f6f6f"&gt;Depor&lt;/font&gt;</description>
    </item></channel></rss>"""
    textos = _parsear_rss(rss)
    assert textos == ['Lapadula suena fuerte']
    assert not any('href' in t or 'http' in t for t in textos)


def test_sentimiento_jugador_prensa_sin_textos(monkeypatch):
    import sentimiento_jugadores_prensa as modulo

    monkeypatch.setattr(modulo, 'notas_prensa',
                        lambda nombre, club='', medios=None: [])
    r = modulo.sentimiento_jugador_prensa('X', 'Y')
    assert not r['ok'] and r['n_textos'] == 0
