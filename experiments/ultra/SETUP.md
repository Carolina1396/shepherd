# ULTRA setup and local checks

Return to the [project overview](README.md) or the
[four-study index and run guides](pilot/README.md).

The existing machine already has the environments, checkpoints, graph store,
and prepared evaluation inputs. Use installation/build commands only when their
destination is absent. All commands below run from the repository root.

## Source code and data prerequisites

The study uses Python 3.11 and the pinned ULTRA implementation below. Its
`ckpts/` directory must contain `ultra_3g.pth` and `ultra_4g.pth`.
These files are included in the pinned upstream checkout. Checkpoint
hashes are recorded in the prepared dataset and
[3g study record](pilot/studies/full_graph_ultra3g_bidirectional.json).

```bash
git clone https://github.com/DeepGraphLearning/ULTRA.git experiments/ultra/vendor/ULTRA
git -C experiments/ultra/vendor/ULTRA checkout --detach 427966ad8ed60420eef034063d44f3153addff90
```

The Translator `2026_06_21` archive and metadata are recorded in
[download.json](download.json), under `data/tier0-20260621/`. Graph building
requires that archive and `output/overview/archive_inventory.json`; full-graph
treatment preparation also uses `output/treatment_pairs/pairs.csv`. These are
existing local inputs. On a fresh machine, restore/download the data and follow
[notebooks 01–02](notebooks/README.md) to prepare their inventories. Cloning the
code alone does not supply the full graph or generated study inputs.

The graph inspection/build scripts require the **`zstd` command-line program**
on `PATH`; the Python `zstandard` package alone is insufficient. Notebooks need
Jupyter and `ipykernel` in the selected Python environment (not included in
`requirements-model.txt`). Use a Python 3.11 kernel; the scripts themselves do
not need a notebook server.

## Fresh-clone reproducibility

GitHub includes code, notebooks with saved outputs, and
[small original reports](pilot/studies/evidence/README.md). It excludes datasets,
model checkouts, environments, prepared tensors, and raw inference scores.
Download each source file from the URL in `download.json` to its listed path
under this directory and verify its SHA-256 before preparing the graph.

For sampling and 4g evaluation, install the dependencies, run notebooks 01–02,
build/verify the Gandalf store, then use the preparation and inference commands
linked from the [pilot index](pilot/README.md). The current chemical/drug
workflow starts with the [baseline preparation](pilot/chemical_disease/README.md),
then uses those frozen inputs for [fine-tuning](pilot/chemical_finetune/README.md).
Follow each guide's required paths: newer runners also depend on local prepared
datasets. This full sequence has not been tested from a clean clone.

The **exact 3g reference runner requires the original frozen**
`output/full-graph-ultra/run_001/` directory, including `data/`, `config.json`,
`preparation.json`, `relation_graph.pt`, and `relation_graph.json`, plus the
Gandalf store. It verifies the recorded hashes. These inputs are available on
the current machine but have no published download bundle. A newly prepared
graph/cache is not guaranteed to have the same byte hashes, so the saved metric
reports alone cannot run that reference on another machine.

On another GPU machine, set `ULTRA_CUDA_HOME`, `ULTRA_CC`, and `ULTRA_CXX` to
its CUDA 11.8 toolkit and compatible compiler paths before using the launcher.
Set `CUDA_VISIBLE_DEVICES` and `TORCH_CUDA_ARCH_LIST` for its hardware too; the
defaults below describe the current A6000/V100 machine.

## CPU and Gandalf environments

On 2026-10-08, the Gandalf runtime was restored in `.venv/` and the ULTRA CPU
runtime in `.venv-model/`, both using Python 3.11.14. The full existing store
passed the original verification, including all predicate/knowledge-level
counts and 5,732 sampled evidence records. The report and Gandalf dependency
snapshot are under `output/gandalf/linux-*-20261008.*`. The original store and
historical verification reports were preserved.

