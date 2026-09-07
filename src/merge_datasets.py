import pandas as pd
import numpy as np
import re
import os

# Ruta relativa al proyecto (funciona desde cualquier lugar)
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(SCRIPT_DIR, '..', 'data')

# Load both datasets
df_modern = pd.read_csv(os.path.join(DATA_DIR, 'adn_boca_real.csv'), encoding='utf-8-sig')
df_hist = pd.read_csv(os.path.join(DATA_DIR, 'adn_boca_historical_raw.csv'), encoding='utf-8-sig')

print(f'Modern (2010-2024): {len(df_modern)} records')
print(f'Historical (2000-2009): {len(df_hist)} records')

# Fix names that have shortname concatenated
# Patterns observed in source data:
#   "Carlos TevezC. Tevez"        -> full name + shortname pegado
#   "G. Barros SchelottoG. Barros" -> apellidos pegados al nombre completo
#   "IarleyIarley"                -> nombre duplicado exacto
#   "Pol FernandezPol Fernandez"  -> nombre y apellido duplicados exactos
# Solo cortamos si TODAS las palabras del shortname ya estan dentro del
# nombre completo, para no romper segundos nombres legitimos como "Juan R."
SHORTNAME_RE = re.compile(r'^(.*?)\s*([A-ZÀ-ÿ]\.\s*[A-Za-zÀ-ÿ]+(?:\s+[A-Za-zÀ-ÿ]+)*)$')


