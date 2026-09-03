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
    {
        'nombre': 'Turquia',
        'fotmob_id': 71,
        'temporadas_totw': ['2024/2025'],
        'skip': True,
        'razon_skip': 'Fuera de mercado: se buscan candidatos solo de ligas de America.',
    },
    {
        'nombre': 'Espana - LaLiga',
        'fotmob_id': 87,
        'temporadas_totw': ['2024/2025'],
        'skip': True,
        'razon_skip': 'Fuera de mercado por costos: Boca no puede competir por jugadores de LaLiga.',
    },
    {
        'nombre': 'Espana - Segunda (LaLiga2)',
        'fotmob_id': 140,
        'temporadas_totw': ['2024/2025'],
        'skip': True,
        'razon_skip': 'Fuera de mercado por costos: la liga queda fuera por criterio de mercado.',
    },
    {
        'nombre': 'Uruguay',
        'fotmob_id': 161,
        'temporadas_totw': ['2024', '2025'],
        'skip': True,
        'razon_skip': 'FotMob no publica Team of the Week para esta liga.',
    },
]


def ligas_activas():
    return [l for l in LIGAS_FOTMOB if not l.get('skip')]


def ligas_saltadas():
    return [l for l in LIGAS_FOTMOB if l.get('skip')]
