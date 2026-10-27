"""Build notebook 05; execute it afterward to save actual outputs."""
import json
from pathlib import Path
import textwrap

ROOT = Path(__file__).resolve().parents[2]
cells = []


def cell(kind, source, visible=False):
    item = {'cell_type': kind, 'metadata': {}, 'source': textwrap.dedent(source).strip() + '\n',
            'id': f'global-treats-{len(cells):02d}'}
    if kind == 'code':
        item.update(execution_count=None, outputs=[])
        item['metadata']['jupyter'] = {'source_hidden': not visible}
    cells.append(item)


cell('markdown', '''
# 05 · Recover all treatment pairs after removing every scoped `treats` edge

For each disease, can **Gandalf walks** and **local ARAGORN rules** retrieve the
chemicals connected to it by `biolink:treats` in the original graph?

**Targets:** every unique original `Drug / ChemicalEntity / SmallMolecule → treats → Disease`
pair, using explicit stored categories. Duplicate evidence records count as one pair.
There is no training/validation/test split in this experiment: all eligible pairs are targets.

**Shared graph:** remove every exact `biolink:treats` record between those chemical
categories and `Disease`, in **both directions**, before either method runs.
This also removes treatment edges previously retained as training evidence.
Other predicates, including `in_clinical_trials_for` and
`treats_or_applied_or_studied_to_treat`, remain. `treats` between categories outside
this scope also remains. A phenotype-only node does not qualify as `Disease`.

**Recovery:** the expected chemical appears anywhere in the graph retrieved for its
disease. Every target stays in the denominator, including isolated and unrecovered
chemicals. This measures graph coverage, not ranked prediction accuracy.
''')
cell('code', '''
RUN_NAME = 'global_treats_recovery_001'
WORKERS = 8
TOP_N = 10
''', True)
cell('markdown', '''
## Run or load the complete comparison

The first run scans the original source and runs both methods for every target disease.
Interrupted runs resume from verified per-disease artifacts. Completed results are
loaded from the cache; table hashes and implementation hashes are checked below.
The runner independently verifies the full mask, preserved evidence, saved graphs,
and recomputed recovery. See the [protocol and reproduction commands](../pilot/global_treats_recovery/README.md).

Gandalf uses 1,000 three-step attempts per disease, with no repeated node within a
walk and no `subclass_of` edges; only completed walks are collected. ARAGORN uses
the same 18 templates as notebook 04 plus the direct lookup, with five seconds per
query. Both have a 3,000-edge ceiling. No answer labels guide retrieval or budget selection.
''')
cell('code', '''
from pathlib import Path
import hashlib, json, subprocess
import pandas as pd
from IPython.display import display, Markdown

ROOT = next(p / 'experiments/ultra' for p in (Path.cwd(), *Path.cwd().parents)
            if (p / 'experiments/ultra/download.json').exists())
OUT = ROOT / 'pilot/results' / RUN_NAME
read = lambda p: json.loads(p.read_text())
def digest(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()

if not (OUT / 'summary.json').exists():
    command = [str(ROOT / '.venv/bin/python'), '-B', '-u',
               str(ROOT / 'pilot/global_treats_recovery/experiment.py'),
               '--output', str(OUT), '--workers', str(WORKERS)]
    if (OUT / 'settings.json').exists():
        command.append('--resume')
    subprocess.run(command, check=True)
summary = read(OUT / 'summary.json')
settings = read(OUT / 'settings.json')
assert summary['complete'] and summary['evaluated_pairs'] == summary['expected_pairs']
assert digest(OUT / 'settings.json') == summary['settings_sha256']
for name, expected in summary['outputs_sha256'].items():
    assert digest(OUT / name) == expected
for name, expected in settings['source_sha256'].items():
    assert digest(ROOT / name) == expected, f'Implementation changed: {name}'
assert summary['mask']['remaining_scoped_treats_records'] == 0
assert summary['saved_graphs_and_recovery_verified']
display(Markdown(f"**Complete:** {summary['expected_pairs']:,} target pairs across "
                 f"{summary['total_diseases']:,} diseases."))
''')
cell('markdown', '## Verify what was removed')
cell('code', '''
m = summary['mask']
display(pd.DataFrame([
    {'Measure': 'Unique chemical → treats → Disease targets', 'Count': summary['expected_pairs']},
    {'Measure': 'Eligible chemical candidate nodes', 'Count': settings['candidate_count']},
    {'Measure': 'Source evidence records, all predicates', 'Count': m['source_evidence_records']},
    {'Measure': 'Scoped treats evidence records removed', 'Count': m['removed_evidence_records']},
    {'Measure': 'Scoped treats evidence records remaining', 'Count': m['remaining_scoped_treats_records']},
    {'Measure': 'Treats records remaining outside category scope', 'Count': m['remaining_treats_records_other_categories']},
]))
''')
cell('markdown', '''
## Recovery of all original eligible treatment pairs

The primary metric is identical for both methods. Explicit ARAGORN answer bindings
are a separate diagnostic because a chemical can also appear as an intermediate node.
''')
cell('code', '''
names = {'gandalf_walks': 'Gandalf walks', 'aragorn_rules': 'Local ARAGORN'}
rows = []
for key, name in names.items():
    v = summary['results'][key]
    assert v['answer_pairs'] == summary['expected_pairs']
    rows.append({'Method': name,
                 'Recovered / expected': f"{v['answers_reached']:,} / {v['answer_pairs']:,}",
                 'Recovery': f"{v['answer_coverage']:.2%}",
                 'Mean graph edges': round(v['mean_edges'], 1),
                 'Empty graphs': v['empty_graphs']})
display(pd.DataFrame(rows))
ar = summary['results']['aragorn_rules']
display(Markdown(f"ARAGORN explicitly bound **{ar['answers_bound']:,}** expected pairs "
                 f"(**{ar['answers_bound']/summary['expected_pairs']:.2%}**)."))
''')
cell('markdown', '## Which answers overlap?')
cell('code', '''
groups = summary['paired_recovery']
display(pd.DataFrame([{'Recovered by': label, 'Pairs': groups.get(key, 0)}
    for key, label in [('both', 'Both methods'), ('gandalf_only', 'Gandalf only'),
                       ('aragorn_only', 'ARAGORN only'), ('neither', 'Neither')]]))
assert sum(groups.values()) == summary['expected_pairs']
''')
cell('markdown', '''
## Rule execution and contributions

All 18 rules are attempted for every disease, including rules whose required
treatment edges have been removed. Counts below refer to expected pairs explicitly
bound by retained complete matches; they overlap across rules. Query predicates may
expand through Biolink, so a template mentioning `treats` need not use an exact
stored `biolink:treats` edge. Errors and timeouts, if present, remain visible here.
''')
cell('code', '''
display(pd.DataFrame([{'Status': k, 'Queries': v} for k, v in summary['rule_status_counts'].items()]))
display(Markdown(f"**{summary['bounded_rule_queries']:,}** rule queries had bounded results. "
                 f"Gandalf completed **{summary['completed_walks']:,} / {summary['attempted_walks']:,}** attempts."))
rules = pd.read_csv(OUT / 'per_rule.csv', dtype={'rule_id': str})
contributions = rules.groupby('rule_id', as_index=False).agg(
    queries=('disease', 'size'), expected_pairs_bound=('expected_pairs_bound', 'sum'))
display(contributions.sort_values(['expected_pairs_bound', 'rule_id'], ascending=[False, True]).head(TOP_N))
''')
cell('markdown', '''
## Inspect individual targets

The complete table includes every target, including misses. Adjust the filter to
inspect disagreements. IDs refer to the original graph.
''')
cell('code', '''
pairs = pd.read_csv(OUT / 'pair_recovery.csv')
assert len(pairs) == summary['expected_pairs']
assert not pairs.duplicated(['chemical', 'disease']).any()
display(pairs.head(TOP_N))
# Example: pairs[pairs['group'].eq('gandalf_only')].head(TOP_N)
''', True)
cell('markdown', '''
**Interpretation:** this experiment tests recovery after globally removing the exact
target predicate within the requested categories. Retained treatment-related
predicates can still expose a target through one hop. Realized graph sizes can differ
despite the shared edge ceiling. This is one-seed retrieval coverage across all
original targets; it does not establish treatment effectiveness or ranked accuracy.
Notebook 04 uses a different mask and evaluation population, so its percentages are
not a controlled before/after estimate of the masking effect.
''')

notebook = {'cells': cells, 'metadata': {
    'kernelspec': {'display_name': 'Python 3', 'language': 'python', 'name': 'python3'},
    'language_info': {'name': 'python', 'file_extension': '.py', 'mimetype': 'text/x-python'}},
    'nbformat': 4, 'nbformat_minor': 5}
path = ROOT / 'notebooks/05_global_treats_recovery.ipynb'
path.write_text(json.dumps(notebook, indent=1) + '\n')
print(path)
