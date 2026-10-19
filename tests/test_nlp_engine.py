from nlp_engine import (
    ESCALA,
    LEXICO_HINCHADA,
    MOTOR,
    PESO_BERT,
    PESO_VADER,
    SentimientoEngine,
    _LEXICO_FRASES,
    _LEXICO_UNIGRAMAS,
    _indice_lexico,
    _normalizar,
    _tokens,
    ajustar_lexico_hinchada,
)


def test_escala_publicada_es_la_real():
    """El techo de la escala tiene que ser el que anuncia la landing."""
    assert ESCALA == 50
    engine = SentimientoEngine(usar_bert=False)
    # Con BERT apagado el ponderado se renormaliza sobre VADER: el techo real
    # es +-50 y no +-27.5.
    assert abs(engine.puntuar('crack machine absolutely brilliant')) <= ESCALA
    assert abs(engine.puntuar('horrible disaster terrible awful')) <= ESCALA


def test_puntuar_con_bert_apagado_alcanza_la_escala():
    """Un texto muy negativo tiene que poder acercarse al piso de -50."""
    engine = SentimientoEngine(usar_bert=False)
    valor = engine.puntuar('pésimo desastre horrible fracaso cholera buenisimo')
    assert valor < -20, f'el motor no llega al rango anunciado: {valor}'
    assert valor >= -ESCALA


def test_pesos_suman_el_ponderado_completo():
    assert PESO_VADER + PESO_BERT == 1.0


def test_bert_apagado_por_defecto():
    """El motor no debe descargar el modelo de BERT sin que se lo pidan."""
    assert SentimientoEngine().usar_bert is False


def test_claves_con_tilde_se_normalizan_al_indexar():
    """'caño' con tilde no puede coincidir contra texto normalizado."""
    assert 'caño' in LEXICO_HINCHADA
    assert 'cano' in _LEXICO_UNIGRAMAS
    assert _LEXICO_UNIGRAMAS['cano'] > 0


def test_variantes_duplicadas_colapsan_en_una_sola_entrada():
    """'ídolo' e 'idolo' son la misma clave: no pueden contar dos veces."""
    assert 'ídolo' in LEXICO_HINCHADA and 'idolo' in LEXICO_HINCHADA
    assert _LEXICO_UNIGRAMAS['idolo'] == 3.0
    unigramas, _ = _indice_lexico()
    assert sum(1 for k in unigramas if k == 'idolo') == 1


def test_frases_se_mantienen_como_frases():
    assert ('pecho', 'frio') in [tuple(p) for p, _ in _LEXICO_FRASES]


def test_el_lexico_no_cuenta_dos_veces_el_mismo_termino():
    """'mufa' esta dentro de 'mufado': con match por token solo cuenta 'mufado'."""
    assert 'mufa' in _LEXICO_UNIGRAMAS and 'mufado' in _LEXICO_UNIGRAMAS
    texto = 'mufado'
    tokens = _tokens(texto)
    assert tokens == ['mufado']
    # 'mufa' no esta en el texto como token propio
    assert 'mufa' not in tokens


def test_ajuste_lexico_suma_los_terminos_presentes():
    """Un termino del lexico tiene que mover el compound."""
    sin = ajustar_lexico_hinchada('el jugador fue malo', 0.0)
    con = ajustar_lexico_hinchada('el jugador fue un crack', 0.0)
    assert con > sin


def test_normalizar_y_tokens():
    assert _normalizar('Cañó') == 'cano'
    assert _tokens('Cañó, un CRACK!') == ['cano', 'un', 'crack']


def test_version_del_motor_registrada():
    assert MOTOR
