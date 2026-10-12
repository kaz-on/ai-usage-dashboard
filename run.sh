#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")"

VENV_DIR=".venv"

if [[ ! -d "$VENV_DIR" ]]; then
  echo "Creating virtualenv..."
  python3 -m venv "$VENV_DIR"
  "$VENV_DIR/bin/pip" install --upgrade pip >/dev/null
fi

# 依存が増えたときに既存 venv でも取り込めるよう、起動のたびに確認する。
"$VENV_DIR/bin/pip" install .

# .env があれば読み込む (set -a により、中の代入はそのまま export される)。
# 環境変数を自分で export して起動する使い方もあるので、無くても止めない。
if [[ -f .env ]]; then
  set -a
  source .env
  set +a
fi

exec "$VENV_DIR/bin/uvicorn" app.main:app \
  --host "${DASHBOARD_BIND_ADDRESS:-127.0.0.1}" \
  --port "${DASHBOARD_PORT:-8080}" \
  --workers 1
