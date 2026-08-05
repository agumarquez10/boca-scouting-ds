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
