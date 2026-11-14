#!/usr/bin/env bash
# Run from any working directory after checking out the experiment commit.
set -euo pipefail
experiment_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
python_bin=${PYTHON_BIN:-python3}
"$python_bin" -c 'import sys; assert sys.version_info >= (3, 12), "Python >=3.12 is required; set PYTHON_BIN"'
java -version
"$python_bin" -m venv "$experiment_dir/.venv"
"$experiment_dir/.venv/bin/python" -m pip install -r "$experiment_dir/requirements.txt"
mkdir -p "$experiment_dir/vendor"
jar_path="$experiment_dir/vendor/amie.jar"
if [[ ! -f "$jar_path" ]]; then
  curl --fail --location --retry 3 https://raw.githubusercontent.com/dig-team/AMIE/add2b6a7e36a68fc85c9d004a089b264e138ff62/amie-dev.jar -o "$jar_path.download"
  mv "$jar_path.download" "$jar_path"
fi
"$experiment_dir/.venv/bin/python" - "$jar_path" <<'PY'
import hashlib, pathlib, sys
p = pathlib.Path(sys.argv[1])
assert hashlib.sha256(p.read_bytes()).hexdigest() == 'bfdb11577fc5404f29eb30b3e16b1002f3b8e38fb53717eccc790a22f63763ca', 'AMIE checksum mismatch'
PY
"$experiment_dir/.venv/bin/python" -m unittest discover -s "$experiment_dir" -p 'test_*.py' -v
"$experiment_dir/.venv/bin/python" -c 'import psutil; m=psutil.virtual_memory(); print(f"RAM total={m.total/2**30:.1f} GiB, available={m.available/2**30:.1f} GiB; mining needs at least 17 GiB available on a >=32 GiB host")'
