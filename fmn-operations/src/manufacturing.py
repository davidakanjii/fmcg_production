"""Interpretable regularized logistic regression with purged temporal validation.

Small NumPy IRLS implementation avoids heavyweight serving dependencies. Fit uses
unweighted likelihood: class weighting would distort probability interpretation.
"""
import numpy as np
import pandas as pd

FEATURES = ['temperature_c', 'vibration_mm_s', 'run_hours_since_maintenance',
            'temperature_mean_6h', 'vibration_mean_6h', 'temperature_change_6h',
            'vibration_change_6h', 'temperature_missing', 'vibration_missing']
NAMES = ['Temperature (C)', 'Vibration (mm/s)', 'Hours since maintenance',
         '6-hour mean temperature (C)', '6-hour mean vibration (mm/s)',
         'Temperature change over 6h (C)', 'Vibration change over 6h (mm/s)',
         'Temperature missing', 'Vibration missing']

def features(d):
    parts = []
    for machine, h in d.groupby('machine_id'):
        h = h.sort_values('timestamp').copy()
        h['temperature_missing'] = h.temperature_c.isna().astype(float)
        h['vibration_missing'] = h.vibration_mm_s.isna().astype(float)
        for col, short in [('temperature_c','temperature'),('vibration_mm_s','vibration')]:
            # Causal fill only, bounded to three preceding hours.
            h[col] = h[col].ffill(limit=3)
            h[short + '_mean_6h'] = h[col].rolling(6, min_periods=1).mean()
            h[short + '_change_6h'] = h[col] - h[col].shift(6)
        labels = np.zeros(len(h), dtype=float)
        for offset in range(1,25):
            labels = np.maximum(labels, h.failure_event.shift(-offset).fillna(0).to_numpy())
        labels[-24:] = np.nan  # Unknown future, even if a shorter partial window contains a failure.
        h['target'] = labels
        h['history_hours'] = np.arange(len(h)) + 1
        parts.append(h)
    return pd.concat(parts, ignore_index=True)

def sigmoid(x):
    return 1 / (1 + np.exp(-np.clip(x, -35, 35)))

def fit(frame, cols, penalty=10.0):
    raw = frame[cols].to_numpy(float)
    median = np.nanmedian(raw, axis=0)
    median = np.nan_to_num(median)
    x = np.where(np.isnan(raw), median, raw)
    mean, scale = x.mean(axis=0), x.std(axis=0)
    scale[scale < 1e-8] = 1
    x = np.column_stack([np.ones(len(x)), (x - mean) / scale])
    y = frame.target.to_numpy(float)
    if len(np.unique(y)) < 2:
        raise ValueError('Training needs positive and negative labels.')
    beta = np.zeros(x.shape[1]); beta[0] = np.log(y.mean()/(1-y.mean()))
    reg = np.eye(x.shape[1]) * penalty; reg[0,0] = 0
    def loss(b):
        z = x @ b
        return np.sum(np.logaddexp(0,z) - y*z) + .5*b@reg@b
    for _ in range(80):
        p = sigmoid(x@beta)
        g = x.T@(p-y) + reg@beta
        h = x.T @ (x * (p*(1-p))[:,None]) + reg + np.eye(len(beta))*1e-9
        step = np.linalg.solve(h,g)
        alpha = 1.0
        old = loss(beta)
        while alpha > 1e-6 and loss(beta-alpha*step) > old:
            alpha *= .5
        beta -= alpha*step
        if np.max(np.abs(alpha*step)) < 1e-6:
            break
    return dict(columns=cols, median=median.tolist(), mean=mean.tolist(), scale=scale.tolist(),
                beta=beta.tolist(), penalty=penalty, train_end=str(frame.timestamp.max()))

def contributions(frame, model):
    raw = frame[model['columns']].to_numpy(float)
    x = np.where(np.isnan(raw), model['median'], raw)
    return (x-model['mean'])/model['scale'] * np.array(model['beta'][1:])

