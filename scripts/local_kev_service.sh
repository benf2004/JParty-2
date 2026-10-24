#!/usr/bin/env bash
# Shared by the full-local setup/start/stop helpers. Source this file.
KEV_ENABLED="${JPARTY_LOCAL_KEV_ENABLED:-0}"
KEV_PORT="${JPARTY_LOCAL_KEV_PORT:-8009}"
KEV_CHECKPOINT="${JPARTY_LOCAL_KEV_CHECKPOINT:-jaredpalmer/kev-0.8b@v1.0}"
KEV_DIR="${HOME}/Library/Application Support/JParty/local-auto-host/kev"
KEV_PID_FILE="${KEV_DIR}/server.pid"
KEV_RUNNER="${KEV_DIR}/jparty_kev_server.py"
KEV_LOG="${HOME}/Library/Application Support/JParty/local-auto-host/kev-server.log"
KEV_URL="http://localhost:${KEV_PORT}/v1"

kev_enabled() {
  case "$KEV_ENABLED" in
    1|yes|true) return 0 ;;
    0|no|false) return 1 ;;
    *) echo "Use JPARTY_LOCAL_KEV_ENABLED=1 or 0." >&2; exit 1 ;;
  esac
}

kev_running() {
  [[ -f "$KEV_PID_FILE" ]] || return 1
  read -r kev_pid < "$KEV_PID_FILE" || return 1
  [[ "$kev_pid" =~ ^[0-9]+$ ]] && [[ "$kev_pid" -gt 1 ]] || return 1
  local command_line
  command_line="$(ps -p "$kev_pid" -o command= 2>/dev/null)" || return 1
  [[ "$command_line" == *"${KEV_RUNNER} --run "* ]]
}

setup_kev() {
  kev_enabled || return 0
  if kev_running; then
    echo "Kev is running; stop it before rerunning setup to change its environment."
    return 0
  fi
  if ! command -v uv >/dev/null 2>&1; then
    brew install uv
  fi
  if [[ ! -d "${KEV_DIR}/.git" ]]; then
    echo "Installing Kev in its own environment..."
    mkdir -p "$(dirname "$KEV_DIR")"
    git clone --branch kev-1.0 --depth 1 https://github.com/jaredpalmer/kev.git "$KEV_DIR"
  fi
  uv sync --project "$KEV_DIR" --python 3.13 --extra serve --frozen
  # macOS framework Python rewrites argv[0], so use a unique script path to
  # identify our process reliably instead of matching the interpreter path.
  cat > "$KEV_RUNNER" <<'PY'
import runpy
runpy.run_module("kev.serve", run_name="__main__")
PY
}

start_kev() {
  local mode="${1:-start}"
  kev_enabled || return 0
  local attempts="${JPARTY_KEV_START_TIMEOUT:-180}"
  [[ "$mode" != "setup" ]] || attempts="${JPARTY_KEV_START_TIMEOUT:-1800}"
  if [[ ! "$attempts" =~ ^[1-9][0-9]*$ ]]; then
    echo "JPARTY_KEV_START_TIMEOUT must be a positive integer (seconds)."
    return 1
  fi
  if [[ ! "$KEV_PORT" =~ ^[0-9]+$ ]] || (( KEV_PORT < 1 || KEV_PORT > 65535 )); then
    echo "JPARTY_LOCAL_KEV_PORT must be between 1 and 65535." >&2
    return 1
  fi
  if [[ ! -x "${KEV_DIR}/.venv/bin/python" || ! -f "$KEV_RUNNER" ]]; then
    echo "Kev is not installed. Run scripts/setup_full_local_auto_host_macos.sh first,"
    echo "or set JPARTY_LOCAL_KEV_ENABLED=0 to use the existing LLM judge."
    return 1
  fi
  if ! kev_running; then
    # Refuse to adopt or stop another service using this port.
    if curl --connect-timeout 1 --max-time 2 -sS "${KEV_URL}/models" >/dev/null 2>&1; then
      echo "Port ${KEV_PORT} is already in use by an unmanaged service. Stop it or choose JPARTY_LOCAL_KEV_PORT."
      return 1
    fi
    echo "Starting Kev (${KEV_CHECKPOINT}); log: ${KEV_LOG}"
    local offline=1
    [[ "$mode" != "setup" ]] || offline=0
    (
      cd "$KEV_DIR"
      # Setup permits model downloads; game-night starts use cached files only.
      exec nohup env HF_HUB_OFFLINE="$offline" TRANSFORMERS_OFFLINE="$offline" \
        "${KEV_DIR}/.venv/bin/python" "$KEV_RUNNER" \
        --run "$KEV_CHECKPOINT" --host 127.0.0.1 --port "$KEV_PORT"
    ) >"$KEV_LOG" 2>&1 < /dev/null &
    echo "$!" > "$KEV_PID_FILE"
    # Allow the background subshell to exec the server before checking its command.
    sleep 1
  fi
  echo "Waiting for Kev to load (first setup may download several GB)..."
  local elapsed
  for ((elapsed=0; elapsed<attempts; elapsed++)); do
    if ! kev_running; then
      echo "Kev exited before becoming ready. Check: $KEV_LOG"
      rm -f "$KEV_PID_FILE"
      return 1
    fi
    if curl --connect-timeout 1 --max-time 2 -fsS "${KEV_URL}/models" 2>/dev/null \
      | "${KEV_DIR}/.venv/bin/python" -c 'import json,sys; d=json.load(sys.stdin); sys.exit(not any(m.get("name")=="kev-latest" and m.get("run")==sys.argv[1] for m in d.get("models", [])))' "$KEV_CHECKPOINT" 2>/dev/null; then
      echo "Kev is ready."
      return 0
    fi
    sleep 1
  done
  echo "Kev is still loading or its checkpoint/port differs. Check: $KEV_LOG"
  echo "Stop it with scripts/stop_full_local_auto_host_macos.sh before changing its checkpoint or port."
  return 1
}

stop_kev() {
  # Stop a managed process even if Kev has since been disabled.
  if kev_running; then
    echo "Stopping JParty Kev..."
    kill "$kev_pid"
    local elapsed
    for ((elapsed=0; elapsed<15; elapsed++)); do
      if ! kev_running; then
        rm -f "$KEV_PID_FILE"
        return 0
      fi
      sleep 1
    done
    echo "Kev has not exited yet; kept its PID file. Retry the stop script."
    return 1
  fi
  rm -f "$KEV_PID_FILE"
  echo "JParty Kev is not running."
}

print_kev_settings() {
  if kev_enabled; then
    echo "  Answer judge: Kev (local decision model)"
    echo "  Kev URL: $KEV_URL"
    echo "  Kev served model: kev-latest"
    echo "  Kev checkpoint: $KEV_CHECKPOINT"
    echo "  Kev log: $KEV_LOG"
  else
    echo "  Answer judge: Local LLM · fast true/false (recommended)"
  fi
}
