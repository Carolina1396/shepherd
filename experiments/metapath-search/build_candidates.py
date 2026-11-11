"""Construct TRAPI treatment predictions using preserved two-edge support graphs."""
import hashlib

def build(g,disease,records):
    nodes={};edges={};aux={};support={}
    for record in records:
        for drug,mid,d,e1,e2 in record['paths']:
            curie=g.curie(drug)
            for n in (drug,mid,d): nodes[g.curie(n)]=g.node(n)
            ids=[]
            for pos in (e1,e2):
                eid,edge=g.edge(pos);edges[eid]=edge;ids.append(eid)
            aid='path-'+hashlib.sha256('|'.join(ids).encode()).hexdigest()
            aux[aid]={'edges':ids};support.setdefault(curie,set()).add(aid)
    results=[]
    for drug,graphs in sorted(support.items()):
        eid='prediction-'+hashlib.sha256((drug+'|'+disease).encode()).hexdigest()
        edges[eid]={'subject':drug,'object':disease,'predicate':'biolink:treats',
                    'knowledge_level':'prediction','agent_type':'computational_model',
                    'attributes':[{'attribute_type_id':'biolink:support_graphs','value':sorted(graphs)}],
                    'sources':[{'resource_id':'infores:shepherd-aragorn','resource_role':'primary_knowledge_source'}]}
        results.append({'node_bindings':{'drug':{'ids':[drug]},'disease':{'ids':[disease]}},
                        'analyses':[{'resource_id':'infores:shepherd-aragorn','edge_bindings':{'e0':{'ids':[eid]}}}]})
    msg={'query_graph':{'nodes':{'drug':{'categories':['biolink:ChemicalEntity']},
         'disease':{'ids':[disease],'categories':['biolink:DiseaseOrPhenotypicFeature']}},
         'edges':{'e0':{'subject':'drug','object':'disease','predicates':['biolink:treats'],'knowledge_type':'inferred'}}},
         'knowledge_graph':{'nodes':nodes,'edges':edges},'results':results}
    if aux:msg['auxiliary_graphs']=aux
    return msg


def build_service(disease,records):
    """Use only bound service-returned evidence, never synthesize cross-result paths."""
    from copy import deepcopy
    class Evidence:
        def __init__(self):self.nodes={};self.edges={}
        def curie(self,n):return n
        def node(self,n):return deepcopy(self.nodes[n])
        def edge(self,e):return e,deepcopy(self.edges[e])
    g=Evidence()
    for record in records:
        kg=record['knowledge_graph']
        for path in record['paths']:
            for n in path[:3]:
                value=kg['nodes'][n]
                if n in g.nodes and g.nodes[n]!=value:raise ValueError('Conflicting node evidence: '+n)
                g.nodes[n]=value
            for eid in path[3:]:
                value=kg['edges'][eid]
                if eid in g.edges and g.edges[eid]!=value:raise ValueError('Conflicting edge evidence: '+eid)
                g.edges[eid]=value
    return build(g,disease,records)