def predict(frame, model):
    return sigmoid(contributions(frame,model).sum(axis=1)+model['beta'][0])

def average_precision(y, p):
    """Non-interpolated AP with tied score groups, matching PR step integration."""
    y, p = np.asarray(y,dtype=int), np.asarray(p,dtype=float)
    if y.sum() == 0:
        return None
    order = np.argsort(-p, kind='stable'); ys=y[order]; ps=p[order]
    ends = np.r_[np.flatnonzero(np.diff(ps)), len(ps)-1]
    tp = np.cumsum(ys)[ends]; precision=tp/(ends+1)
    return float(np.sum(np.diff(np.r_[0,tp/y.sum()])*precision))

def metrics(frame, p, threshold):
    y=frame.target.to_numpy(int); a=p>=threshold
    tp=int((a & (y==1)).sum()); fp=int((a & (y==0)).sum()); fn=int((~a & (y==1)).sum())
    precision=tp/max(tp+fp,1); recall=tp/max(tp+fn,1)
    return dict(rows=len(y), positive_hours=int(y.sum()), prevalence=float(y.mean()),
        average_precision=average_precision(y,p), precision=precision, recall=recall,
        f2=5*precision*recall/max(4*precision+recall,1e-12), brier=float(np.mean((p-y)**2)),
        false_positive_hours=fp, alert_hours=int(a.sum()), threshold=float(threshold))

def events_metrics(frame, p, threshold, raw):
    scored=frame[['machine_id','timestamp']].copy(); scored['alert']=p>=threshold
    events=[]
    for e in raw[raw.failure_event.eq(1)].itertuples():
        pre=scored[(scored.machine_id==e.machine_id)&(scored.timestamp<e.timestamp)&
                   (scored.timestamp>=e.timestamp-pd.Timedelta(hours=24))]
        # Only events with the entire 24-hour warning window in the evaluated set.
        if len(pre)!=24:
            continue
        alarms=pre[pre.alert]
        events.append(dict(machine=e.machine_id, failure_at=str(e.timestamp), detected=not alarms.empty,
            lead_hours=None if alarms.empty else float((e.timestamp-alarms.timestamp.min()).total_seconds()/3600)))
    n=sum(e['detected'] for e in events)
    # Each run of consecutive hourly warnings counts as one episode.
    episodes=0
    for _,h in scored.groupby('machine_id'):
        h=h.sort_values('timestamp')
        continuation=h.alert.shift(1,fill_value=False)&h.timestamp.diff().eq(pd.Timedelta(hours=1))
        episodes+=int((h.alert & ~continuation).sum())
    return dict(eligible_events=len(events), detected_events=n, event_recall=n/len(events) if events else None,
        alert_episodes=episodes, false_alert_hours_per_machine_day=float(((p>=threshold)&frame.target.eq(0)).sum()/(len(frame)/24)),
        events=events)

