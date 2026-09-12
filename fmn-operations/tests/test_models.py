import json
import unittest
from unittest.mock import patch
from pathlib import Path
import numpy as np
import pandas as pd
from src.data import ROOT,load_data
from src import supply,manufacturing as m

class ModelTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.s,_=load_data('supply');cls.m,_=load_data('manufacturing')
        cls.bundle=json.loads((ROOT/'artifacts/dashboard.json').read_text())

    def test_source_cleaning_and_categories(self):
        self.assertEqual(len(self.s),4536);self.assertEqual(len(self.m),43344)
        self.assertEqual(self.s.category.nunique(),5)
        self.assertFalse(self.s.duplicated(['sku_id','date']).any())
        self.assertEqual(self.s.units_sold.isna().sum(),90)

    def test_duplicate_key_conflict_rejected(self):
        d=self.s.head(2).copy();other=d.head(1).copy();other.units_sold+=1
        with patch('src.data.pd.read_csv',return_value=pd.concat([d,other])):
            with self.assertRaisesRegex(ValueError,'Conflicting'):load_data('supply')

    def test_future_inputs_rejected(self):
        h=self.s[self.s.sku_id=='SKU-1000'].head(60)
        with self.assertRaisesRegex(ValueError,'future'):
            supply.forecast(h,h.iloc[:0],pd.date_range(h.date.iloc[-1],periods=3))

    def test_stock_reconstruction_never_silently_forward_fills(self):
        h=pd.DataFrame({'date':pd.date_range('2026-01-01',periods=3),
            'closing_stock':[100,np.nan,np.nan],'units_received':[0,20,0],'units_sold':[5,30,10]})
        self.assertEqual(supply.current_stock(h)[0],80)
        h.loc[1,'units_sold']=np.nan
        self.assertIsNone(supply.current_stock(h)[0])

    def test_no_labels_at_censored_tail_and_excludes_present_failure(self):
        h=self.m[self.m.machine_id=='MCH-202'].head(80).copy();h['failure_event']=0
        h.loc[h.index[40],'failure_event']=1
        f=m.features(h)
        self.assertEqual(f.loc[16:39,'target'].sum(),24)
        self.assertEqual(f.loc[40,'target'],0)
        self.assertTrue(f.tail(24).target.isna().all())

    def test_sensor_features_are_causal(self):
        h=self.m[self.m.machine_id=='MCH-200'].head(100).copy()
        before=m.features(h)
        h.loc[h.index[60]:,'temperature_c']=999
        after=m.features(h)
        np.testing.assert_allclose(before.loc[:59,m.FEATURES],after.loc[:59,m.FEATURES],equal_nan=True)

    def test_logistic_fit_and_contributions(self):
        frame=pd.DataFrame({'x':np.linspace(-3,3,100),'target':np.r_[np.zeros(50),np.ones(50)],
                            'timestamp':pd.date_range('2026-01-01',periods=100,freq='h')})
        model=m.fit(frame,['x'],1)
        p=m.predict(frame,model)
        self.assertLess(p[0],.1);self.assertGreater(p[-1],.9)
        np.testing.assert_allclose(p,m.sigmoid(m.contributions(frame,model).sum(1)+model['beta'][0]))

    def test_average_precision_ties(self):
        self.assertAlmostEqual(m.average_precision([1,0],[.5,.5]),.5)
        self.assertEqual(m.average_precision([1,0],[.9,.1]),1)
        self.assertIsNone(m.average_precision([0,0],[.9,.1]))

    def test_missing_targets_not_scored(self):
        r=supply.error_metrics([{'actual':10,'prediction':12},{'actual':None,'prediction':900}])
        self.assertEqual(r['n'],1);self.assertEqual(r['mae'],2)

    def test_artifact_inventory_math_and_cold_starts(self):
        rows=self.bundle['supply']
        self.assertEqual(sum(r['cold_start'] for r in rows),3)
        for r in rows:
            self.assertEqual(len(r['forecast']),30)
            self.assertAlmostEqual(r['lead_demand'],sum(f['units'] for f in r['forecast'][:r['lead_days']]))
            if r['stock'] is not None:
                self.assertAlmostEqual(r['reorder_units'],max(0,r['lead_demand']+r['reserve']-r['stock']))
                self.assertAlmostEqual(r['forecast'][0]['projected_stock'],r['stock']-r['forecast'][0]['units'])

    def test_temporal_split_purge(self):
        e=self.bundle['evaluation']['manufacturing']
        self.assertLess(pd.Timestamp(e['train_end'])+pd.Timedelta(hours=24),pd.Timestamp(e['validation_start']))
        self.assertLess(pd.Timestamp(e['validation_end'])+pd.Timedelta(hours=24),pd.Timestamp(e['test_start']))
        self.assertEqual(e['test']['threshold'],e['validation']['threshold'])

    def test_new_machine_no_positive_validation_claim(self):
        e=self.bundle['evaluation']['manufacturing']['new_machine_test']
        self.assertEqual(e['positive_hours'],0);self.assertIsNone(e['average_precision'])

if __name__=='__main__':unittest.main()
