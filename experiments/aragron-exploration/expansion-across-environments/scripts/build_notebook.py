"""Build the offline notebook from cached evidence; no HTTP requests are made.

Use --execute to run its display cells with IPython and embed outputs. No kernel
or nbformat dependency is needed; the file follows nbformat 4.5.
"""
import argparse
import sys
import json
from pathlib import Path
import textwrap

ROOT = Path(__file__).resolve().parent.parent
NOTEBOOKS = ROOT / 'notebooks'
cells = []


def md(source):
    cells.append({'cell_type': 'markdown', 'metadata': {}, 'source': textwrap.dedent(source).strip() + '\n'})


def code(source):
    cells.append({'cell_type': 'code', 'metadata': {}, 'execution_count': None, 'outputs': [],
                  'source': textwrap.dedent(source).strip() + '\n'})


md('''
# Ten treatment queries across ARAGORN environments

**Question:** When we ask the same ten treatment questions, do Development, CI/Staging,
Test and Production expand the same rules, find the same paths, and return the same chemicals?

Each request is **ChemicalEntity → inferred treats → one fixed disease/phenotype**.
We submit the original query once per environment. **Hosted ARAGORN** expands it,
retrieves the direct lookup plus its treatment rules, and merges the callbacks.
The workflow is `aragorn.lookup`: scoring and ranking are outside this experiment.

Tier 0 and no fallback are requested; subclass behavior stays at service defaults.
All existing graph edges remain visible. This is an environment comparison, not a holdout
recovery or clinical-validity evaluation. The ten targets are a documented convenience sample.

**Running this notebook is offline.** It reads saved evidence and does not submit queries.
''')
code('''
import json
from pathlib import Path
import sys
import pandas as pd
from IPython.display import display, HTML, Markdown
from html import escape

candidates = [p for base in (Path.cwd(), *Path.cwd().parents)
              for p in (base, base / 'experiments/aragron-exploration/expansion-across-environments',
                        base / 'expansion-across-environments')]
ROOT = next(p for p in candidates if (p / 'scripts/analyze.py').exists() and (p / 'config.json').exists())
RUN = ROOT / 'output/run_002'
sys.path.insert(0, str(ROOT / 'scripts'))
from analyze import expected_graphs, graph_key
report = json.loads((RUN / 'report.json').read_text())
config = json.loads((RUN / 'config.json').read_text())
cases = report['cases']
ENVIRONMENTS = [e['name'] for e in config['environments']]
LABELS = {'development': 'Development', 'ci_staging': 'CI / Staging', 'test': 'Test', 'production': 'Production'}
display(pd.DataFrame([report['overview']]))
print('A completed workflow can include rejected rule callbacks. Completion does not mean every rule succeeded.')
''')
md('''
## The ten questions

The first seven targets come from our earlier rule probes. The remaining three are the next
distinct targets in the existing seeded treatment-holdout cohort. We use only their target IDs;
the chemical end is open and no edges are removed. Names below come from the local graph.
''')
code('''
display(pd.DataFrame(config['targets']).rename(columns={'id':'Target ID', 'name':'Disease / phenotype', 'selection':'Why selected'}))
''')
md('''
## Where did each request run?

Application release, TRAPI version and Biolink version are separate fields.
The release files describe the advertised release; they do not establish a deployed image digest.
Template equality below preserves edge direction, categories, predicates and qualifier values,
after translating the known TRAPI 1.x/2.x qualifier encoding for comparison only.
''')
code('''
rows = []
for v in report['versions']:
    observations = [c for c in cases if c['environment'] == v['environment']]
    rows.append({'Environment': LABELS[v['environment']], 'ARAGORN URL': v['base_url'] + '/query',
                 'Release': v['application_version'], 'TRAPI': v['trapi_version'], 'Biolink': v['biolink_version'],
                 'Release treatment rules': v['release_rule_count'],
                 'Same 18 templates as Dev': v['same_ordered_semantic_templates_as_development'],
                 'Observed retrieval URL': ', '.join(sorted({u for c in observations for u in c['observed_retrieval_urls']})),
                 'Queries with Tier 0 execution logged': sum(c['tier0_execution_logged'] for c in observations)})
display(pd.DataFrame(rows))
print('Internal graph release remains unverified. The URL and live logs identify execution, not SERVER_MATURITY process variables.')
''')
md('''
## What exactly did we send?

For TRAPI 1.x releases, `log_level` must also be at the top level. Development reads
`parameters.log_level`. This is a logging adaptation; the query graph and lookup workflow
are identical. `run_001` preserves the four initial logging probes; `run_002` is the main comparison.
''')
code('''
for environment in ('development', 'production'):
    request = json.loads((RUN / environment / 'q01/request.json').read_text())
    display(HTML('<details><summary>' + LABELS[environment] + ' — exact first request</summary><pre>' +
                 escape(json.dumps(request, indent=2)) + '</pre></details>'))
''')
md('''
## Final chemical answers

These counts are **after ARAGORN merges and filters results**, including repeated-node filtering.
They include direct and inferred support. A chemical can have both. Raw rule callback counts,
shown later, are different quantities and can overlap.
''')
code('''
frame = pd.DataFrame([{k:c.get(k) for k in ['environment','query','target_name','final_result_count',
    'unique_chemical_count','direct_only','inferred_only','both','query_status','complete_for_answer_comparison']} for c in cases])
counts = frame.pivot(index=['query','target_name'], columns='environment', values='unique_chemical_count').reindex(columns=ENVIRONMENTS)
display(counts.rename(columns=LABELS).rename_axis(index=['Query','Disease / phenotype'], columns=None))
display(HTML('<details><summary>Direct / inferred support and completion for all 40 responses</summary>' + frame.to_html(index=False) + '</details>'))
''')
md('''
## Are the returned chemical IDs the same?

We compare the sets of exact returned CURIEs, not just counts. Jaccard is intersection / union;
1 means identical sets (including two empty sets). No additional synonym normalization is applied.
Comparisons are withheld if final response or callback observations are incomplete.
''')
code('''
comparisons = pd.DataFrame(report['answer_comparisons'])
summary = comparisons.groupby(['environment_a','environment_b'], sort=False).agg(
    comparable_targets=('complete_for_comparison','sum'), identical_answer_sets=('identical_answer_ids',lambda x: sum(v is True for v in x)),
    minimum_jaccard=('jaccard','min')).reset_index()
display(summary)
differences = comparisons[(comparisons.identical_answer_ids == False) | ~comparisons.complete_for_comparison]
if len(differences):
    display(differences)
else:
    print('All observed answer-ID sets match across all six environment pairs for all ten targets.')
''')
md('''
## Were all rules actually observed?

**Observed** means we matched a query graph logged by the running service to a release template.
It does not mean the rule had a match. A release containing 18 rules is not by itself proof
that all 18 were executed. Direct lookup is numbered 0 and is excluded from the 18-rule count.
''')
code('''
observation = pd.DataFrame([{'Environment': LABELS[e],
    'Queries with all 18 rule graphs observed': sum(c['observed_rule_count']==18 for c in cases if c['environment']==e),
    'Callbacks received (direct + rules)': sum(c['received_callbacks'] for c in cases if c['environment']==e),
    'Total final results': sum(c['final_result_count'] or 0 for c in cases if c['environment']==e),
    'Integrity errors': sum(len(c['integrity_errors']) for c in cases if c['environment']==e)} for e in ENVIRONMENTS])
display(observation)
rule_rows = [dict(environment=c['environment'],query=c['query'],target_name=c['target_name'],**r) for c in cases for r in c['rule_results'] if r['rule']]
rf = pd.DataFrame(rule_rows)
positive = rf.assign(positive=rf.raw_result_count.fillna(0)>0).pivot_table(index='rule',columns='environment',values='positive',aggfunc='sum').reindex(columns=ENVIRONMENTS)
display(Markdown('**Number of targets with a positive raw callback, per rule (out of ten):**'))
display(positive.rename(columns=LABELS))
print('These are pre-merge matches. A positive rule can contribute no final answers after filtering.')
rule_comparisons = pd.DataFrame(report.get('rule_comparisons', []))
if len(rule_comparisons):
    differing_rules = rule_comparisons[(rule_comparisons.identical_raw_counts == False) | (rule_comparisons.identical_outcomes == False)]
    print('Target/rule combinations with observations in all four environments:', int(rule_comparisons.complete_observation.sum()), 'of 190 (including direct lookup).')
    if len(differing_rules):
        display(differing_rules)
    else:
        print('No raw callback count or outcome differences among fully observed comparisons.')
''')
md('''
## Read each rule, its edges, and its outcome

Open a rule to see its required edges and qualifiers, followed by all ten target comparisons.
Each cell contains the raw callback count and its outcome. `invalid_predicate` and
`unsupported_pattern` are service rejections. `empty_callback_no_error_logged` means an empty
callback with no error observed; it is not graph-wide absence. `not_observed` means unknown.

A full-path count of zero does not tell us which individual edge is missing. This experiment
records the actual service expansions; it does not independently query every edge in isolation.
''')
code('''
release_rules = json.loads((RUN / 'development/release-rules.json').read_text())['{"predicate": "biolink:treats"}']
request = json.loads((RUN / 'development/q01/request.json').read_text())
graphs = expected_graphs(request, release_rules)
for number in range(1, len(release_rules)+1):
    graph = graphs[number]
    edge_rows = []
    for eid, edge in graph['edges'].items():
        edge_rows.append({'Edge':eid, 'From variable':edge['subject'],
            'From category':', '.join(graph['nodes'][edge['subject']].get('categories',[])),
            'Predicate':', '.join(edge.get('predicates',[])), 'To variable':edge['object'],
            'To category':', '.join(graph['nodes'][edge['object']].get('categories',[])),
            'Qualifiers':json.dumps(edge.get('constraints',{}).get('qualifiers',[]))})
    rule_cases = []
    for index, target in enumerate(config['targets'],1):
        row = {'Target':target['name']}
        for env in ENVIRONMENTS:
            case = next(c for c in cases if c['query']==f'q{index:02d}' and c['environment']==env)
            result = next((r for r in case['rule_results'] if r['rule']==number), None)
            row[LABELS[env]] = ('unknown' if result is None else
                f"{result['raw_result_count'] if result['raw_result_count'] is not None else '?'} — {', '.join(result['outcomes'])}")
        rule_cases.append(row)
    body = pd.DataFrame(edge_rows).to_html(index=False) + pd.DataFrame(rule_cases).to_html(index=False)
    display(HTML(f'<details><summary><b>Rule {number}</b> — {len(edge_rows)} required edges</summary>{body}</details>'))
''')
md('''
## Inspect one query in detail

Change `QUERY` below to `q01` … `q10`. For each environment, inspect final chemical answers,
callback counts and warnings. Saved `response.json` contains the complete returned knowledge graph,
auxiliary support graphs and logs. Per-rule callback graphs are in `report.json`.
Final merged evidence generally does not retain a unique originating rule label.
''')
code('''
QUERY = 'q01'
for case in [c for c in cases if c['query']==QUERY]:
    title = LABELS[case['environment']] + ' — ' + case['target_name']
    counts = pd.DataFrame(case['rule_results'])[['rule','expanded_graph_observed','raw_result_count','outcomes']]
    answers = pd.DataFrame(case['answers'])
    warnings = pd.DataFrame(case['warnings_errors'])
    html = counts.to_html(index=False) + '<h4>Final chemical answers</h4>' + answers.to_html(index=False)
    html += '<details><summary>Warnings / errors</summary>' + warnings.to_html(index=False) + '</details>'
    display(HTML('<details><summary><b>' + escape(title) + '</b></summary>' + html + '</details>'))
''')
md('''
## Why might final answers differ when raw counts match?

The saved release source has a relevant difference in the filter for frequently reused
intermediate nodes. Older releases compare the QEdge field `qualifiers`, even though their
rule templates store `qualifier_constraints`; absent values therefore compare equal.
Development compares `constraints.qualifiers`, including their actual values.

The offline diagnostic below runs only the inspected graph-selection function from each saved
release source. It identifies variables that would be considered for filtering. The filter's
threshold is more than 10 results through a candidate intermediate node.
This is a **possible explanation**, not a causal replay of the live callbacks: identical raw
counts do not prove identical raw paths, and we do not have the raw callback bodies.
''')
code('''
path = RUN / 'merge-filter-diagnostic.json'
if path.exists():
    diagnostic = json.loads(path.read_text())
    display(pd.DataFrame(diagnostic['differences']))
    for limitation in diagnostic['limitations']:
        print('•', limitation)
else:
    print('Run diagnose_filters.py offline to generate the optional release-source diagnostic.')
''')

