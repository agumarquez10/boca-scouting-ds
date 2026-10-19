import pandas as pd

from evaluar_sentimiento import cargar, clasificar, evaluar, main, metricas


def test_clasificar_respeta_el_umbral():
    assert clasificar([10, -10, 2, -2, 0], 5) == [1, -1, 0, 0, 0]


def test_metricas_predictor_perfecto():
    m = metricas([-1, 0, 1], [-30, 1, 30], 5)
    assert m['spearman'] == 1.0
    assert m['f1_macro_umbral_5'] == 1.0
    assert m['accuracy_umbral_5'] == 1.0


def test_metricas_sin_relacion_da_spearman_bajo():
    m = metricas([-1, 1, -1, 1, 0, 0], [5, 5, -5, -5, 0, 1], 5)
    assert abs(m['spearman']) < 0.5


def test_evaluar_separa_por_fuente():
    df = pd.DataFrame({
        'fuente': ['youtube', 'youtube', 'prensa', 'prensa'],
        'texto': ['a', 'b', 'c', 'd'],
        'etiqueta': [1, -1, 1, -1],
    })
    variantes = {'trucho': lambda t: {'a': 30, 'b': -30, 'c': -30, 'd': 30}[t]}
    r = evaluar(df, variantes, umbral=5)
    assert r['trucho']['todas']['spearman'] == 0.0
    # Con 2 textos por fuente la correlacion no tiene sentido: queda en None.
    assert r['trucho']['por_fuente']['youtube']['spearman'] is None
    assert r['trucho']['por_fuente']['prensa']['n'] == 2


def test_cargar_ignora_etiquetas_vacias_o_invalidas(tmp_path):
    pd.DataFrame({'id': ['0001', '0002', '0003'], 'fuente': ['prensa'] * 3,
                  'nombre': ['A'] * 3, 'club': ['B'] * 3,
                  'texto': ['uno uno uno', 'dos dos dos', 'tres tres tres']}).to_csv(
        tmp_path / 'muestra.csv', index=False, encoding='utf-8-sig')
    pd.DataFrame({'id': ['0001', '0002'], 'etiqueta': [1, 7]}).to_csv(
        tmp_path / 'etiquetas.csv', index=False, encoding='utf-8-sig')
    df = cargar(str(tmp_path))
    assert list(df['id']) == ['0001']


def test_main_sin_etiquetas_no_calcula_nada(tmp_path, monkeypatch, capsys):
    pd.DataFrame({'id': ['0001'], 'fuente': ['prensa'], 'nombre': ['A'], 'club': ['B'],
                  'texto': ['texto suficientemente largo']}).to_csv(
        tmp_path / 'muestra.csv', index=False, encoding='utf-8-sig')
    pd.DataFrame({'id': [], 'etiqueta': []}).to_csv(
        tmp_path / 'etiquetas.csv', index=False, encoding='utf-8-sig')
    monkeypatch.setattr('sys.argv', ['evaluar_sentimiento.py', '--directorio', str(tmp_path)])
    assert main() == 2
    assert 'No alcanza' in capsys.readouterr().out
    assert not (tmp_path / 'evaluacion.json').exists()


def test_main_sin_archivo_de_etiquetas_da_mensaje_no_error(tmp_path, monkeypatch, capsys):
    pd.DataFrame({'id': ['0001'], 'fuente': ['prensa'], 'nombre': ['A'], 'club': ['B'],
                  'texto': ['texto suficientemente largo']}).to_csv(
        tmp_path / 'muestra.csv', index=False, encoding='utf-8-sig')
    monkeypatch.setattr('sys.argv', ['evaluar_sentimiento.py', '--directorio', str(tmp_path)])
    assert main() == 2
    assert 'No alcanza' in capsys.readouterr().out
