#!/usr/bin/env bash
# Arguments: a new run name, optionally the export, graph, and split directories.
set -euo pipefail
experiment_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
repo_dir=$(cd -- "$experiment_dir/../.." && pwd)
run_name=${1:?Usage: bash run_server.sh NEW_RUN_NAME [EXPORT_DIR] [GRAPH_DIR] [SPLITS_DIR]}
[[ "$run_name" =~ ^[A-Za-z0-9_-]+$ ]] || { echo 'Run name must contain only letters, digits, underscores, or hyphens.' >&2; exit 2; }
export_dir=${2:-$experiment_dir/runs/export-001}
graph_dir=${3:-$repo_dir/artifacts/gandalf_no_drug_disease}
splits_dir=${4:-$repo_dir/data_split/nonisolated}
run_dir="$experiment_dir/runs/$run_name"
mkdir "$run_dir"
exec > >(tee -a "$run_dir/driver.log") 2>&1
python_bin="$experiment_dir/.venv/bin/python"
git -C "$repo_dir" rev-parse HEAD > "$run_dir/git-commit.txt"
"$python_bin" "$experiment_dir/workflow.py" mine --export "$export_dir" --out "$run_dir/mining"
"$python_bin" - "$run_dir/mining/manifest.json" <<'PY'
import json, sys
m = json.load(open(sys.argv[1]))
if m['state'] == 'blocked_memory':
    sys.exit('Mining blocked by memory preflight; see manifest. Validation was not started.')
PY
"$python_bin" "$experiment_dir/workflow.py" validate --export "$export_dir" --mined "$run_dir/mining" --out "$run_dir/validation" --graph "$graph_dir" --splits "$splits_dir"
