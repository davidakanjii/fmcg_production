"""Run after configuring .env. Makes THREE real provider calls using the supplied data."""
import json
from src.data import ROOT
from src.llm import Explainer,retrieve,LLMUnavailable
from server import load_env

def main():
    load_env();b=json.loads((ROOT/'artifacts/dashboard.json').read_text());service=Explainer()
    cases=[('supply','SKU-1000','Explain this item flag.','explanation'),
           ('manufacturing','MCH-208','Explain this machine status.','explanation'),
           ('supply',None,'Which SKUs may run out before replenishment?','qa')]
    for kind,entity,question,mode in cases:
        evidence=retrieve(b,kind,question=question,entity_id=entity)
        try:result=service.answer(evidence,question,mode)
        except LLMUnavailable as e:raise SystemExit(str(e))
        print(json.dumps(result,indent=2))
    print('Transport and reference checks passed. Manually compare all numerical claims with the app before presenting.')

if __name__=='__main__':main()
