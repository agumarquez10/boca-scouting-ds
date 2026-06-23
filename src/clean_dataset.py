import os
import pandas as pd
import numpy as np


def clean_dataset(inpath, outpath, report_path):
    df = pd.read_csv(inpath)
    report_lines = []

    report_lines.append(f'Input file: {inpath}')
    report_lines.append(f'Initial rows: {len(df)}')

    # Drop exact duplicates
    before = len(df)
    df = df.drop_duplicates()
    after = len(df)
    report_lines.append(f'Duplicates removed: {before - after}')

    # Basic info
    report_lines.append('\nColumn dtypes:')
    report_lines.append(str(df.dtypes))
    report_lines.append('\nMissing values per column:')
    report_lines.append(str(df.isnull().sum()))

    # Fill missing numeric with median
    num_cols = df.select_dtypes(include=[np.number]).columns.tolist()
    for c in num_cols:
        if df[c].isnull().any():
            med = df[c].median()
            df[c] = df[c].fillna(med)
            report_lines.append(f'Filled missing in {c} with median={med}')

    # Fill missing object cols with mode or 'unknown'
    obj_cols = df.select_dtypes(include=['object']).columns.tolist()
    for c in obj_cols:
        if df[c].isnull().any():
            try:
                mode = df[c].mode()[0]
            except Exception:
                mode = 'unknown'
            df[c] = df[c].fillna(mode)
            report_lines.append(f'Filled missing in {c} with mode={mode}')

    # Convert common columns to numeric types where appropriate
    int_cols = ['temporada', 'edad', 'partidos']
    for c in int_cols:
        if c in df.columns:
            df[c] = pd.to_numeric(df[c], errors='coerce').fillna(0).astype(int)

    # Ensure binary/int columns
    for c in ['etiqueta', 'perfil_ofensivo']:
        if c in df.columns:
            df[c] = pd.to_numeric(df[c], errors='coerce').fillna(0).astype(int)

    # Feature engineering: one-hot encode position
    if 'posicion' in df.columns:
        pos_dummies = pd.get_dummies(df['posicion'], prefix='pos')
        df = pd.concat([df.drop(columns=['posicion']), pos_dummies], axis=1)
        report_lines.append('One-hot encoded `posicion`')

    # Normalize numeric columns (create scaled versions)
    numeric_for_scaling = [c for c in num_cols if c in df.columns and c not in ['etiqueta', 'perfil_ofensivo']]
    for c in numeric_for_scaling:
        mean = df[c].mean()
        std = df[c].std()
        if std == 0 or np.isnan(std):
            df[c + '_scaled'] = 0.0
        else:
            df[c + '_scaled'] = (df[c] - mean) / std
        report_lines.append(f'Added scaled column: {c}_scaled (mean={mean:.3f}, std={std:.3f})')

    # Save cleaned dataset
    os.makedirs(os.path.dirname(outpath), exist_ok=True)
    df.to_csv(outpath, index=False)
    report_lines.append(f'Cleaned dataset saved to: {outpath}')

    # Save a short report
    os.makedirs(os.path.dirname(report_path), exist_ok=True)
    with open(report_path, 'w', encoding='utf-8') as f:
        f.write('\n'.join(report_lines))

    return outpath, report_path


if __name__ == '__main__':
    workspace_root = os.path.dirname(os.path.dirname(__file__))
    inpath = os.path.join(workspace_root, 'data', 'adn_boca_features.csv')
    outpath = os.path.join(workspace_root, 'data', 'adn_boca_features_clean.csv')
    report_path = os.path.join(workspace_root, 'outputs', 'dataset_report.txt')
    out, rep = clean_dataset(inpath, outpath, report_path)
    print('Saved cleaned dataset to', out)
    print('Saved report to', rep)