def clean_name(raw):
    if not isinstance(raw, str):
        return raw
    s = raw.strip()
    if not s:
        return s

    # Patron 1: shortname pegado al final: "Nombre CompletoX. Apellido Ap2"
    m = SHORTNAME_RE.match(s)
    if m:
        full = m.group(1).strip()
        short_surname = m.group(2).split('.', 1)[1].strip()
        short_words = short_surname.split()
        words_full = set(full.lower().split())
        if len(full) >= 3 and short_words and all(w.lower() in words_full for w in short_words):
            return full

    # Patron 2: duplicacion exacta del nombre completo ("IarleyIarley",
    # "Pol FernandezPol Fernandez", "BaianoBaiano").
    for split in range(len(s) // 2, 2, -1):
        if s[:split] == s[split:2 * split]:
            return s[:split]

    return s


# Test the cleaning
test_names = df_hist['nombre'].unique()[:10]
print('\nName cleaning test:')
for n in test_names:
    cleaned = clean_name(n)
    if n != cleaned:
        print(f'  {n:50s} -> {cleaned}')

# Apply cleaning
df_hist['nombre'] = df_hist['nombre'].apply(clean_name)
df_modern['nombre'] = df_modern['nombre'].apply(clean_name)

# Check for duplicates between datasets
combined = pd.concat([df_hist, df_modern], ignore_index=True)
dupes = combined.duplicated(subset=['nombre', 'temporada', 'posicion'], keep='last')
print(f'\nDuplicates between datasets: {dupes.sum()}')

# Keep the modern version (more reliable) where there's overlap
combined = combined[~dupes].copy()

# Clean encoding issues. Los datos vienen con doble-encoding (mojibake):
# el string actual es texto latin-1 que fue mal decodificado.
# Probamos revertir de forma segura y no rompemos si ya esta bien.
def fix_encoding(name):
    if not isinstance(name, str):
        return name
    try:
        fixed = name.encode('latin-1').decode('utf-8').strip()
        # solo aceptamos si no se introdujeron caracteres de reemplazo
        return fixed if '\ufffd' not in fixed else name.strip()
    except (UnicodeDecodeError, UnicodeEncodeError):
        return name.strip()

combined['nombre'] = combined['nombre'].apply(fix_encoding)

# ============================================================
# CORRECCION DE POSICIONES (errores conocidos de la fuente)
# ============================================================
CORRECCIONES_POSICION = {
    'Cristian Pavón': 'Right Winger',
}
mask_pos = combined['nombre'].isin(CORRECCIONES_POSICION)
n_pos = mask_pos.sum()
combined.loc[mask_pos, 'posicion'] = combined.loc[mask_pos, 'nombre'].map(CORRECCIONES_POSICION)
if n_pos:
    print(f'\nPosiciones corregidas ({n_pos} registros):')
    for k, v in CORRECCIONES_POSICION.items():
        print(f'  {k}: -> {v}')

# ============================================================
# CORRECCIÓN 1: Rating original de la API (NO recalcular)
# Usamos el rating que viene de la fuente de datos.
# Si no existe, lo calculamos como fallback pero lo marcamos.
# ============================================================
if 'rating' not in combined.columns or combined['rating'].isna().all():
    print("\n⚠️  Rating no disponible en datos originales, calculando fallback...")
    def compute_rating_fallback(row):
        gpg = row['goles'] / max(row['partidos'], 1)
        apg = row['asistencias'] / max(row['partidos'], 1)
        mp = min(row['partidos'] / 38, 1.0)
        return min(round(6.0 + gpg * 3.0 + apg * 2.0 + mp * 0.5, 1), 9.5)
    combined['rating'] = combined.apply(compute_rating_fallback, axis=1)
else:
    print(f"\n[OK] Rating original preserved (range: {combined['rating'].min():.1f} - {combined['rating'].max():.1f})")

# ============================================================
# CORRECCIÓN 2: Etiqueta más robusta
# Definición: jugador con buen rendimiento整体 Y contribución ofensiva clara
# Usamos el rating original + goles+asistencias como proxy
# ============================================================
combined['contribucion_ofensiva'] = combined['goles'] + combined['asistencias']

# Definición robusta: rating >= 7.0 Y al menos 3 goles+asistencias en la temporada
# (más exigente que >2 para reducir falsos positivos)
combined['etiqueta'] = (
    (combined['rating'] >= 7.0) & 
    (combined['contribucion_ofensiva'] >= 3)
).astype(int)

# ============================================================
# CORRECCIÓN 5: Etiqueta manual del jugador (juicio humano)
# Si etiquetas_manuales.csv tiene un valor para el jugador, esa
# etiqueta TIENE PRIORIDAD sobre la fórmula (aplica a todas sus
# temporadas). Celda vacía = coincidís con la fórmula.
# ============================================================
etq_path = os.path.join(DATA_DIR, 'etiquetas_manuales.csv')
if os.path.exists(etq_path):
    manual = pd.read_csv(etq_path, encoding='utf-8-sig')
    manual = manual.dropna(subset=['etiqueta_manual'])
    manual = manual.assign(etiqueta_manual=manual['etiqueta_manual'].astype(int))
    override = manual.set_index('jugador')['etiqueta_manual']
    mapeado = combined['nombre'].map(override)
    n_flips = mapeado.notna().sum()
    if n_flips > 0:
        combined['etiqueta'] = mapeado.fillna(combined['etiqueta']).astype(int)
        print(f'\nEtiqueta manual aplicada a {n_flips} registros ({manual["jugador"].nunique()} jugadores)')
    else:
        print('\netiquetas_manuales.csv leido pero sin valores en etiqueta_manual')
else:
    print('\netiquetas_manuales.csv no encontrado, se usa solo la fórmula')

print(f'\nEtiqueta distribution (nueva definición):')
print(combined['etiqueta'].value_counts().to_string())

# Sort
combined = combined.sort_values(['temporada', 'rating'], ascending=[False, False]).reset_index(drop=True)

# Select final columns (SIN rating en features para evitar leakage)
final_cols = ['nombre', 'temporada', 'posicion', 'edad', 'partidos',
              'goles', 'asistencias', 'pases_precisos', 'rating', 'etiqueta']
combined = combined[final_cols].copy()

# Show key players
print(f'\n=== FINAL DATASET: {len(combined)} records ===')
print(f'Period: {int(combined["temporada"].min())} - {int(combined["temporada"].max())}')
print(f'Etiqueta distribution:\n{combined["etiqueta"].value_counts().to_string()}')
print(f'\n--- Key historical players ---')
key_players = ['Palacio', 'Barros Schelotto', 'Battaglia', 'Ibarra', 'Morel Rodriguez',
               'Tevez', 'Riquelme', 'Gago', 'Delgado', 'Clemente Rodriguez']
for name_search in key_players:
    found = combined[combined['nombre'].str.contains(name_search, case=False, na=False)]
    if not found.empty:
        print(f'\n{name_search}:')
        for _, r in found.iterrows():
            print(f'  {int(r["temporada"])} | {r["posicion"]:20s} | g={int(r["goles"]):2d} | a={int(r["asistencias"]):2d} | rt={r["rating"]} | et={int(r["etiqueta"])}')

# Save final dataset
combined.to_csv(os.path.join(DATA_DIR, 'adn_boca_real.csv'), index=False, encoding='utf-8-sig')
print(f'\nSaved to adn_boca_real.csv')

# ============================================================
# CORRECCIÓN 3: Features derivadas SIN data leakage
# NO incluir rating ni variables derivadas del rating
# ============================================================
df_exp = combined.copy()

# Recrear contribucion_ofensiva en df_exp (no estaba en final_cols)
df_exp['contribucion_ofensiva'] = df_exp['goles'] + df_exp['asistencias']

# --- Features de tasa (NO derivadas del rating) ---
df_exp['goles_por_partido'] = (df_exp['goles'] / df_exp['partidos'].replace(0, np.nan)).fillna(0)
df_exp['asist_por_partido'] = (df_exp['asistencias'] / df_exp['partidos'].replace(0, np.nan)).fillna(0)
df_exp['contribucion_gol'] = ((df_exp['goles'] + df_exp['asistencias']) / df_exp['partidos'].replace(0, np.nan)).fillna(0)

# --- CORRECCIÓN: Experiencia real ---
# Contamos cuántas temporadas distintas tiene cada jugador en el dataset
seasons_per_player = combined.groupby('nombre')['temporada'].nunique().reset_index()
seasons_per_player.columns = ['nombre', 'temporadas_en_dataset']
df_exp = df_exp.merge(seasons_per_player, on='nombre', how='left')

# Edad del jugador en su primer registro en el dataset (proxy de edad debut)
primera_temp = combined.groupby('nombre')['temporada'].min().reset_index()
primera_temp.columns = ['nombre', 'primera_temporada']
df_exp = df_exp.merge(primera_temp, on='nombre', how='left')
df_exp['edad_primer_registro'] = df_exp['edad'] - (df_exp['temporada'] - df_exp['primera_temporada'])

# Experiencia = temporadas activas en nuestro dataset (proxy de trayectoria)
df_exp['experiencia'] = df_exp['temporadas_en_dataset']

# --- Otras features útiles ---
df_exp['promedio_goles_por_temporada'] = df_exp['goles'] / df_exp['experiencia'].replace(0, 1)
df_exp['promedio_asistencias_por_temporada'] = df_exp['asistencias'] / df_exp['experiencia'].replace(0, 1)
df_exp['proporcion_goles'] = (df_exp['goles'] / df_exp['contribucion_ofensiva'].replace(0, 1)).fillna(0)

# --- Feature categórica: perfil ofensivo ---
df_exp['perfil_ofensivo'] = (df_exp['posicion'].isin([
    'Attacking Midfield', 'Left Winger', 'Right Winger',
    'Centre-Forward', 'Secondary Striker'
])).astype(int)

# --- Feature: participación en el equipo ---
# Partidos jugados como proporción de una temporada completa (38 partidos)
df_exp['partidos_por_temporada'] = df_exp['partidos'] / df_exp['experiencia'].replace(0, 1)

# ============================================================
# CORRECCIÓN 4: Guardar dataset de features SIN rating ni leakage
# Se excluyen:
#   - rating (prohibido por regla del proyecto)
#   - goles, asistencias y derivados (goles_por_partido,
#     contribucion_gol, promedio_*_por_temporada, proporcion_goles):
#     la etiqueta usa (goles+asistencias>=3), asi que estas columnas
#     serian copia directa del umbral (leakage indirecto).
#   - experiencia (== temporadas_en_dataset, colinealidad perfecta)
# ============================================================
feature_cols = ['nombre', 'temporada', 'posicion', 'edad', 'partidos',
                'pases_precisos',
                'etiqueta',  # target
                'edad_primer_registro', 'primera_temporada',
                'temporadas_en_dataset',
                'perfil_ofensivo',
                'partidos_por_temporada']
df_exp = df_exp[feature_cols].copy()

df_exp.to_csv(os.path.join(DATA_DIR, 'adn_boca_real_features.csv'), index=False, encoding='utf-8-sig')
print(f'Saved features to adn_boca_real_features.csv')
print(f'Features: {[c for c in feature_cols if c not in ["nombre","temporada","etiqueta"]]}')

# File sizes
for f in ['adn_boca_real.csv', 'adn_boca_real_features.csv']:
    size = os.path.getsize(os.path.join(DATA_DIR, f))
    print(f'{f}: {size:,} bytes')
