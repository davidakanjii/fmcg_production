import io
import json
import os
import unittest
from unittest.mock import patch
from urllib.error import HTTPError
from src.data import ROOT
from src.llm import Explainer,LLMUnavailable,retrieve,snapshot_bundle

class LLMTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.bundle=json.loads((ROOT/'artifacts/dashboard.json').read_text())

    def test_exact_id_retrieval_is_grounded(self):
        e=retrieve(self.bundle,'supply','Why is sku-1004 flagged?')
        self.assertEqual([r['id'] for r in e['records']],['SKU-1004'])
        self.assertIn('forecast',e['records'][0])
        self.assertEqual(e['records'][0]['flag'],'Healthy')

    def test_fleet_is_complete_not_arbitrary_top_k(self):
        e=retrieve(self.bundle,'manufacturing','Which machines need attention?')
        self.assertEqual(len(e['records']),17)
        self.assertNotIn('trend',e['records'][0])

    def test_unknown_id_fails_explicitly(self):
        with self.assertRaisesRegex(ValueError,'No data'):retrieve(self.bundle,'supply','SKU-9999')

    def test_replay_excludes_future_outcomes(self):
        b=snapshot_bundle(self.bundle,'manufacturing','2026-04-13 00:00:00')
        e=retrieve(b,'manufacturing',entity_id='MCH-207')
        self.assertEqual(e['as_of'],'2026-04-13 00:00:00')
        self.assertEqual(e['records'][0]['flag'],'Inspect now')
        self.assertNotIn('test',e['validation']);self.assertNotIn('event_test',e['validation'])
        self.assertTrue(all(t['timestamp']<=e['as_of'] for t in e['records'][0]['trend']))

    def test_no_key_means_no_fabricated_explanation(self):
        with patch.dict(os.environ,{'OPENAI_API_KEY':''}):
            with self.assertRaisesRegex(LLMUnavailable,'not configured'):Explainer().answer({},'why')

    def response(self,answer,ids):
        return io.BytesIO(json.dumps({'status':'completed','output':[{'type':'message','content':[
            {'type':'output_text','text':json.dumps({'answer':answer,'source_ids':ids})}]}]}).encode())

    def test_real_request_contract_with_mocked_transport(self):
        e=retrieve(self.bundle,'supply',entity_id='SKU-1004')
        with patch.dict(os.environ,{'OPENAI_API_KEY':'test-not-a-real-key'}),patch('src.llm.request.urlopen') as call:
            call.return_value=self.response('SKU-1004 is Healthy.',['SKU-1004'])
            service=Explainer();r=service.answer(e,'Explain','explanation')
            self.assertEqual(r['source_ids'],['SKU-1004'])
            req=call.call_args.args[0];body=json.loads(req.data)
            self.assertEqual(req.full_url,'https://api.openai.com/v1/responses')
            self.assertFalse(body['store']);self.assertIn('stock',body['input'])
            self.assertEqual(body['text']['format']['type'],'json_schema')
            self.assertTrue(service.answer(e,'Explain','explanation')['cached']);self.assertEqual(call.call_count,1)

    def test_invented_source_rejected(self):
        with patch.dict(os.environ,{'OPENAI_API_KEY':'test-not-a-real-key'}),patch('src.llm.request.urlopen') as call:
            call.return_value=self.response('SKU-9999 needs action.',['SKU-9999'])
            with self.assertRaisesRegex(LLMUnavailable,'grounding'):Explainer().answer(retrieve(self.bundle,'supply'),'?')

    def test_provider_failure_is_not_leaked(self):
        with patch.dict(os.environ,{'OPENAI_API_KEY':'test-not-a-real-key'}),patch('src.llm.request.urlopen') as call:
            call.side_effect=HTTPError('url',429,'private provider details',{},None)
            with self.assertRaisesRegex(LLMUnavailable,'HTTP 429') as raised:Explainer().answer(retrieve(self.bundle,'supply'),'?')
            self.assertNotIn('private provider details',str(raised.exception))

if __name__=='__main__':unittest.main()
