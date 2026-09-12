"""Rebuild reviewed evidence and model artifacts: python train.py."""
import json
from datetime import datetime, timezone
from pathlib import Path
import numpy as np
import pandas as pd
from src.data import ROOT, load_data
from src import supply, manufacturing

def safe(value):
    if isinstance(value,dict): return {k:safe(v) for k,v in value.items()}
    if isinstance(value,(list,tuple)): return [safe(v) for v in value]
    if isinstance(value,(np.integer,)): return int(value)
    if isinstance(value,(float,np.floating)): return None if not np.isfinite(value) else float(value)
    if isinstance(value,np.bool_): return bool(value)
    return value

def main():
    a,qa=load_data('supply');b,qb=load_data('manufacturing')
    print('Evaluating supply forecasts...',flush=True)
    se,residuals,st=supply.evaluate(a)
    print('Training and validating machine risk...',flush=True)
    model,me,features,mt=manufacturing.train_evaluate(b)
    bundle=safe(dict(version=1,generated_at=datetime.now(timezone.utc).isoformat(),
        data_quality=dict(supply=qa,manufacturing=qb),evaluation=dict(supply=se,manufacturing=me),
        supply=supply.snapshot(a,se,residuals),manufacturing=manufacturing.snapshot(b,features,model),
        manufacturing_replays={str(t):manufacturing.snapshot(b[b.timestamp<=t],features[features.timestamp<=t],model)
            for t in [pd.Timestamp('2026-04-13 00:00:00'),pd.Timestamp('2026-04-24 12:00:00')]}))
    out=ROOT/'artifacts';out.mkdir(exist_ok=True)
    (out/'dashboard.json').write_text(json.dumps(bundle,indent=2,allow_nan=False),encoding='utf-8')
    (out/'machine_model.json').write_text(json.dumps(safe(model),indent=2,allow_nan=False),encoding='utf-8')
    (out/'supply_model.json').write_text(json.dumps(dict(method=se['selected'],residual_bands=residuals),indent=2),encoding='utf-8')
    pd.DataFrame(st).to_csv(out/'supply_backtest.csv',index=False)
    mt.to_csv(out/'machine_backtest.csv',index=False)
    print(json.dumps(dict(supply_selected=se['selected'],supply_test=se['test'][se['selected']],
                         machine_selected=me['selected'],machine_test=me['test'],events=me['event_test']),indent=2))

if __name__=='__main__': main()
