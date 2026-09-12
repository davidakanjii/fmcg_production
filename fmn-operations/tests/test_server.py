import json
import os
import threading
import unittest
from http.server import ThreadingHTTPServer
from urllib import request,error
from unittest.mock import patch
from server import make_handler
from src.data import ROOT

class HTTPTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        bundle=json.loads((ROOT/'artifacts/dashboard.json').read_text())
        cls.server=ThreadingHTTPServer(('127.0.0.1',0),make_handler(bundle))
        cls.thread=threading.Thread(target=cls.server.serve_forever,daemon=True);cls.thread.start()
        cls.url='http://127.0.0.1:'+str(cls.server.server_port)
    @classmethod
    def tearDownClass(cls):cls.server.shutdown();cls.server.server_close();cls.thread.join()
    def test_routes_and_exports(self):
        for path in ['/supply','/manufacturing','/validation','/app.js','/style.css','/health','/api/data','/api/export?kind=supply']:
            with request.urlopen(self.url+path) as r:self.assertEqual(r.status,200);self.assertGreater(len(r.read()),0)
    def test_secrets_are_not_served(self):
        for path in ['/.env','/src/llm.py','/../.env']:
            with self.assertRaises(error.HTTPError) as e:request.urlopen(self.url+path)
            self.assertEqual(e.exception.code,404)
    def test_csrf_required_and_ai_missing_state(self):
        body=json.dumps({'kind':'supply','id':'SKU-1000'}).encode()
        with self.assertRaises(error.HTTPError) as e:
            request.urlopen(request.Request(self.url+'/api/explain',data=body,headers={'Content-Type':'application/json'}))
        self.assertEqual(e.exception.code,403)
        with request.urlopen(self.url+'/api/status') as r:token=json.load(r)['csrf_token']
        with patch.dict(os.environ,{'OPENAI_API_KEY':''}),self.assertRaises(error.HTTPError) as e:
            request.urlopen(request.Request(self.url+'/api/explain',data=body,headers={'Content-Type':'application/json','X-CSRF-Token':token}))
        self.assertEqual(e.exception.code,503)

if __name__=='__main__':unittest.main()
