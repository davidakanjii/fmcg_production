"""Short-horizon forecasts, temporal backtests and explicit inventory policy."""
import numpy as np
import pandas as pd

METHODS = ['mean28', 'seasonal7', 'weekday_shrinkage']

def forecast(history, peers, dates, method='weekday_shrinkage'):
    """All inputs must end before forecast dates. Category transfer for <28 days."""
    if history.date.max() >= dates.min() or (len(peers) and peers.date.max() >= dates.min()):
        raise ValueError('Forecast inputs contain future observations.')
    observed = history.units_sold.dropna()
    n = len(observed)
    recent = history.tail(28).units_sold.mean()
    peer_levels = peers.groupby('sku_id').units_sold.mean()
    prior = float(peer_levels.median()) if len(peer_levels) else float(recent if pd.notna(recent) else 0)
    recent = float(recent) if pd.notna(recent) else prior
    if n < 28:
        weight = n / (n + 14)
        level = weight * recent + (1 - weight) * prior
        return np.full(len(dates), max(0, level))
    if method == 'mean28':
        return np.full(len(dates), recent)
    if method == 'seasonal7':
        last = history.tail(7).set_index(history.tail(7).date.dt.dayofweek).units_sold.to_dict()
        return np.array([last.get(t.dayofweek, recent) for t in dates], dtype=float).clip(0)
    h = history.tail(56).copy()
    h['dow'] = h.date.dt.dayofweek
    means = h.groupby('dow').units_sold.mean()
    counts = h.groupby('dow').units_sold.count()
    overall = h.units_sold.mean()
    factors = ((means * counts + overall * 3) / (counts + 3)) / max(overall, 1)
    return np.array([recent * factors.get(t.dayofweek, 1) for t in dates]).clip(0)

def error_metrics(rows):
    d = pd.DataFrame(rows).dropna(subset=['actual', 'prediction'])
    err = d.prediction - d.actual
    return dict(n=len(d), mae=float(err.abs().mean()), wape=float(err.abs().sum() / max(d.actual.abs().sum(), 1)),
                bias=float(err.sum() / max(d.actual.abs().sum(), 1)))

def backtest(d, origins, methods=METHODS, cold=False):
    rows = []
    for origin in origins:
        origin = pd.Timestamp(origin)
        past = d[d.date <= origin]
        future = d[(d.date > origin) & (d.date <= origin + pd.Timedelta(days=14))]
        for sku, full in past.groupby('sku_id'):
            if len(full) < 56:
                continue
            h = full.tail(12) if cold else full
            peers = past[(past.category == h.category.iloc[-1]) & (past.sku_id != sku) &
                         (past.date > origin - pd.Timedelta(days=28))]
            target = future[future.sku_id == sku]
            dates = pd.DatetimeIndex(target.date)
            for method in methods:
                p = forecast(h, peers, dates, method)
                p = np.where(np.isfinite(p), p, h.units_sold.mean())
                for date, actual, pred in zip(dates, target.units_sold, p):
                    rows.append(dict(sku_id=sku, origin=str(origin.date()), date=str(date.date()),
                                     actual=float(actual), prediction=float(pred), method=method))
    return rows

def evaluate(d):
    tuning = backtest(d, ['2026-04-01', '2026-04-15', '2026-04-29'])
    tune_metrics = {m: error_metrics([r for r in tuning if r['method'] == m]) for m in METHODS}
    selected = min(METHODS, key=lambda m: tune_metrics[m]['wape'])
    test = backtest(d, ['2026-05-13', '2026-05-27', '2026-06-10'])
    test_metrics = {m: error_metrics([r for r in test if r['method'] == m]) for m in METHODS}
    residuals = {}
    for sku in d.sku_id.unique():
        e = [abs(r['prediction'] - r['actual']) for r in tuning if r['method'] == selected and r['sku_id'] == sku and np.isfinite(r['actual'])]
        if e:
            residuals[sku] = float(np.quantile(e, .9))
    chosen_test = [r for r in test if r['method'] == selected and np.isfinite(r['actual'])]
    coverage = np.mean([abs(r['prediction'] - r['actual']) <= residuals[r['sku_id']] for r in chosen_test])
    cold_rows = backtest(d, ['2026-05-13', '2026-05-27', '2026-06-10'], [selected], cold=True)
    per_sku = {sku: error_metrics([r for r in chosen_test if r['sku_id'] == sku]) for sku in residuals}
    return dict(selected=selected, tuning=tune_metrics, test=test_metrics, per_sku_test=per_sku,
                daily_band_test_coverage=float(coverage), cold_start_simulation=error_metrics(cold_rows),
                test_origins=['2026-05-13', '2026-05-27', '2026-06-10'], horizon_days=14,
                band_description='Tuning 90th percentile absolute error per SKU; empirical daily band, not a stockout probability.'), residuals, test

