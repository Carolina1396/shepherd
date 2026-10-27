# Chemical/drug treatment prediction: pretrained 4g

Part of [Study 1: full graph treatment prediction](../README.md#study-1-full-graph-treatment-prediction). Original experiment ID: **10**.
Numbered experiment references below use the original IDs.

Evaluate the full Tier 0 graph with the agreed treatment definition:
**(Drug OR ChemicalEntity OR SmallMolecule) → biolink:treats → Disease**.
A node qualifies if its recorded categories include at least one listed subject
category; the object must include `biolink:Disease`. Deduplicate by subject and
disease IDs before splitting. Use the same pretrained 4g checkpoint as Experiment
3, with no fine-tuning or validation-based model selection.

| Output | Count |
|---|---:|
| Eligible treats evidence records | 27,236 |
| Unique eligible treatment pairs | 22,918 |
| Visible context pairs | 18,334 |
| Validation pairs | 2,291 |
| Test pairs | 2,293 |
| Validation disease queries | 1,145 |
| Test disease queries | 1,122 |
| Chemical/drug candidates per disease | 1,117,832 |
| Distinct subjects with eligible treatments | 4,556 |
| Distinct diseases with eligible treatments | 3,901 |

Candidates are all connected nodes meeting the subject category rule, including
nodes without known treatments. Protein-only subjects and non-Disease targets
are excluded from the evaluation labels. Their nodes and edges remain available
as graph context, except where a direct connection belongs to a held-out pair.

Use the existing global split rule: sort unique CURIE pairs, shuffle with seed
731, allocate floor 80%, floor 10%, and the remaining pairs. Remove every direct
connection of validation/test pairs, across all predicates and both directions,
before constructing inverse edges and the relation graph. Use all eligible known
answers across splits for filtered, pessimistic ranking. The new split requires
fresh inference; scores from Experiments 3 and 9 are not reused. Masking removes
11,133 direct triples, leaving 27,916,156 directed triples (55,832,312 with
inverses) across all 1,670,341 graph nodes.

Status: **completed and independently verified** on validation and test.

| Split | Pairs | MRR | Hits@1 | Hits@3 | Hits@10 | Top-10 answers |
|---|---:|---:|---:|---:|---:|---:|
| Validation | 2,291 | 0.0868 | 0.0485 | 0.0808 | 0.1637 | 375 |
| Test | 2,293 | 0.0825 | 0.0414 | 0.0820 | 0.1618 | 371 |

Independent verification checked all 2,267 score-file hashes and recomputed
every rank and metric for all 4,584 held-out pairs. Preparation checks verified
the endpoint categories, complete eligible-pair coverage, and graph masking.

Inference took **26.65 minutes** for validation and **26.14 minutes** for test,
averaging **1.40 seconds per disease query** against all 1,117,832 candidates.
Peak allocated GPU memory was **7.76 GB**, with **9.69 GB reserved**, on an RTX
A6000. Inference timings exclude preparation, ranking, and file writing and
include the two reused smoke queries. The resumed workflow, including independent
verification, took **58.08 minutes**; earlier preparation and smoke checks are
additional. Relation-graph construction took 247.71 seconds.

The corrected treatment definition did not close the gap with MechRepoNet
(test MRR 0.2193 / Hits@10 0.3797). Candidate counts, labels, and graph structure
still differ between those experiments.

Earlier experiment results are preserved. Differences from Experiment 3 include
the label population, split membership, and candidate pool; this remains an
exploratory comparison.

Run from the repository root, using a fresh output directory:

```bash
experiments/ultra/.venv/bin/python -B -u experiments/ultra/pilot/chemical_disease/prepare.py \
  --output experiments/ultra/pilot/results/chemical_disease_4g_002
experiments/ultra/.venv/bin/python -B -u experiments/ultra/pilot/chemical_disease/verify_preparation.py \
  --dataset experiments/ultra/pilot/results/chemical_disease_4g_002
bash experiments/ultra/scripts/gpu_python.sh -B -u experiments/ultra/pilot/chemical_disease/run.py \
  --dataset experiments/ultra/pilot/results/chemical_disease_4g_002
```

The runner evaluates validation and test in sequence. Use `--max-queries 1` for
one query per split, then `--resume` without the limit for the complete run.
Local output retains graph/configuration hashes, scores, ranks, timings, and
peak GPU memory. Partial metrics are explicitly marked incomplete.

[Verified setup record](../studies/full_graph_chemical_disease_4g_setup.json).
[Completed results and verification](../studies/full_graph_chemical_disease_4g_results.json).
The launched workflow saves its progress in `run.log`, its final status in
`run_status.json`, and a retained study result after independent score verification.

After a complete run, independently verify every saved score file and rank:

```bash
experiments/ultra/.venv/bin/python -B -u experiments/ultra/pilot/chemical_disease/verify_results.py \
  --dataset experiments/ultra/pilot/results/chemical_disease_4g_002
```
