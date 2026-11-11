"""Compare complete, protocol-matched validation runs; never modifies candidates."""
import argparse,json
from pathlib import Path

def compare(old,new):
    ma=json.load((old/'manifest.json').open());mb=json.load((new/'manifest.json').open())
    a=json.load((old/'summary.json').open());b=json.load((new/'summary.json').open())
    for key in ('config','inputs','code','mode','batch','diseases','runtime','retrieval_metadata'):
        if ma.get(key)!=mb.get(key):raise ValueError('Incomparable runs: '+key)
    if not a['eligible_for_selection'] or not b['eligible_for_selection']:raise ValueError('Both runs must be complete full ranked validation')
    delta=b['metrics']['macro_hits_at_10']-a['metrics']['macro_hits_at_10']
    keep=delta>0 or (delta==0 and len(mb['templates']['templates'])<len(ma['templates']['templates']))
    return {'decision':'keep' if keep else 'discard','macro_hits_at_10_delta':delta,
            'incumbent':str(old),'candidate':str(new),'note':'Single fixed validation comparison, not statistical significance.'}
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('incumbent',type=Path);p.add_argument('candidate',type=Path);a=p.parse_args()
    print(json.dumps(compare(a.incumbent,a.candidate),indent=2))
