"""
Configuracion de las ligas objetivo para el 11 ideal (Team of the Week) de FotMob.

Cada liga define los IDs de FotMob y las temporadas (con su formato exacto) que
FotMob usa en el endpoint de TOTW. Las temporadas se eligen cercanas a la
temporada actual de scouting (2024). Si una liga no publica TOTW (Uruguay),
se deja marcada con `skip=True` para avisarle al usuario y continuar.
"""

LIGAS_FOTMOB = [
    {
        'nombre': 'Argentina',
        'fotmob_id': 112,
        'temporadas_totw': ['2024'],
        'skip': False,
        'razon_skip': '',
    },
    {
        'nombre': 'Brasil',
        'fotmob_id': 268,
        'temporadas_totw': ['2024'],
        'skip': False,
        'razon_skip': '',
    },
    {
        'nombre': 'Mexico',
        'fotmob_id': 230,
        'temporadas_totw': ['2024/2025 - Apertura', '2024/2025 - Clausura'],
        'skip': False,
        'razon_skip': '',
    },
    {
        'nombre': 'USA (MLS)',
        'fotmob_id': 130,
        'temporadas_totw': ['2025'],
        'skip': False,
        'razon_skip': '',
    },
]


def ligas_activas():
    return [l for l in LIGAS_FOTMOB if not l.get('skip')]


def ligas_saltadas():
    return [l for l in LIGAS_FOTMOB if l.get('skip')]
