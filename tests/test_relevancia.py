from relevancia import MIN_TEXTOS, es_espanol, filtrar_relevantes, menciona, suficientes


def test_apellido_con_tildes_cuenta_como_mencion():
    assert menciona('Ávalos marcó otra vez', 'Gabriel Ávalos', 'Olimpia')


def test_nombre_completo_cuenta_como_mencion():
    assert menciona('Gabriel Avalos fue figura', 'Gabriel Ávalos', 'Olimpia')


def test_texto_ajeno_no_menciona_al_jugador():
    assert not menciona('El clásico de la fecha es el domingo', 'Gabriel Ávalos', 'Olimpia')


def test_nombre_unico_exige_el_club():
    assert menciona('Mauricio marcó con Palmeiras', 'Mauricio', 'Palmeiras')
    assert not menciona('Mauricio Pochettino habló de la Selección', 'Mauricio', 'Palmeiras')


def test_apellido_igual_al_club_no_cuenta_solo():
    assert not menciona('Bahia ganó el partido', 'Matheus Bahia', 'Bahia')
    assert menciona('Matheus Bahia anotó', 'Matheus Bahia', 'Bahia')


def test_es_espanol_descarta_portugues_y_acepta_espanol():
    assert es_espanol('El jugador tiene muito talento e eu gosto dele') is False
    assert es_espanol('Qué buen partido de Juan, es muy bueno')


def test_es_espanol_neutro_se_conserva():
    assert es_espanol('Juan Perez 2-1 Olimpia')


def test_filtrar_relevantes_combina_mencion_e_idioma():
    textos = [
        'Gabriel Ávalos es un crack, muy buen partido',
        'Gabriel Ávalos tem muito talento, obrigado',
        'Partido de la fecha sin nombres propios',
    ]
    assert filtrar_relevantes(textos, 'Gabriel Ávalos', 'Olimpia') == [
        'Gabriel Ávalos es un crack, muy buen partido']


def test_suficientes_respeta_el_minimo():
    assert MIN_TEXTOS == 3
    assert not suficientes(['a', 'b'])
    assert suficientes(['a', 'b', 'c'])
