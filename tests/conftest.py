import os
import sys

import pytest

SRC = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'src')
if SRC not in sys.path:
    sys.path.insert(0, SRC)


@pytest.fixture(autouse=True)
def sin_clave_youtube(monkeypatch):
    """Los tests nunca consultan YouTube de verdad: sin clave, la medicion se salta."""
    import sentimiento_jugadores_youtube as yt
    monkeypatch.setattr(yt, 'YOUTUBE_API_KEY', '')
