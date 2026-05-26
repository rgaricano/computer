#!/bin/bash
export CPTR_DATA_DIR="${CPTR_DATA_DIR:-$(cd "$(dirname "$0")" && pwd)/.cptr}"
uv run cptr run --reload --port 9741
