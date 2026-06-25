import pandas as pd
import numpy as np
import re

DATA_DIR = 'C:/Users/Agu/Desktop/boca-scouting-ds/data'

# Load both datasets
df_modern = pd.read_csv(f'{DATA_DIR}/adn_boca_real.csv', encoding='utf-8-sig')
df_hist = pd.read_csv(f'{DATA_DIR}/adn_boca_historical_raw.csv', encoding='utf-8-sig')

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

# Recompute rating and etiqueta for consistency
def compute_rating(row):
    gpg = row['goles'] / max(row['partidos'], 1)
    apg = row['asistencias'] / max(row['partidos'], 1)
    mp = min(row['partidos'] / 38, 1.0)
    return min(round(6.0 + gpg * 3.0 + apg * 2.0 + mp * 0.5, 1), 9.5)

combined['rating'] = combined.apply(compute_rating, axis=1)
combined['etiqueta'] = ((combined['rating'] >= 7.0) & 
                         ((combined['goles'] + combined['asistencias']) > 2)).astype(int)

# Sort
combined = combined.sort_values(['temporada', 'rating'], ascending=[False, False]).reset_index(drop=True)

# Select final columns
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
combined.to_csv(f'{DATA_DIR}/adn_boca_real.csv', index=False, encoding='utf-8-sig')
print(f'\nSaved to adn_boca_real.csv')

# Create features version
df_exp = combined.copy()
df_exp['goles_por_partido'] = (df_exp['goles'] / df_exp['partidos'].replace(0, np.nan)).fillna(0)
df_exp['asist_por_partido'] = (df_exp['asistencias'] / df_exp['partidos'].replace(0, np.nan)).fillna(0)
df_exp['rendimiento'] = df_exp['rating'] * (df_exp['partidos'] / 38)
df_exp['participacion_gol'] = ((df_exp['goles'] + df_exp['asistencias']) / df_exp['partidos'].replace(0, np.nan)).fillna(0)
df_exp['experiencia'] = df_exp['temporada'] - (2024 - df_exp['edad'])
df_exp['pases_norm'] = df_exp['pases_precisos'] / 90
df_exp['perfil_ofensivo'] = (df_exp['posicion'].isin(['Attacking Midfield', 'Left Winger', 'Right Winger',
                                                       'Centre-Forward', 'Secondary Striker'])).astype(int)

df_exp.to_csv(f'{DATA_DIR}/adn_boca_real_features.csv', index=False, encoding='utf-8-sig')
print(f'Saved features to adn_boca_real_features.csv')

# File sizes
import os
for f in ['adn_boca_real.csv', 'adn_boca_real_features.csv']:
    size = os.path.getsize(f'{DATA_DIR}/{f}')
    print(f'{f}: {size:,} bytes')