md('''
## Limits and reproducibility

Rule matches demonstrate returned evidence for these targets. This is not a measurement of all
treatment-rule paths in a graph, nor evidence that returned chemicals are effective treatments.
The service may impose additional limits. “Completed” describes the outer workflow and can coexist
with rule-level validation failures. Inspect the retained warnings before interpreting coverage.

The main run retains 40 exact requests/responses, status checks, release snapshots, response hashes,
`results.csv`, `rules.csv`, and `answer_overlap.csv`. The runner skips existing submission markers,
including uncertain network outcomes; it never automatically repeats an uncertain POST.
''')
code('''
for limitation in report['limitations']:
    print('•', limitation)
print('Saved run:', RUN.resolve())
print('Offline re-audit: experiments/ultra/.venv/bin/python -B experiments/aragron-exploration/expansion-across-environments/scripts/run.py')
print('New live run: add --submit --output <new-directory>; this submits up to 40 hosted queries.')
''')


def main(notebook_name='01_ten_queries_all_environments.ipynb'):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--execute', action='store_true')
    args = parser.parse_args()
    for i, cell in enumerate(cells):
        cell['id'] = f'cell-{i:02d}'
    if args.execute:
        from IPython.core.interactiveshell import InteractiveShell
        from IPython.utils.capture import capture_output
        shell = InteractiveShell.instance()
        shell.user_ns['__name__'] = '__main__'
        count = 0
        for cell in cells:
            if cell['cell_type'] != 'code':
                continue
            count += 1
            with capture_output() as captured:
                result = shell.run_cell(cell['source'])
            if result.error_before_exec or result.error_in_exec:
                raise RuntimeError(f'Notebook cell {count} failed: {captured.stdout} {captured.stderr}')
            outputs = []
            if captured.stdout:
                outputs.append({'output_type':'stream','name':'stdout','text':captured.stdout})
            if captured.stderr:
                outputs.append({'output_type':'stream','name':'stderr','text':captured.stderr})
            for item in captured.outputs:
                outputs.append({'output_type':'display_data','data':item.data,'metadata':item.metadata})
            cell.update(outputs=outputs, execution_count=count)
    notebook = {'nbformat':4,'nbformat_minor':5,'metadata':{
        'kernelspec': {'display_name':'Python 3','language':'python','name':'python3'},
        'language_info': {'name':'python','version':sys.version.split()[0]}},'cells':cells}
    NOTEBOOKS.mkdir(parents=True, exist_ok=True)
    path = NOTEBOOKS / notebook_name
    path.write_text(json.dumps(notebook, indent=1) + '\n')
    print(f'Wrote {path}; {sum(c["cell_type"]=="code" for c in cells)} code cells; executed={args.execute}')


if __name__ == '__main__':
    main()