def train_evaluate(d):
    f=features(d)
    eligible=f[f.target.notna() & f.failure_event.eq(0)].copy()
    # Purge label windows crossing split boundaries. No future-failure targets enter prior splits.
    train=eligible[eligible.timestamp < pd.Timestamp('2026-03-01')-pd.Timedelta(hours=24)]
    val=eligible[(eligible.timestamp>=pd.Timestamp('2026-03-01')) &
                 (eligible.timestamp<pd.Timestamp('2026-04-01')-pd.Timedelta(hours=24))]
    test=eligible[eligible.timestamp>=pd.Timestamp('2026-04-01')]
    candidates=[]
    for name,cols,pen in [('maintenance_baseline',['run_hours_since_maintenance'],10),
                          ('sensor_logistic_l2_1',FEATURES,1),('sensor_logistic_l2_10',FEATURES,10),
                          ('sensor_logistic_l2_100',FEATURES,100)]:
        model=fit(train,cols,pen); pv=predict(val,model)
        candidates.append((name,model,pv,average_precision(val.target,pv)))
    selected=max(candidates,key=lambda c:c[3] if c[3] is not None else -1)
    name,model,pv,_=selected
    thresholds=np.unique(np.r_[np.linspace(.005,.5,100),np.quantile(pv,np.linspace(.90,1,101))])
    best=max((metrics(val,pv,t) for t in thresholds), key=lambda m:(m['f2'],m['precision']))
    threshold=best['threshold']
    pt=predict(test,model)
    evaluation=dict(selected=name, train_rows=len(train), train_positive_hours=int(train.target.sum()),
        validation_candidates={n:dict(average_precision=ap) for n,_,_,ap in candidates},
        validation=best, test=metrics(test,pt,threshold),
        baseline_test=metrics(test,predict(test,candidates[0][1]),threshold),
        event_test=events_metrics(test,pt,threshold,d), threshold_policy='Maximum validation F2; frozen before test',
        train_end=str(train.timestamp.max()),validation_start=str(val.timestamp.min()),
        validation_end=str(val.timestamp.max()),test_start=str(test.timestamp.min()),test_end=str(test.timestamp.max()),
        horizon_hours=24, total_failure_events=int(d.failure_event.sum()),
        calibration='Uncalibrated model score, not a validated failure probability; only 17 events available.')
    # Evaluate the baseline at its own validation-selected threshold as well.
    bpv=candidates[0][2]
    bt=max((metrics(val,bpv,t) for t in thresholds),key=lambda m:(m['f2'],m['precision']))['threshold']
    evaluation['baseline_test']=metrics(test,predict(test,candidates[0][1]),bt)
    cold=test[test.history_hours<168]
    evaluation['new_machine_test']=metrics(cold,predict(cold,model),threshold) if len(cold) else None
    model.update(name=name, threshold=threshold)
    test_output=test[['machine_id','timestamp','target']].copy();test_output['risk_score']=pt
    return model,evaluation,f,test_output

def snapshot(d, f, model):
    result=[]
    for machine,h in f.groupby('machine_id'):
        h=h.sort_values('timestamp');last=h.tail(1);r=last.iloc[0]
        raw=d[d.machine_id==machine].iloc[-1]
        score=float(predict(last,model)[0]);c=contributions(last,model)[0]
        drivers=[]
        for j in np.argsort(-np.abs(c))[:4]:
            col=model['columns'][j]
            drivers.append(dict(feature=col,label=NAMES[FEATURES.index(col)],value=None if pd.isna(r[col]) else float(r[col]),
                log_odds_contribution=float(c[j]), direction='raises score' if c[j]>0 else 'lowers score',
                training_mean=float(model['mean'][j])))
        cold=len(h)<168
        missing=bool(raw[['temperature_c','vibration_mm_s']].isna().any())
        flag='Failure recorded' if r.failure_event==1 else 'Inspect now' if score>=model['threshold'] else 'Monitor'
        recent=h.tail(72);scores=predict(recent,model)
        result.append(dict(id=machine,line=r.line,as_of=str(r.timestamp),history_hours=len(h),cold_start=cold,
            flag=flag,risk_score=score,threshold=model['threshold'],horizon_hours=24,
            temperature_c=None if pd.isna(raw.temperature_c) else float(raw.temperature_c),
            vibration_mm_s=None if pd.isna(raw.vibration_mm_s) else float(raw.vibration_mm_s),
            maintenance_hours=float(r.run_hours_since_maintenance),missing_sensor=missing,drivers=drivers,
            previous_24h_score=float(scores[-25]) if len(scores)>24 else None,
            trend=[dict(timestamp=str(row.timestamp),score=float(s),temperature_c=None if pd.isna(row.temperature_c) else float(row.temperature_c),
                        vibration_mm_s=None if pd.isna(row.vibration_mm_s) else float(row.vibration_mm_s))
                   for row,s in zip(recent.itertuples(),scores)]))
    return sorted(result,key=lambda r:-r['risk_score'])