For a **fresh environment**, from the repository root (a working C++ compiler is
needed for ULTRA's extension):

```bash
git clone https://github.com/ranking-agent/gandalf.git experiments/ultra/vendor/gandalf
git -C experiments/ultra/vendor/gandalf checkout --detach 3fbaded1c922de3d61ff2af17694264d13b221f5
python3.11 -m venv experiments/ultra/.venv
experiments/ultra/.venv/bin/python -m pip install -e 'experiments/ultra/vendor/gandalf[server]' numpy==1.26.4 PyYAML==6.0.3 zstandard
python3.11 -m venv experiments/ultra/.venv-model
experiments/ultra/.venv-model/bin/python -m pip install torch==2.1.0 --index-url https://download.pytorch.org/whl/cpu
experiments/ultra/.venv-model/bin/python -m pip install -r experiments/ultra/requirements-model.txt torch-scatter==2.1.2 -f https://data.pyg.org/whl/torch-2.1.0+cpu.html
```

On this machine the Python 3.11 interpreter used above is
`/home/agonzalez/miniconda3/envs/ctx/bin/python`; it can replace `python3.11` in
the commands. Gandalf's `server` extras supply dependencies imported by its
built-in plugins even when accessing a local store. This does not start a server.
ULTRA source/checkpoints must also be present at the pinned version documented
above. The downloaded graph, full store, and treatment-pair preprocessing outputs
are already present here.

## GPU environment

`.venv-model-gpu/` uses Python 3.11, PyTorch 2.1.0 with CUDA 11.8,
PyG 2.4.0, and `torch-scatter` 2.1.2 for PyTorch 2.1/CUDA 11.8.
The existing CPU and Gandalf environments are preserved.

Use [scripts/gpu_python.sh](scripts/gpu_python.sh) through Bash to run GPU Python
with the required compiler and extension-cache settings:

```bash
bash experiments/ultra/scripts/gpu_python.sh -c 'import torch; print(torch.cuda.get_device_name(0))'
```

The launcher defaults to physical GPU 0 (RTX A6000) with PCI bus ordering.
Set `CUDA_VISIBLE_DEVICES=1` before the command to use the V100 instead. It uses
the existing CUDA 11.8 toolkit and GCC 11.4 compiler under
`/home/agonzalez/miniconda3/envs/ultra_b` without modifying that environment.
This is an external toolchain dependency, not a fully self-contained CUDA
installation. `ULTRA_CUDA_HOME`, `ULTRA_CC`, and `ULTRA_CXX` can override those
defaults; unrelated inherited CUDA/compiler settings are replaced by the launcher.
The GPU kernel cache is `.cache/torch_extensions_gpu`, separate from the CPU
cache, with compiled support for both GPU architectures. First compilation uses
at most two parallel jobs by default.

To recreate the environment on this machine, when the destination is absent:

```bash
/home/agonzalez/miniconda3/envs/ctx/bin/python -m venv experiments/ultra/.venv-model-gpu
experiments/ultra/.venv-model-gpu/bin/python -m pip install torch==2.1.0 --index-url https://download.pytorch.org/whl/cu118
experiments/ultra/.venv-model-gpu/bin/python -m pip install -r experiments/ultra/requirements-model.txt torch-scatter==2.1.2+pt21cu118 -f https://data.pyg.org/whl/torch-2.1.0+cu118.html
```

[verify_ultra_gpu.py](scripts/verify_ultra_gpu.py) checks the native CUDA kernel's
forward output and gradients against CPU, then compares 6,227 pretrained model
scores for one validation disease using the existing masked sampled graph:

```bash
bash experiments/ultra/scripts/gpu_python.sh -B -u experiments/ultra/scripts/verify_ultra_gpu.py
```

It writes `output/gpu-verification/verification.json` and a dependency freeze
only after passing. For another verification, supply a fresh `--output` folder.
Verification passed on the RTX A6000 on 2026-10-08: kernel outputs and gradients
matched CPU, and the maximum absolute difference across 6,227 pretrained scores
was `2.38e-6`. GPU inference for that sampled-graph query took 0.39 seconds with
65.4 MB peak allocated GPU memory (not total device usage). Dependency checks
also passed. See the [verification report](pilot/studies/evidence/gpu-verification/verification.json)
and [dependency snapshot](pilot/studies/evidence/gpu-verification/requirements-freeze.txt).
This check does not evaluate held-out test labels or benchmark the full graph.
The launcher configures CUDA access; application code must still move its model
and graph tensors to CUDA. The earlier CPU pilot runner explicitly uses CPU.

## Build and verify the Gandalf store

The store was built with [ranking-agent/gandalf](https://github.com/ranking-agent/gandalf)
at commit `3fbaded1c922de3d61ff2af17694264d13b221f5`, with local source under
`vendor/gandalf/`. No Gandalf source changes,
Retriever service, or Shepherd workers are needed for this local preparation.

[scripts/build_gandalf_store.py](scripts/build_gandalf_store.py) extracts our
pinned Tier 0 archive, prepares a setup sample, calls Gandalf's builder, and
checks the saved stores in separate processes. Gandalf stores connections in
CSR arrays and properties in accompanying stores. Its loader indexes nodes
appearing in edges: **1,670,341 connected nodes** in this release. The other
**84,413 raw nodes** are not edge endpoints and are not indexed. All original
node records remain in the extracted JSONL file.

The setup sample takes the first 100 edges per exact predicate (or all if fewer),
plus their endpoint nodes: **5,732 edges, 7,987 nodes, all 60 predicates**. This
is a format/access check, not a representative prediction dataset. Build, save,
reload, neighbor access, and source/knowledge-level allow/deny checks passed.
All sampled edge IDs, primary sources, knowledge levels, agent types,
publications, and node categories matched the raw records after reload.

The **full build and fresh-process reload verification also passed**:

| Measurement | Result |
|---|---:|
| Indexed nodes | 1,670,341 |
| Edges | 28,709,074 |
| Predicates | 60 |
| Build + save time (excluding extraction) | 20.1 minutes |
| Peak resident memory during build/save | 12.3 GB |
| Saved store size | 21.6 GB |
| Memory-mapped reload time in this run | 6.2 seconds |

Sizes above use decimal GB. Reload time benefits from the local filesystem cache
and does not mean every property was read into memory. Full verification matched
every predicate count and knowledge-level total against the raw scan, checked
CSR edge counts, and repeated the detailed sample checks inside the full store.
The 84,413 unindexed nodes are isolated; no input edges were removed. The raw
JSONL files occupy another 25.5 GB, and the original compressed archive is retained.

Run each stage in order from the repository root, using Gandalf's existing env:

```bash
experiments/ultra/.venv/bin/python -B experiments/ultra/scripts/build_gandalf_store.py prepare
experiments/ultra/.venv/bin/python -B experiments/ultra/scripts/build_gandalf_store.py sample
experiments/ultra/.venv/bin/python -B experiments/ultra/scripts/build_gandalf_store.py verify-sample
experiments/ultra/.venv/bin/python -B experiments/ultra/scripts/build_gandalf_store.py full
experiments/ultra/.venv/bin/python -B experiments/ultra/scripts/build_gandalf_store.py verify-full
```

Builds need network access for Gandalf's pinned Biolink schema. Existing store
directories are never overwritten. Temporary build databases are cleaned after
the saved store is written. Files under `output/gandalf/` include `sample-store/`,
`full-store/`, input counts, build timings/peak memory, and verification reports.

The full store supplies the disease-based sampling pilot. Gandalf walks operate
on the full graph; the active pilot performs sampling and coverage analysis,
then prepares a separate masked graph for ULTRA validation.

## CPU benchmark check

From the repository root:

```bash
experiments/ultra/.venv-model/bin/python experiments/ultra/scripts/run_ultra_example.py
```

This runs the [official ULTRA](https://github.com/DeepGraphLearning/ULTRA)
CoDExSmall example with `ultra_4g.pth`, CPU inference, and **zero training epochs**.
It evaluates the full validation and test splits using the upstream ranking code.
The launcher only relocates data/output paths and configures local build tools;
the upstream model code is unchanged. The first run downloads the benchmark and
compiles a C++ extension (requires a working C++ compiler).

CoDExSmall is a general knowledge-graph benchmark. This example checks that ULTRA
runs locally; its scores do not measure treatment prediction on Tier 0.

Completed locally on 2026-10-05: 32,888 training graph triples, 1,827 validation
triples, and 1,828 test triples. The checkpoint was used without further training.
Filtered ranking evaluates both missing heads and missing tails.

| Split | MRR | Hits@1 | Hits@10 |
|---|---:|---:|---:|
| Validation | 0.477777 | 0.373290 | 0.676793 |
| Test | 0.463778 | 0.360503 | 0.665208 |

MRR measures how highly the known answer ranks (higher is better); Hits@10 is the
fraction of queries where it ranks among the first ten. The run took about two
minutes including initial extension compilation. Its log is at
`output/ultra-example/Ultra/CoDExSmall/2026-10-05-16-18-04/log.txt`.
