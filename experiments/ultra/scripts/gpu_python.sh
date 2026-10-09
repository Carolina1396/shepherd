#!/usr/bin/env bash
# Run the separate GPU Python environment with ULTRA's CUDA build toolchain.
set -euo pipefail
ULTRA_ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
export CUDA_HOME="${ULTRA_CUDA_HOME:-/home/agonzalez/miniconda3/envs/ultra_b}"
export CC="${ULTRA_CC:-${CUDA_HOME}/bin/x86_64-conda-linux-gnu-gcc}"
export CXX="${ULTRA_CXX:-${CUDA_HOME}/bin/x86_64-conda-linux-gnu-c++}"
export PATH="${ULTRA_ROOT}/.venv-model-gpu/bin:${CUDA_HOME}/bin:${PATH}"
export TORCH_EXTENSIONS_DIR="${ULTRA_ROOT}/.cache/torch_extensions_gpu"
export TORCH_CUDA_ARCH_LIST="${TORCH_CUDA_ARCH_LIST:-7.0;8.6}"
export CUDA_DEVICE_ORDER=PCI_BUS_ID
export CUDA_VISIBLE_DEVICES="${CUDA_VISIBLE_DEVICES:-0}"
export MAX_JOBS="${MAX_JOBS:-2}"
export OMP_NUM_THREADS="${OMP_NUM_THREADS:-1}"
export MKL_NUM_THREADS="${MKL_NUM_THREADS:-1}"
exec "${ULTRA_ROOT}/.venv-model-gpu/bin/python" "$@"
