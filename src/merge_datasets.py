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
def clean_name(raw):
    if not isinstance(raw, str):
        return raw
    # Pattern: "Name SurnameX. SurnamePosition" or similar
    # First try: find the short name pattern before the position
    # The typical Transfermarkt format is: "Full NameF. NamePosition"
    # We want just "Full Name"
    
    # Remove the duplicated short name suffix
    # Pattern: after the full name, there's a capital letter + period + space + capital letter + text
    # e.g., "Carlos TevezC. TevezCentre-Forward" -> "Carlos Tevez"
    m = re.match(r'^([A-Za-zÀ-ÿ\s.]+?)(?:[A-Z]\.\s*[A-Za-zÀ-ÿ]+)+', raw)
    if m:
        return m.group(1).strip()
    
    # Simpler: take everything before the first short name pattern
    # A short name is like "C. Tevez" or "J. Riquelme"  
    m = re.match(r'^(.+?)\s+[A-Z]\.\s*[A-Z][a-z]+', raw)
    if m:
        return m.group(1).strip()
    
    return raw.strip()


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

# Clean encoding issues by encoding to latin-1 and decoding from utf-8
def fix_encoding(name):
    try:
        return name.encode('latin-1').decode('utf-8').strip()
    except:
        return name.strip()

combined['nombre'] = combined['nombre'].apply(fix_encoding)

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
df_exp['pases_norm'] = df_exp['pases_precisos'] / 90

# --- Feature categórica: perfil ofensivo ---
df_exp['perfil_ofensivo'] = (df_exp['posicion'].isin([
    'Attacking Midfield', 'Left Winger', 'Right Winger',
    'Centre-Forward', 'Secondary Striker'
])).astype(int)

# --- Feature: participación en el equipo ---
# Partidos jugados como proporción de una temporada completa (38 partidos)
df_exp['partidos_por_temporada'] = df_exp['partidos'] / df_exp['experiencia'].replace(0, 1)

# ============================================================
# CORRECCIÓN 4: Guardar dataset de features SIN rating
# Solo features que NO son derivadas del rating
# ============================================================
feature_cols = ['nombre', 'temporada', 'posicion', 'edad', 'partidos',
                'goles', 'asistencias', 'pases_precisos',
                'etiqueta',  # target
                'goles_por_partido', 'asist_por_partido', 'contribucion_gol',
                'experiencia', 'edad_primer_registro', 'primera_temporada',
                'temporadas_en_dataset',
                'promedio_goles_por_temporada', 'promedio_asistencias_por_temporada',
                'proporcion_goles', 'pases_norm', 'perfil_ofensivo',
                'partidos_por_temporada']
df_exp = df_exp[feature_cols].copy()

df_exp.to_csv(os.path.join(DATA_DIR, 'adn_boca_real_features.csv'), index=False, encoding='utf-8-sig')
print(f'Saved features to adn_boca_real_features.csv')
print(f'Features: {[c for c in feature_cols if c not in ["nombre","temporada","etiqueta"]]}')

# File sizes
for f in ['adn_boca_real.csv', 'adn_boca_real_features.csv']:
    size = os.path.getsize(os.path.join(DATA_DIR, f))
    print(f'{f}: {size:,} bytes')
