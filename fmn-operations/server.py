"""Local-only HTTP app. Run python server.py, then open http://127.0.0.1:8765.

Set HOST=0.0.0.0 and PORT via environment variables to run on a public host.
"""
import csv
import io
import json
import mimetypes
import os
import secrets
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs
from src.data import ROOT
from src.llm import Explainer, LLMUnavailable, retrieve, compact, snapshot_bundle

def load_env():
    path=ROOT/'.env'
    if path.exists():
        for line in path.read_text(encoding='utf-8-sig').splitlines():
            line=line.strip()
            if line and not line.startswith('#') and '=' in line:
                key,value=line.split('=',1)
                os.environ.setdefault(key.strip(),value.strip().strip('"').strip("'"))

def make_handler(bundle,explainer=None):
    explainer=explainer or Explainer();csrf=secrets.token_urlsafe(32)
    class Handler(BaseHTTPRequestHandler):
        def log_message(self,fmt,*args):
            # Requests only; no questions, API credentials or response content in logs.
            pass

        def respond(self,code,payload,ctype='application/json; charset=utf-8',extra=None):
            data=json.dumps(payload,allow_nan=False).encode() if ctype.startswith('application/json') else payload
            self.send_response(code)
            self.send_header('Content-Type',ctype);self.send_header('Content-Length',str(len(data)))
            self.send_header('Cache-Control','no-store');self.send_header('X-Content-Type-Options','nosniff')
            self.send_header('Content-Security-Policy',"default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'")
            for k,v in (extra or {}).items():self.send_header(k,v)
            self.end_headers();self.wfile.write(data)

        def do_GET(self):
            u=urlparse(self.path)
            if u.path=='/api/status':
                return self.respond(200,dict(ai_configured=bool(os.getenv('OPENAI_API_KEY','').strip()),
                    model=os.getenv('OPENAI_MODEL','gpt-4.1-mini'),csrf_token=csrf))
            if u.path=='/api/data':return self.respond(200,bundle)
            if u.path=='/health':return self.respond(200,{'ok':True})
            if u.path=='/api/export':
                kind=parse_qs(u.query).get('kind',[''])[0]
                if kind not in ('supply','manufacturing'):return self.respond(400,{'error':'Unknown app'})
                replay=parse_qs(u.query).get('as_of',[''])[0]
                if replay and (kind!='manufacturing' or replay not in bundle.get('manufacturing_replays',{})):
                    return self.respond(400,{'error':'Unknown replay timestamp'})
                selected_rows=bundle['manufacturing_replays'][replay] if replay else bundle[kind]
                rows=[{k:v for k,v in compact(r).items() if not isinstance(v,(dict,list))} for r in selected_rows]
                buffer=io.StringIO(newline='');writer=csv.DictWriter(buffer,fieldnames=list(rows[0]));writer.writeheader();writer.writerows(rows)
                return self.respond(200,buffer.getvalue().encode('utf-8-sig'),'text/csv; charset=utf-8',
                    {'Content-Disposition':f'attachment; filename="{kind}_attention.csv"'})
            files={'/':'index.html','/supply':'index.html','/manufacturing':'index.html','/validation':'index.html',
                   '/app.js':'app.js','/style.css':'style.css'}
            if u.path not in files:return self.respond(404,{'error':'Not found'})
            p=ROOT/'web'/files[u.path]
            return self.respond(200,p.read_bytes(),mimetypes.guess_type(p)[0]+'; charset=utf-8')

        def do_POST(self):
            if self.path not in ('/api/explain','/api/ask'):return self.respond(404,{'error':'Not found'})
            if self.headers.get('X-CSRF-Token')!=csrf:return self.respond(403,{'error':'Refresh the app before requesting AI.'})
            if self.headers.get('Content-Type','').split(';')[0]!='application/json':return self.respond(415,{'error':'JSON required'})
            try:
                length=int(self.headers.get('Content-Length',0))
                if length<=0 or length>8192:raise ValueError('Request must be between 1 and 8192 bytes.')
                body=json.loads(self.rfile.read(length));kind=body.get('kind')
                replay=body.get('as_of')
                evidence_bundle=snapshot_bundle(bundle,kind,replay)
                if self.path=='/api/explain':
                    entity=body.get('id')
                    if not isinstance(entity,str):raise ValueError('Choose an item.')
                    evidence=retrieve(evidence_bundle,kind,entity_id=entity)
                    question='Explain the flag, evidence and suggested next action for '+entity+'.'
                    mode='explanation'
                else:
                    question=body.get('question','')
                    if not isinstance(question,str) or not 3<=len(question.strip())<=1000:raise ValueError('Enter a question of 3 to 1000 characters.')
                    evidence=retrieve(evidence_bundle,kind,question=question);mode='qa'
                return self.respond(200,explainer.answer(evidence,question,mode))
            except (ValueError,TypeError,AttributeError) as e:return self.respond(400,{'error':str(e) or 'Invalid request'})
            except LLMUnavailable as e:return self.respond(503,{'error':str(e)})
            except Exception:return self.respond(500,{'error':'Unexpected error. Check the server setup and retry.'})
    return Handler

def main():
    load_env()
    path=ROOT/'artifacts/dashboard.json'
    if not path.exists():
        raise SystemExit('Run python train.py first to build the model and evidence artifacts.')
    bundle=json.loads(path.read_text(encoding='utf-8'))
    host=os.getenv('HOST','127.0.0.1');port=int(os.getenv('PORT','8765'))
    server=ThreadingHTTPServer((host,port),make_handler(bundle))
    print(f'FMN Operations: http://{host}:{port}/supply',flush=True)
    print(f'Plant app: http://{host}:{port}/manufacturing',flush=True)
    try:server.serve_forever()
    except KeyboardInterrupt:pass
    finally:server.server_close()

if __name__=='__main__':main()
