#!/usr/bin/env bash
set -euo pipefail
cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.."
export UV_CACHE_DIR="${UV_CACHE_DIR:-$PWD/.cache/uv}"
export UV_PYTHON_INSTALL_DIR="${UV_PYTHON_INSTALL_DIR:-$PWD/.cache/uv-python}"
if ! command -v uv >/dev/null 2>&1; then
  printf '%s\n' 'Install uv from the official distribution, then run scripts/bootstrap.sh.' >&2
  exit 3
fi
uv python install --no-bin 3.10
uv sync --frozen --all-extras
./scripts/doctor.sh
