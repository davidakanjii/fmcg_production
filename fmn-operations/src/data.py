"""Schema checks and deterministic cleaning. Never fill missing evaluation labels."""
from pathlib import Path
import hashlib
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]

def load_data(kind, directory=None):
    directory = Path(directory or ROOT / 'data')
    supply = kind == 'supply'
    filename = 'project1_supply_chain_demand.csv' if supply else 'project2_manufacturing_sensors.csv'
    entity, time = ('sku_id', 'date') if supply else ('machine_id', 'timestamp')
    numeric = ['units_sold', 'units_received', 'closing_stock', 'lead_time_days'] if supply else [
        'temperature_c', 'vibration_mm_s', 'run_hours_since_maintenance', 'failure_event']
    category = 'category' if supply else 'line'
    path = directory / filename
    d = pd.read_csv(path)
    required = [entity, time, category] + numeric
    if not set(required).issubset(d.columns):
        raise ValueError(f'{filename}: missing columns {set(required)-set(d.columns)}')
    report = dict(source=filename, sha256=hashlib.sha256(path.read_bytes()).hexdigest(), raw_rows=len(d),
                  exact_duplicates=int(d.duplicated().sum()), missing=d[required].isna().sum().to_dict())
    d = d.drop_duplicates().copy()
    d[time] = pd.to_datetime(d[time], errors='raise')
    if d[[entity, time, category]].isna().any().any():
        raise ValueError('Entity, timestamp and category must be present.')
    for c in numeric:
        d[c] = pd.to_numeric(d[c], errors='raise')
        if np.isinf(d[c]).any():
            raise ValueError(f'Non-finite {c}')
    if d.duplicated([entity, time]).any():
        raise ValueError('Conflicting entity/time rows require source correction.')
    if supply:
        report['category_labels_before'] = sorted(d.category.unique().tolist())
        d['category'] = d.category.str.strip().str.title()
        if d[numeric].lt(0).any().any() or d.lead_time_days.isna().any() or d.lead_time_days.le(0).any():
            raise ValueError('Supply measures must be nonnegative and lead times positive.')
        if d.lead_time_days.mod(1).ne(0).any():
            raise ValueError('Lead times must be whole days.')
    else:
        if not d.failure_event.isin([0, 1]).all():
            raise ValueError('Failure events must be 0 or 1.')
        if d[['vibration_mm_s', 'run_hours_since_maintenance']].lt(0).any().any():
            raise ValueError('Negative vibration or maintenance age.')
        if d.run_hours_since_maintenance.isna().any():
            raise ValueError('Missing maintenance age.')
    d = d.sort_values([entity, time]).reset_index(drop=True)
    gap = d.groupby(entity)[time].diff().dropna()
    expected = pd.Timedelta(days=1) if supply else pd.Timedelta(hours=1)
    if not gap.eq(expected).all():
        raise ValueError('Irregular time grid: reindex and review missing periods before modeling.')
    report.update(clean_rows=len(d), entities=int(d[entity].nunique()), start=str(d[time].min()),
                  end=str(d[time].max()), gaps=int(gap.ne(expected).sum()))
    return d, report
