#!/usr/bin/env bash
set -euo pipefail

COMPOSE_DIR="${COMPOSE_DIR:-/volume1/docker/compose/investing-platform}"
DOCKER_BIN="${DOCKER_BIN:-}"
SUDO_BIN="${SUDO_BIN:-sudo}"

if [[ -z "$DOCKER_BIN" ]]; then
  if [[ -x /usr/local/bin/docker ]]; then
    DOCKER_BIN=/usr/local/bin/docker
  else
    DOCKER_BIN=docker
  fi
fi

args=()
apply_seen=false
yes_seen=false

for arg in "$@"; do
  case "$arg" in
    --apply)
      apply_seen=true
      ;;
    --yes)
      yes_seen=true
      ;;
  esac
  args+=("$arg")
done

if [[ "$apply_seen" == true && "$yes_seen" == false ]]; then
  args+=(--yes)
fi

if [[ ! -d "$COMPOSE_DIR" ]]; then
  echo "Compose directory not found: $COMPOSE_DIR" >&2
  echo "Set COMPOSE_DIR to the folder containing docker-compose.yml." >&2
  exit 1
fi

cd "$COMPOSE_DIR"

docker_cmd=("$DOCKER_BIN")
if [[ "${EUID:-$(id -u)}" -ne 0 && -n "$SUDO_BIN" ]]; then
  docker_cmd=("$SUDO_BIN" "$DOCKER_BIN")
fi

exec "${docker_cmd[@]}" compose exec -T app \
  python -m app.imports.refresh_all_brokers "${args[@]}"
