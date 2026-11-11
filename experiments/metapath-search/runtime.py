"""Read-only fingerprint of the local ranking workers and dataset mounts."""
import json,subprocess,hashlib
from pathlib import Path

def capture(root):
    names=['shepherd_server','aragorn_lookup','merge_message','finish_query','filtered_retriever','aragorn_omnicorp','aragorn_score','sort_results_score','filter_results_top_n','filter_kgraph_orphans']
    result={}
    for name in names:
        d=json.loads(subprocess.check_output(['docker','inspect','shepherd-autoresearch-'+name+'-1'],text=True))[0]
        if not d['State']['Running']:raise ValueError(name+' is not running')
        # Never capture secrets from full environment/config output.
        env={x.split('=',1)[0]:x.split('=',1)[1] for x in d['Config'].get('Env',[]) if '=' in x}
        result[name]={'image':d['Image'],'command':d['Config']['Cmd'],
                      'settings':{k:v for k,v in env.items() if (k.startswith('OMNICORP_') and not k.endswith('_URL')) or k in ('KG_RETRIEVAL_URL','SYNC_KG_RETRIEVAL_URL','CALLBACK_HOST','GANDALF_HOST','GANDALF_PORT','TIER0__GANDALF__HOST','TIER0__GANDALF__PORT')},
                      'mounts':[{k:m[k] for k in ('Source','Destination','RW')} for m in d['Mounts']]}
    lookup=result['aragorn_lookup']['settings'].get('KG_RETRIEVAL_URL','')
    if lookup!='http://filtered_retriever:8080/asyncquery':raise ValueError('Lookup worker is not routed to filtered Retriever')
    backend=result['filtered_retriever']['settings']
    if backend.get('TIER0__GANDALF__PORT')!='56430' or backend.get('TIER0__GANDALF__HOST')!='http://host.docker.internal':raise ValueError('Retriever is not routed to filtered Gandalf')
    adapter=root/'local_setup/filtered_retriever/gandalf_driver.py'
    result['filtered_retriever']['adapter_sha256']=hashlib.sha256(adapter.read_bytes()).hexdigest()
    result['datasets']={}
    for name in ('curies.lmdb','shared_counts.lmdb'):
        s=(root/'omnicorp_lmdb'/name).stat()
        result['datasets'][name]={'bytes':s.st_size,'mtime_ns':s.st_mtime_ns}
    return result
