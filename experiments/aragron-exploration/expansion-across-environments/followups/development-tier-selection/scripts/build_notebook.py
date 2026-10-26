"""Build the offline tier-selection notebook; --execute embeds its saved-data outputs."""
from pathlib import Path
import sys

HERE = Path(__file__).resolve().parent
FOLLOWUP_ROOT = HERE.parent
EXPERIMENT_ROOT = FOLLOWUP_ROOT.parent.parent
sys.path.insert(0, str(EXPERIMENT_ROOT / 'scripts'))
import build_notebook as shared

shared.NOTEBOOKS = FOLLOWUP_ROOT / 'notebooks'
shared.cells.clear()
md, code = shared.md, shared.code

md('''
# Does removing the Tier 0 restriction recover more ARAGORN rules?

We reran the same ten original **ChemicalEntity → inferred treats → fixed disease/phenotype**
questions against hosted **Development ARAGORN**. ARAGORN performs the expansion itself;
we do not submit eighteen manually expanded queries. The workflow is `aragorn.lookup`
(expansion, retrieval and merge; no scoring). All graph edges remain available.

Two request variants distinguish **using defaults** from **actually requesting another tier**:

| Variant | `tier` | `tiers` | `tier_fallback` |
|---|---|---|---|
| Previous Tier 0 baseline | 0 | [0] | false |
| Default rerun | omitted | omitted | omitted |
| Explicit Tier 1 rerun | 1 | [1] | false |

Retriever accepts one tier per request. Omitting tier controls defaults to Tier 0.
Fallback concerns backend availability; it does **not** automatically try another tier
when a rule is rejected or returns zero paths. Explicit Tier 1 with fallback disabled
is needed here to avoid mistaking a fallback Tier 0 answer for a Tier 1 answer.

**Running this notebook is offline.** It reads saved requests, responses and logs.
Graph release is unknown for ARAGORN's internal Retriever.
''')
code('''
import json
from pathlib import Path
from collections import Counter
import pandas as pd
from IPython.display import display, Markdown

relative = Path('experiments/aragron-exploration/expansion-across-environments/followups/development-tier-selection')
candidates = [Path.cwd(), Path.cwd() / relative, Path.cwd() / 'development-tier-selection']
ROOT = next(p for p in candidates if (p / 'output/run_001').exists())
RUN = ROOT / 'output/run_001'
load = lambda p: json.loads(p.read_text())
report = load(RUN / 'report.json')
outcomes = load(RUN / 'rule-outcomes.json')
comparison = load(RUN / 'comparison.json')
config = load(RUN / 'config.json')
cases = report['cases']
display(pd.DataFrame(outcomes['environment_summary']))
print('Actual outer submissions:', len(list(RUN.glob('*/q*/submission.json'))))
print('Environment: Development only. Every request has a named submitter. No scheduled repetitions.')
''')
md('''
## What exactly did we submit?

The only differences between the two current variants are the tier controls.
Timeout (120 seconds), DEBUG logging, bypass_cache, target IDs and workflow are held fixed.
The baseline is the earlier Development run saved in `../../output/run_002`.
These runs occurred at different times, so graph stability must not be assumed.
''')
code('''
display(pd.DataFrame(config['default']['targets']))
for arm in ['default', 'tier1']:
    display(Markdown(f'**{arm}: exact first submitted request**'))
    print(json.dumps(load(RUN / arm / 'q01/request.json'), indent=2))
''')
md('''
## What actually executed, and what came back?

`executed_tiers` comes from **Begin processing tier-N job** log messages, not request parameters.
An empty list means no tier execution was observed. `unique_chemical_count = null` means
there was no final results list; it must not be interpreted as a successful search returning zero.

An outer HTTP 200 and `Completed` status can coexist with failed downstream lookups.
Use callback evidence to distinguish those cases. Exact answer-ID and raw-count comparisons
are withheld when either run is incomplete.
''')
code('''
columns = ['environment','query','target_name','executed_tiers','received_callbacks','failed_dispatches',
           'unique_chemical_count','baseline_unique_chemicals','same_final_chemical_ids',
           'same_all_callback_counts','newly_positive_rules','complete_for_answer_comparison']
display(pd.DataFrame(comparison)[columns])
''')
md('''
## How is each rule identified and classified?

A callback's logged query graph is matched to the rules from the advertised ARAGORN release.
Matching preserves direction, predicates, node categories, pinned IDs and qualifier values;
only known TRAPI syntax differences and optional lookup defaults are normalized.
Rule 0 is the direct lookup and is excluded from the eighteen-rule totals.

- **Returned:** a matched rule callback has positive raw results, before ARAGORN merge filtering.
- **Rejected:** a matched callback logs an invalid predicate or unsupported typed edge pattern.
- **Empty:** one matched callback returns zero without logged failure or truncation.
- **Incomplete/error:** timeout or other failure observed in an identified callback.
- **Unknown:** insufficient evidence to identify the rule's result, including dispatch failures with no callback graph.

A zero-result rule for these ten targets is not proof of graph-wide absence.
Failed Tier 1 dispatches cannot establish rule coverage, rejection, or successful expansion of each numbered rule.
''')
code('''
records = pd.DataFrame(outcomes['records'])
for arm in ['default', 'tier1']:
    display(Markdown(f'**{arm}: classification for all 18 rules and ten targets**'))
    subset = records[records.environment == arm]
    display(subset.pivot(index='rule', columns='query', values='category'))
    display(Markdown('**Raw callback counts (before merge); missing means unobserved, not zero.**'))
    display(subset.pivot(index='rule', columns='query', values='raw_result_count'))
''')
md('''
## What edges does each rule require?

The patterns below come from the saved advertised-release templates, not from guessed names.
For each rule, compare the default and Tier 1 outcome totals across the ten targets.
A rule rejection describes compatibility of a query pattern; it does not by itself prove an individual
predicate is absent from every record in a graph.
''')
code('''
sys_path = str(ROOT.parent.parent / 'scripts')
import sys
if sys_path not in sys.path: sys.path.insert(0, sys_path)
from analyze import expected_graphs
rules = load(RUN / 'default/release-rules.json')['{"predicate": "biolink:treats"}']
graphs = expected_graphs(load(RUN / 'default/q01/request.json'), rules)
for number in range(1, 19):
    graph = graphs[number]
    display(Markdown(f'### Rule {number}'))
    edges = []
    for eid, edge in graph['edges'].items():
        edges.append({'edge': eid,
            'subject': edge['subject'] + ': ' + ', '.join(graph['nodes'][edge['subject']].get('categories', [])),
            'predicate': ', '.join(edge.get('predicates', [])),
            'object': edge['object'] + ': ' + ', '.join(graph['nodes'][edge['object']].get('categories', [])),
            'qualifiers / constraints': json.dumps(edge.get('qualifier_constraints') or edge.get('constraints') or {})})
    display(pd.DataFrame(edges))
    selected = records[records.rule == number]
    display(pd.crosstab(selected.environment, selected.category))
''')
md('''
## Read the actual evidence

These are verbatim messages from saved responses. The failed Tier 1 messages do not expose
the downstream HTTP status or response body. In the advertised worker source, a non-200
Retriever response sets `success=False` but leaves `error=None`, producing this uninformative error.
Thus “Tier 1 unavailable” is only a possible cause; the exact cause is unresolved.
''')
code('''
for arm in ['default', 'tier1']:
    response = load(RUN / arm / 'q01/response.json')
    logs = response.get('logs', [])
    display(Markdown(f'**{arm}, first target: routing and failure evidence**'))
    selected = [l for l in logs if any(t in l.get('message','') for t in
                ['Sending lookup query', 'Begin processing tier', 'Failed to do lookup', 'MetaEdges could not be found', 'invalid predicates'])]
    for entry in selected[:24]:
        print(entry.get('level'), entry.get('message'))
    print('Total failed dispatches:', sum('Failed to do lookup' in l.get('message','') for l in logs))
''')
md('''
## Why doesn't public Retriever health resolve the failure?

ARAGORN's returned logs name **`http://retriever/asyncquery`**, an internal service URL.
The separate public endpoint **`https://dev.retriever.biothings.io/status`** reported both
Tier 0 (Gandalf) and Tier 1 (Elasticsearch) healthy at the saved preflight check.
We have not established that this public endpoint and ARAGORN's internal service are the same deployment.
Its health therefore cannot establish the state of the internal Tier 1 backend.

The evidence supports a precise conclusion: **omitting tier controls does not broaden the search**.
The explicit Tier 1 requests test the hosted ARAGORN route, but failed retrieval prevents a
coverage comparison. Additional rules may exist elsewhere; this experiment does not establish that.
The next diagnostic is to obtain the internal Retriever's rejected-submission HTTP status and body,
and verify its Tier 1 configuration, before repeating the coverage experiment.
''')
code('''
health = load(ROOT / 'output/preflight/public-retriever-status.json')
print('Separate public service:', health['url'])
display(pd.DataFrame(health['body']['tiers']))
print('Reported public deployment:', health['body']['version'])
print('No graph queries are issued by this notebook.')
''')

if __name__ == '__main__':
    shared.main('01_development_default_vs_tier1.ipynb')
