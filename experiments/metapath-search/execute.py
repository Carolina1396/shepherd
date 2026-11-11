"""Read-only exact-index executor preserving evidence positions and qualifiers."""
import json,pickle,sys,time
from collections import defaultdict
from pathlib import Path
import lmdb,msgpack,numpy as np
from template_format import matches_qualifiers,validate_template
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'metapath-feasibility'))
from pilot import Graph

class Executor(Graph):
    def __init__(self,root):
        super().__init__(root)
        self.pools=pickle.load((root/'edge_property_pools.pkl').open('rb'))
        for n in ('edge_quals_idx','edge_sources_idx','edge_kl_at_idx','rev_to_fwd'):
            setattr(self,n,np.load(root/(n+'.npy'),mmap_mode='r'))
        self.edge_env=lmdb.open(str(root/'edge_properties.lmdb'),readonly=True,lock=False,readahead=False)
        self.id_env=lmdb.open(str(root/'edge_ids.lmdb'),readonly=True,lock=False,readahead=False)
    def incident(self,node,edge,anchor):
        outgoing=edge['subject']==anchor
        offsets=self.fwd_offsets if outgoing else self.rev_offsets
        a,b=map(int,offsets[node:node+2]);positions=np.arange(a,b)
        targets=self.fwd_targets[a:b] if outgoing else self.rev_sources[a:b]
        predicates=self.fwd_predicates[a:b] if outgoing else self.rev_predicates[a:b]
        pid=self.meta['predicate_to_idx'].get(edge['predicate'])
        keep=predicates==pid if pid is not None else np.zeros(len(predicates),dtype=bool)
        positions=positions[keep];targets=targets[keep]
        if not outgoing: positions=self.rev_to_fwd[positions]
        result=[]
        for target,pos in zip(targets,positions):
            qualifiers=self.pools['quals_pool'][int(self.edge_quals_idx[pos])]
            if matches_qualifiers(qualifiers,edge): result.append((int(target),int(pos)))
        return result,b-a
    def lookup(self,template,disease,limits):
        validate_template(template);start=time.monotonic();paths=[];drugs=set();work=0;state='complete'
        d=self.idx(disease)
        if d is None:return {'state':'missing_endpoint','paths':[],'seconds':0,'edges_examined':0}
        de=template['edges']['disease_edge'];ce=template['edges']['drug_edge']
        neighbors,n=self.incident(d,de,'disease');work+=n
        mids=defaultdict(list)
        for m,pos in neighbors:
            if m!=d and template['intermediate_category'] in self.categories(m):mids[m].append(pos)
        for mid,ends in sorted(mids.items()):
            if work>limits['max_edges']:state='edge_limit';break
            if time.monotonic()-start>limits['seconds']:state='time_limit';break
            starts,n=self.incident(mid,ce,'intermediate');work+=n
            if work>limits['max_edges']:state='edge_limit';break
            for drug,pos in starts:
                if drug in (mid,d) or not self.drugs[drug]:continue
                for end in ends:
                    if len(paths)>=limits['max_paths'] or (drug not in drugs and len(drugs)>=limits['max_candidates']):
                        state='evidence_limit';break
                    drugs.add(drug);paths.append([drug,mid,d,pos,end])
                if state!='complete':break
            if state!='complete':break
        if work>limits['max_edges']:state='edge_limit'
        if time.monotonic()-start>limits['seconds'] and state=='complete':state='time_limit'
        return {'state':state,'paths':paths,'seconds':round(time.monotonic()-start,6),'edges_examined':work}
    def node(self,idx):
        return msgpack.unpackb(self.tx.get(int(idx).to_bytes(4,'big'),db=self.props),raw=False)
    def edge(self,pos):
        key=int(pos).to_bytes(4,'big')
        with self.id_env.begin() as tx:eid=tx.get(key).decode()
        with self.edge_env.begin() as tx:attrs=json.loads(tx.get(key))
        source=int(np.searchsorted(self.fwd_offsets,pos,side='right')-1)
        kl,at=self.pools['kl_at_pool'][int(self.edge_kl_at_idx[pos])]
        edge={'subject':self.curie(source),'object':self.curie(int(self.fwd_targets[pos])),
              'predicate':self.pred[int(self.fwd_predicates[pos])],
              'sources':self.pools['sources_pool'][int(self.edge_sources_idx[pos])],
              'knowledge_level':kl,'agent_type':at}
        if attrs:edge['attributes']=attrs
        qs=self.pools['quals_pool'][int(self.edge_quals_idx[pos])]
        if qs:edge['qualifiers']=qs
        return eid,edge
