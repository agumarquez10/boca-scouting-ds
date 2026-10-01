"""
Configuracion de las ligas objetivo para el 11 ideal (Team of the Week) de FotMob.

Cada liga define los IDs de FotMob y las temporadas (con su formato exacto) que
FotMob usa en el colector historico legado. El radar semanal resuelve la
temporada actual en runtime para no fijar temporadas vencidas en la configuracion.
Si una liga no publica TOTW, se deja marcada con `skip=True`.
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
        'nombre': 'Ecuador',
        'fotmob_id': 246,
        'temporadas_totw': [],
        'skip': True,
        'razon_skip': 'Stand by: esperar a que FotMob publique el TOTW de la fecha',
    },
    {
        'nombre': 'Peru',
        'fotmob_id': 131,
        'temporadas_totw': [],
        'skip': False,
        'razon_skip': '',
    },
    {
        'nombre': 'Uruguay',
        'fotmob_id': 161,
        'temporadas_totw': [],
        'skip': True,
        'razon_skip': 'Stand by: FotMob no publica TOTW para Uruguay (endpoint rounds = null)',
    },
    {
        'nombre': 'Chile',
        'fotmob_id': 273,
        'temporadas_totw': [],
        'skip': False,
        'razon_skip': '',
    },
    {
        'nombre': 'Paraguay',
        'fotmob_id': 199,
        'temporadas_totw': [],
        'skip': False,
        'razon_skip': '',
    },
    {
        'nombre': 'USA (MLS)',
        'fotmob_id': 130,
        'temporadas_totw': ['2025'],
        'skip': True,
        'razon_skip': 'Quitada del radar a pedido del usuario (2026-09-30)',
    },
]


def ligas_activas():
    return [l for l in LIGAS_FOTMOB if not l.get('skip')]


def ligas_saltadas():
    return [l for l in LIGAS_FOTMOB if l.get('skip')]