def current_stock(h):
    last = h.iloc[-1]
    if pd.notna(last.closing_stock):
        return float(last.closing_stock), 'observed'
    good = h[h.closing_stock.notna()]
    if good.empty:
        return None, 'unknown'
    anchor = good.iloc[-1]
    later = h[h.date > anchor.date]
    if later[['units_received', 'units_sold']].isna().any().any():
        return None, 'unknown'
    return float(max(0, anchor.closing_stock + (later.units_received - later.units_sold).sum())), 'reconstructed from stock balance'

def snapshot(d, evaluation, residuals):
    result = []
    for sku, h in d.groupby('sku_id'):
        last = h.iloc[-1]
        peers = d[(d.category == last.category) & (d.sku_id != sku) & (d.date <= last.date) &
                  (d.date > last.date - pd.Timedelta(days=28))]
        dates = pd.date_range(last.date + pd.Timedelta(days=1), periods=30)
        p = forecast(h, peers, dates, evaluation['selected'])
        p = np.nan_to_num(p, nan=float(h.units_sold.mean()))
        stock, stock_source = current_stock(h)
        lead = int(last.lead_time_days)
        if lead > 30:
            raise ValueError('Lead time exceeds supported 30-day horizon.')
        expected = float(p[:lead].sum())
        n = int(h.units_sold.notna().sum())
        cold = n < 28
        q = residuals.get(sku, float(p.mean()) * .8)
        # Heuristic reserve, explicitly not an optimized service level or interval.
        reserve = float(q * np.sqrt(lead))
        cover = stock / max(float(p.mean()), 1) if stock is not None else None
        flag = ('Check stock' if stock is None else 'Shortage' if stock < expected else
                'Reorder soon' if stock < expected + reserve else 'Excess stock' if cover > lead + 30 else 'Healthy')
        stockout = None
        if stock is not None and (np.cumsum(p) > stock).any():
            stockout = str(dates[np.argmax(np.cumsum(p) > stock)].date())
        result.append(dict(id=sku, category=last.category, as_of=str(last.date.date()), history_days=len(h),
            observed_sales_days=n, cold_start=cold, flag=flag, stock=stock, stock_source=stock_source,
            lead_days=lead, demand_7d=float(p[:7].sum()), demand_14d=float(p[:14].sum()), demand_30d=float(p.sum()),
            lead_demand=expected, reserve=reserve, cover_days=cover, stockout_date=stockout,
            reorder_units=None if stock is None else float(max(0, expected + reserve - stock)),
            missing_sales=int(h.units_sold.isna().sum()), zero_stock_days=int(h.closing_stock.eq(0).sum()),
            forecast=[dict(date=str(t.date()), units=float(v), lower=float(max(0, v-q)), upper=float(v+q),
                           projected_stock=None if stock is None else float(stock - p[:i+1].sum())) for i, (t,v) in enumerate(zip(dates,p))],
            history=[dict(date=str(r.date.date()), units=None if pd.isna(r.units_sold) else float(r.units_sold),
                          stock=None if pd.isna(r.closing_stock) else float(r.closing_stock)) for r in h.tail(60).itertuples()],
            model='category-shrunk mean' if cold else evaluation['selected']))
    order = {'Shortage':0, 'Check stock':1, 'Reorder soon':2, 'Excess stock':3, 'Healthy':4}
    return sorted(result, key=lambda r: (order[r['flag']], r['cover_days'] or 0))
