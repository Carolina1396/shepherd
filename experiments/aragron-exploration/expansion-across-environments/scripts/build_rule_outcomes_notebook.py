"""Build the dedicated offline rule-outcome notebook; --execute embeds displays."""
# Reuse the existing nbformat writer and display execution. Importing it only
# constructs cell definitions; it does not read data, write files, or send queries.
from build_notebook import cells, md, code, main
cells.clear()

md('''
# Which rules expanded, returned results, were rejected, or were empty?

This notebook audits **10 treatment queries × 18 rules × 4 hosted environments = 720 rule evaluations**.
It uses the saved main run (`run_002`). The 40 direct lookups are counted separately.

**Expansion and outcome are different dimensions.** An expanded rule can return results,
be rejected, or return an empty callback. We confirm expansion by matching a callback query
graph from the live logs to the release template; the existence of a template file alone is insufficient.

**Returned** means a positive raw callback result count, before ARAGORN filters and merges.
It does not mean a unique chemical answer or a confirmed contribution to the final response.

Running this notebook is offline. No new service queries are submitted.
''')
code('''
from pathlib import Path
import json
import hashlib
import sys
from html import escape
import pandas as pd
from IPython.display import display, HTML, Markdown

candidates = [p for base in (Path.cwd(), *Path.cwd().parents)
              for p in (base, base / 'experiments/aragron-exploration/expansion-across-environments',
                        base / 'expansion-across-environments')]
ROOT = next(p for p in candidates if (p / 'scripts/rule_outcomes.py').exists())
RUN = ROOT / 'output/run_002'
analysis = json.loads((RUN / 'rule-outcomes.json').read_text())
assert analysis['source_report_sha256'] == hashlib.sha256((RUN / 'report.json').read_bytes()).hexdigest(), 'Rebuild rule_outcomes.py after updating the source report.'
rows = analysis['records']
LABELS = {'development':'Development', 'ci_staging':'CI / Staging', 'test':'Test', 'production':'Production'}
ENVIRONMENTS = list(LABELS)
COLORS = {'returned':'#dcfce7','rejected':'#fee2e2','empty':'#e5e7eb','incomplete':'#fef3c7','error':'#fef3c7','unknown':'#dbeafe'}
SYMBOLS = {'returned':'R','rejected':'X','empty':'E','incomplete':'I','error':'!','unknown':'?'}

def table(data):
    return pd.DataFrame(data).to_html(index=False, escape=True)

def numbers(values):
    return ', '.join(map(str, values)) if values else 'None'

display(pd.DataFrame([analysis['totals']]))
display(pd.DataFrame([{'Term':k,'Meaning':v} for k,v in analysis['definitions'].items()]))
print('Expanded is a separate total. Returned + rejected + empty + incomplete + error + unknown partitions the rule evaluations.')
''')
md('''
## Outcome totals for each environment

A rule evaluation is one rule for one target in one environment. Thus 27 returned evaluations
means 27 rule–target combinations had positive callbacks; it is not 27 rules or 27 chemicals.
The reported error count excludes the explicitly classified rejections.
''')
code('''
environment_counts = pd.DataFrame(analysis['environment_summary'])
display(environment_counts)
assert all(sum(s[k] for k in ('returned','rejected','empty','incomplete','error','unknown')) == s['rule_evaluations'] for s in analysis['environment_summary'])
agreement = pd.DataFrame(analysis['environment_agreement'])
display(agreement)
''')
md('''
## Which rules had each outcome for each target?

The table below combines environments **only if their expanded-rule and outcome lists agree for
that target**. Otherwise each environment is displayed separately. Rejected rules are explicitly
listed; they must not be interpreted as successful zero-result searches.
''')
code('''
query_rows = []
for agreement in analysis['environment_agreement']:
    subset = [q for q in analysis['query_summary'] if q['query']==agreement['query']]
    selected = subset[:1] if agreement['same_expansion_and_outcome_groups'] else subset
    for q in selected:
        query_rows.append({'Query':q['query'], 'Target':q['target_name'],
            'Environments':'All four (verified)' if agreement['same_expansion_and_outcome_groups'] else LABELS[q['environment']],
            'Expanded':numbers(q['expanded_rules']), 'Returned':numbers(q['returned_rules']),
            'Rejected':numbers(q['rejected_rules']), 'Empty':numbers(q['empty_rules']),
            'Incomplete / error / unknown':numbers(sorted(q['incomplete_rules']+q['error_rules']+q['unknown_rules']))})
display(pd.DataFrame(query_rows))
''')
md('''
## Status grid: ten targets × eighteen rules, for each environment

**R (count)** = returned raw results; **X** = rejected; **E** = empty callback with no error logged.
**I / ! / ?** indicate incomplete search, other backend error, or unknown evidence.
A `*` on a returned result means additional issues are recorded in the detailed evidence.
Color is supplementary; every cell also has a text label. Hover over a cell for the exact outcome.
''')
code('''
for env in ENVIRONMENTS:
    selected = [r for r in rows if r['environment']==env]
    html = '<table><thead><tr><th>Query / target</th>' + ''.join(f'<th>R{n}</th>' for n in range(1,19)) + '</tr></thead><tbody>'
    for query in dict.fromkeys(r['query'] for r in selected):
        query_rows = [r for r in selected if r['query']==query]
        html += '<tr><th style="text-align:left">' + escape(query + ' — ' + query_rows[0]['target_name']) + '</th>'
        by_rule = {r['rule']:r for r in query_rows}
        for number in range(1,19):
            row = by_rule.get(number)
            if row is None:
                html += '<td>?</td>'
                continue
            label = SYMBOLS[row['category']]
            if row['category']=='returned':
                label += ' (' + str(row['raw_result_count']) + ')' + ('*' if row['issue_flags'] else '')
            tooltip = f"Expanded: {row['expanded']}; " + ', '.join(row['outcomes'] + row['issue_flags'])
            html += '<td title="' + escape(tooltip, quote=True) + '" style="padding:6px;white-space:nowrap;color:#111827;background:' + COLORS[row['category']] + '">' + escape(label) + '</td>'
        html += '</tr>'
    html += '</tbody></table>'
    display(HTML('<details open><summary><b>' + LABELS[env] + '</b></summary><div style="overflow-x:auto">' + html + '</div></details>'))
''')
md('''
## What happened to each rule across all forty query/environment combinations?

Each rule has forty evaluations: ten targets in four environments.
“Always empty” is restricted to these ten targets. It is not a claim that no matching path exists
anywhere in the graph. A rule returning paths for some targets may be empty for others.
''')
code('''
display(pd.DataFrame(analysis['rule_summary']))
print('Always rejected in this sample:', numbers([r['rule'] for r in analysis['rule_summary'] if r['rejected']==r['rule_evaluations']]))
print('Always empty in this sample:', numbers([r['rule'] for r in analysis['rule_summary'] if r['empty']==r['rule_evaluations']]))
print('Returned results for at least one target:', numbers([r['rule'] for r in analysis['rule_summary'] if r['returned']]))
''')
md('''
## Why were rules rejected? Which edges did the service flag?

Rule 1 is rejected for an invalid predicate. The other rejected rules have query edges for which
Retriever reports no compatible **MetaEdge**: a supported category/predicate/category pattern.

These messages describe the service's validation or supported schema. They do not independently
establish graph-wide absence. An edge not named by the error has **not** been independently
confirmed present. Full rejection messages and observed graphs are retained for every evaluation.
''')
code('''
rejection_rows = []
seen = set()
for row in rows:
    if row['category']!='rejected':
        continue
    for evidence in row['rejections']:
        for edge in evidence['flagged_edges']:
            if 'predicates' not in edge:
                pattern = 'Observed edge details unavailable'
            else:
                pattern = ', '.join(edge['subject_categories']) + ' → ' + ', '.join(edge['predicates']) + ' → ' + ', '.join(edge['object_categories'])
            key = (row['rule'], edge['edge'], pattern, evidence['message'])
            if key in seen:
                continue
            seen.add(key)
            rejection_rows.append({'Rule':row['rule'], 'Flagged edge':edge['edge'], 'Typed edge pattern':pattern,
                                   'Exact service message':evidence['message']})
display(pd.DataFrame(rejection_rows).sort_values(['Rule','Flagged edge']))
print('Development also logs some unknown-constraints warnings. Those warnings are retained and alone do not prove qualifiers were ignored.')
''')
md('''
## Inspect the exact evidence for one query and environment

Change `QUERY` and `ENVIRONMENT` below. Each rule shows its outcome, raw count, observed query
graph, warnings/errors and callback ID. A returned path count is recorded before merge filters;
this view does not attribute final merged answers to individual rules.
''')
code('''
QUERY = 'q01'
ENVIRONMENT = 'development'
selected = [r for r in rows if r['query']==QUERY and r['environment']==ENVIRONMENT]
assert selected, 'Choose q01 … q10 and development / ci_staging / test / production.'
display(Markdown('**' + LABELS[ENVIRONMENT] + ' — ' + selected[0]['target_name'] + '**'))
display(pd.DataFrame([{k:r[k] for k in ('rule','expanded','category','raw_result_count','callback_count','issue_flags')} for r in selected]))
for row in selected:
    content = {k:row[k] for k in ('outcomes','callback_ids','rejections','warnings_errors','observed_query_graphs','response_artifact')}
    title = f"Rule {row['rule']}: {row['category']} — raw results: {row['raw_result_count']}"
    display(HTML('<details><summary>' + escape(title) + '</summary><pre>' + escape(json.dumps(content,indent=2)) + '</pre></details>'))
''')
md('''
## Direct lookup is separate

ARAGORN also performs the original question as a direct lookup. Those forty callbacks are excluded
from the 720 rule evaluations above. Direct results explain how a target can receive final answers
even if none of its eighteen inference-rule callbacks returned a result.
''')
code('''
direct = pd.DataFrame(analysis['direct_lookups'])
display(direct.pivot(index=['query','target_name'],columns='environment',values='raw_result_count').reindex(columns=ENVIRONMENTS).rename(columns=LABELS))
for limitation in analysis['limitations']:
    print('•', limitation)
print('Detailed export:', (RUN / 'rule-outcomes.csv').resolve())
print('Per-query lists:', (RUN / 'rule-outcomes-by-query.csv').resolve())
''')

if __name__ == '__main__':
    main(notebook_name='02_rule_outcomes.ipynb')
