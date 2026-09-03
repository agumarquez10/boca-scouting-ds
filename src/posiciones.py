import pandas as pd

GRUPOS_POSICION = {
    'Centre-Forward': 'Delantero',
    'Secondary Striker': 'Delantero',
    'Second Striker': 'Delantero',
    'Attack': 'Delantero',
    'Attacker': 'Delantero',
    'Forward': 'Delantero',
    'Left Winger': 'Extremo',
    'Right Winger': 'Extremo',
    'Attacking Midfield': 'Mediocampista_ofensivo',
    'Left Midfield': 'Mediocampista_ofensivo',
    'Right Midfield': 'Mediocampista_ofensivo',
    'Midfield': 'Mediocampista_ofensivo',
    'Midfielder': 'Mediocampista_ofensivo',
    'Central Midfield': 'Mediocampista_central',
    'Defensive Midfield': 'Mediocampista_central',
    'Left-Back': 'Lateral',
    'Right-Back': 'Lateral',
    'Centre-Back': 'Defensor_central',
    'Defender': 'Defensor_central',
    'Goalkeeper': 'Arquero',
}

DEFAULT_GRUPO = 'Arquero'

POSICIONES_OFENSIVAS = {
    'Attack', 'Attacker', 'Forward', 'Centre-Forward', 'Secondary Striker',
    'Second Striker', 'Left Winger', 'Right Winger', 'Attacking Midfield',
}

# Mapea el key de posicion de FotMob (positionDescription.strPos.key) a una
# etiqueta reconocida por GRUPOS_POSICION, para alimentar el PositionEncoder.
FOTMOB_KEY_ETIQUETA = {
    'keeper': 'Goalkeeper',
    'keeper_long': 'Goalkeeper',
    'goalkeeper': 'Goalkeeper',
    'rightback': 'Right-Back',
    'leftback': 'Left-Back',
    'centerback': 'Centre-Back',
    'centreback': 'Centre-Back',
    'right_wing_back': 'Right-Back',
    'left_wing_back': 'Left-Back',
    'rightwingback': 'Right-Back',
    'leftwingback': 'Left-Back',
    'defensive_midfielder': 'Defensive Midfield',
    'centerdefensivemidfielder': 'Defensive Midfield',
    'left_defensive_midfielder': 'Defensive Midfield',
    'right_defensive_midfielder': 'Defensive Midfield',
    'centralmidfielder': 'Central Midfield',
    'centercentralmidfielder': 'Central Midfield',
    'centermidfielder': 'Central Midfield',
    'central_midfielder': 'Central Midfield',
    'leftcentralmidfielder': 'Central Midfield',
    'rightcentralmidfielder': 'Central Midfield',
    'midfielder': 'Midfielder',
    'attacking_midfielder': 'Attacking Midfield',
    'centerattackingmidfielder': 'Attacking Midfield',
    'leftattackingmidfielder': 'Attacking Midfield',
    'rightattackingmidfielder': 'Attacking Midfield',
    'leftmidfielder': 'Left Midfield',
    'rightmidfielder': 'Right Midfield',
    'leftwinger': 'Left Winger',
    'rightwinger': 'Right Winger',
    'striker': 'Centre-Forward',
    'centerforward': 'Centre-Forward',
    'centreforward': 'Centre-Forward',
    'secondstriker': 'Second Striker',
    'second_striker': 'Second Striker',
    'forward': 'Forward',
    'attacker': 'Forward',
    'defender': 'Defender',
}


def posicion_fotmob_a_grupo(key):
    """Traduce un key de posicion de FotMob al grupo canónico del modelo."""
    if not isinstance(key, str):
        return DEFAULT_GRUPO
    etiqueta = FOTMOB_KEY_ETIQUETA.get(key) or FOTMOB_KEY_ETIQUETA.get(key.lower())
    if etiqueta is None:
        return DEFAULT_GRUPO
    return GRUPOS_POSICION.get(etiqueta, DEFAULT_GRUPO)


def es_perfil_ofensivo_fotmob(key):
    """True si el key de posicion de FotMob es de perfil ofensivo."""
    if not isinstance(key, str):
        return False
    etiqueta = FOTMOB_KEY_ETIQUETA.get(key) or FOTMOB_KEY_ETIQUETA.get(key.lower())
    if etiqueta is None:
        return False
    return etiqueta in POSICIONES_OFENSIVAS


def posicion_desde_layout(x, y):
    """Deriva una etiqueta de posicion aproximada desde el verticalLayout del TOTW.

    Solo se usa como fallback cuando FotMob no reporta primaryPosition.
    y = fila del campo (0 arriba? 1 abajo), x = costado.
    En FotMob layout: y bajo = arquero/fondo, y alto = delantera.
    """
    y = float(y if y is not None else 0.5)
    x = float(x if x is not None else 0.5)
    if y <= 0.2:
        return 'Goalkeeper'
    if y <= 0.45:
        if x < 0.3 or x > 0.7:
            return 'Right-Back' if x >= 0.5 else 'Left-Back'
        return 'Centre-Back'
    if y <= 0.7:
        if x < 0.3 or x > 0.7:
            return 'Midfielder'
        return 'Central Midfield'
    if x < 0.3 or x > 0.7:
        return 'Right Winger' if x >= 0.5 else 'Left Winger'
    return 'Centre-Forward'


def agrupar_posicion(pos):
    if isinstance(pos, str) and pos in GRUPOS_POSICION:
        return GRUPOS_POSICION[pos]
    return DEFAULT_GRUPO


def es_perfil_ofensivo(pos):
    """Misma semantica que merge_datasets.perfil_ofensivo pero acepta
    posiciones genericas de la API (Attacker/Midfielder/Forward/...).
    Los 'Midfielder' genericos se tratan como no-ofensivos (la mayoria son
    centrales/defensivos y el train asi lo codifica)."""
    return isinstance(pos, str) and pos in POSICIONES_OFENSIVAS


class PositionEncoder:
    """Aplica one-hot sobre el grupo de posicion con las mismas columnas que el train.

    Permite persistir el encoder (joblib) y usarlo desde scripts, evitando
    la funcion __main__ que rompia agrupar_posicion.pkl.
    """

    def __init__(self, columnas):
        self.columnas = sorted(columnas)

    def transform(self, posiciones):
        grupos = pd.Series(list(posiciones)).map(GRUPOS_POSICION).fillna(DEFAULT_GRUPO)
        dummies = pd.get_dummies(grupos, prefix='pos').astype(int)
        for c in self.columnas:
            if c not in dummies.columns:
                dummies[c] = 0
        return dummies[self.columnas]
