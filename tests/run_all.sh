#!/usr/bin/env bash
#  run_all.sh — Todas las pruebas: las de pytest y los guiones que manejan la ventana o FFmpeg.
#
#  Uso:   bash tests/run_all.sh            (FFmpeg del PATH o de $TUXENC_FFMPEG_DIR)
#  Los vídeos de prueba se generan la primera vez en tests/.media (o en $TUXENC_TESTMEDIA).
set -uo pipefail

cd "$(dirname "$0")/.." || exit 1
PY="${PYTHON:-python3}"
export QT_QPA_PLATFORM="${QT_QPA_PLATFORM:-offscreen}"
export PYTHON_KEYRING_BACKEND="${PYTHON_KEYRING_BACKEND:-keyring.backends.null.Keyring}"

# Guiones que se ejecutan de arriba abajo (no son funciones de pytest)
SCRIPTS=(tests/test_engine.py tests/test_control.py tests/test_prio.py tests/test_progress_subs.py
         tests/gui_*.py)

echo "▶ Vídeos de prueba"
"$PY" -m tests.media || exit 1

echo "▶ pytest"
ignore=()
for s in tests/test_engine.py tests/test_control.py tests/test_prio.py tests/test_progress_subs.py; do
  ignore+=(--ignore="$s")
done
"$PY" -m pytest -q -p no:cacheprovider tests "${ignore[@]}" || exit 1

failed=()
for s in "${SCRIPTS[@]}"; do
  start=$SECONDS
  log="$(mktemp)"
  if timeout 600 "$PY" "$s" >"$log" 2>&1; then
    printf '✓ %-32s %3ss\n' "$s" "$((SECONDS - start))"
  else
    printf '✗ %-32s %3ss\n' "$s" "$((SECONDS - start))"
    tail -40 "$log" | sed 's/^/    /'
    failed+=("$s")
  fi
  rm -f "$log"
done

if [ "${#failed[@]}" -gt 0 ]; then
  echo "Fallaron: ${failed[*]}"
  exit 1
fi
echo "Todas las pruebas pasan."
