"""Build the analysis notebook using the standard notebook JSON format."""
import json
from pathlib import Path
import textwrap

ROOT = Path(__file__).resolve().parents[2]
cells = []


def cell(kind, source, visible=False):
    item = {'cell_type': kind, 'metadata': {}, 'source': textwrap.dedent(source).strip() + '\n',
            'id': f'metapaths-{len(cells):02d}'}
    if kind == 'code':
        item.update(execution_count=None, outputs=[])
        item['metadata']['jupyter'] = {'source_hidden': not visible}
    cells.append(item)


def md(source):
    cell('markdown', source)


def code(source, visible=False):
    cell('code', source, visible)




md(r"""
# 04 · Top metapaths: Gandalf vs local ARAGORN

Same dataset and **treats-only mask**: held-out direct `treats` edges are removed; other direct predicates remain.

Ranked by **distinct expected chemical–disease pairs recovered**, not pattern frequency. Counts overlap across rows. Recovery means the chemical appears in the retrieved graph, not ranking accuracy.
""")

code(r"""
SPLIT = 'validation'  # 'test' is exploratory.
TOP_N = 5
""", visible=True)

code(r"""
from pathlib import Path
import json, hashlib, html
import pandas as pd
from IPython.display import display, HTML, Markdown

ROOT = next(p / 'experiments/ultra' for p in (Path.cwd(), *Path.cwd().parents)
            if (p / 'experiments/ultra/download.json').exists())
OUT = ROOT / 'pilot/results/chemical_metapaths_001'
WALKS = ROOT / 'pilot/results/chemical_walks_treats_only_001'
read = lambda p: json.loads(p.read_text())
assert SPLIT in ('validation','test') and isinstance(TOP_N,int) and TOP_N > 0
manifest = read(OUT / 'manifest.json')
for name in ('answer_metapaths.csv','rule_catalog.json'):
    assert hashlib.sha256((OUT / name).read_bytes()).hexdigest() == manifest['outputs'][name]
assert hashlib.sha256((WALKS / 'summary.json').read_bytes()).hexdigest() == manifest['inputs'][str((WALKS / 'summary.json').relative_to(ROOT))]
comparison = read(WALKS / 'summary.json')
patterns = pd.read_csv(OUT / 'answer_metapaths.csv')
rules = read(OUT / 'rule_catalog.json')

def table(frame):
    markup = frame.to_html(index=False,escape=True).replace(r'\n', '<br>')
    display(HTML(markup.replace('<table ', '<table style="text-align:left" ')))

rows = []
for key, name in [('gandalf_walks','Gandalf walks'),('aragorn_rules','Local ARAGORN')]:
    v = comparison['results'][key][SPLIT]
    rows.append({'Method':name, 'Recovered / expected':f"{v['answers_reached']:,} / {v['answer_pairs']:,}",
                 'Recovery':f"{v['answer_coverage']:.2%}", 'Mean graph connections':round(v['graph_sizes']['edges']['mean'])})
display(Markdown(f'**{SPLIT.title()} comparison**'))
table(pd.DataFrame(rows))
""")

md(r"""
## Gandalf: top observed metapaths

No fixed rules: these are observed 1–3 step prefixes of completed three-edge walks. Arrows preserve stored edge direction; categories are descriptive and qualifiers are not used by the sampler.
""")

code(r"""
top = patterns[patterns.split.eq(SPLIT)].sort_values(
    ['distinct_answer_pairs','metapath'],ascending=[False,True]).head(TOP_N)
table(top[['metapath','distinct_answer_pairs']].rename(columns={
    'metapath':'Observed metapath', 'distinct_answer_pairs':'Expected pairs recovered'}))
""")

md(r"""
## Local ARAGORN: top rule patterns

Every listed edge and qualifier must match together; some rules are triangles rather than single paths. **A = answer chemical; D = query disease/phenotype.** Intermediate node types are shown in each row. Brackets give object aspect/direction qualifiers; query predicates can expand through Biolink.
""")

code(r"""
short = lambda s: s.removeprefix('biolink:')
alias = lambda n: {'$source':'A','$target':'D'}.get(n,n.upper())

def motif(q):
    lines = []
    for e in q['edges'].values():
        p = '|'.join(map(short,e['predicates']))
        qualifiers = e.get('constraints',{}).get('qualifiers',[])
        if qualifiers:
            p += ' [' + ' OR '.join(', '.join(
                (str(v) if k in ('biolink:object_aspect_qualifier','biolink:object_direction_qualifier')
                 else f'{short(k)}={v}') for k,v in qc.items()) for qc in qualifiers) + ']'
        lines.append(f"{alias(e['subject'])} —{p}→ {alias(e['object'])}")
    return '\n'.join(lines)

ranked = sorted((r for r in rules if r[SPLIT]['answers_bound']>0),
                key=lambda r:(-r[SPLIT]['answers_bound'],r['rule_id']))[:TOP_N]
rows = []
for r in ranked:
    q = r['query_graph']
    rows.append({'Rule':r['rule_id'], 'Required pattern':motif(q),
                 'Intermediate types':'; '.join(f"{alias(n)}: {'|'.join(map(short,v['categories']))}"
                                               for n,v in q['nodes'].items() if n not in ('$source','$target')),
                 'Expected pairs recovered':r[SPLIT]['answers_bound']})
table(pd.DataFrame(rows))
assert len(rules)==18
""")

md(r"""
**What differs:** Gandalf can recover answers through a single retained treatment-related edge. ARAGORN requires a complete rule pattern—for example, rule 5 also needs a second disease and a `has_phenotype` link. Gandalf's larger retrieved graphs also affect recovery.

[Methods, verification, and full cached results](../pilot/metapath_analysis/README.md)
""")

notebook = {'cells': cells, 'metadata': {'kernelspec': {'display_name': 'Python 3', 'language': 'python', 'name': 'python3'},
             'language_info': {'name': 'python', 'file_extension': '.py', 'mimetype': 'text/x-python'}},
             'nbformat': 4, 'nbformat_minor': 5}
path = ROOT / 'notebooks/04_aragorn_gandalf_metapaths.ipynb'
path.write_text(json.dumps(notebook, indent=1) + '\n')
print(path)
