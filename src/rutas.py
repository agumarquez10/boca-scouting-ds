import os

_MARCA_RAIZ = 'AGENTS.md'


def raiz_repo(partida=None):
    """Devuelve la raiz del repo caminando hacia arriba desde partida (o el CWD).

    Independiente del directorio de trabajo: los notebooks se ejecutan desde
    cualquier carpeta y siempre resuelven data/outputs/models/secrets del repo.
    """
    actual = os.path.abspath(partida or os.getcwd())
    while os.path.dirname(actual) != actual:
        if os.path.exists(os.path.join(actual, _MARCA_RAIZ)):
            return actual
        actual = os.path.dirname(actual)
    raise RuntimeError(f'raiz del repo no encontrada (falta {_MARCA_RAIZ} hacia arriba)')


def dir_src():
    return os.path.join(raiz_repo(), 'src')


def dir_datos():
    return os.path.join(raiz_repo(), 'data')


def dir_outputs():
    return os.path.join(raiz_repo(), 'outputs')


def dir_models():
    return os.path.join(raiz_repo(), 'models')


def dir_secrets():
    return os.path.join(raiz_repo(), 'secrets')
