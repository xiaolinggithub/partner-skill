#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'USAGE'
Partner installer

Usage:
  bash install.sh [--target codex|claude|agents|all] [--dry-run]
  bash install.sh --status
  bash install.sh --configure [partner-setup-ui.py args...]
  bash install.sh --configure-cli [partner-setup.py args...]

Targets:
  codex   -> ~/.codex/skills/partner-skill  (+ ~/.codex/prompts/idea-king.md)
  claude  -> ~/.claude/skills/partner-skill (+ ~/.claude/skills/idea-king)
  agents  -> ~/.agents/skills/partner-skill (+ ~/.agents/skills/idea-king)
  all     -> all of the above

The idea-king (点子王) companion skill ships with Partner: first-principles
decomposition plus adversarial review, used by Direction B on every work
split. It installs as its own skill directory so both agents can call it.

--status compares every installed copy's .install-meta commit against this
repository's HEAD so stale copies are visible before they cause confusion.

--configure opens the localhost-only single-page setup UI; any extra arguments
are passed to partner-setup-ui.py. --configure-cli keeps the terminal fallback.
USAGE
}

TARGET="codex"
DRY_RUN="false"
STATUS="false"
BACKUP_KEEP=3

while [ "$#" -gt 0 ]; do
  case "$1" in
    --target)
      TARGET="${2:-}"
      shift 2
      ;;
    --target=*)
      TARGET="${1#--target=}"
      shift
      ;;
    --dry-run)
      DRY_RUN="true"
      shift
      ;;
    --status)
      STATUS="true"
      shift
      ;;
    --configure)
      shift
      exec python3 "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/scripts/partner-setup-ui.py" "$@"
      ;;
    --configure-cli)
      shift
      exec python3 "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/scripts/partner-setup.py" --interactive "$@"
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "Unknown argument: $1" >&2
      usage
      exit 2
      ;;
  esac
done

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)"
if [ ! -f "$ROOT/SKILL.md" ]; then
  echo "ERROR: install.sh must run from the partner-skill repository." >&2
  exit 1
fi

source_commit() {
  if git -C "$ROOT" rev-parse --is-inside-work-tree >/dev/null 2>&1; then
    git -C "$ROOT" rev-parse HEAD
  else
    echo "unknown"
  fi
}

host_for_dest() {
  case "$1" in
    "$HOME"/.codex/*) echo "codex" ;;
    "$HOME"/.claude/*) echo "claude" ;;
    "$HOME"/.agents/*) echo "generic" ;;
    *) echo "unknown" ;;
  esac
}

write_install_meta() {
  local meta_path="$1"
  local host="${2:-unknown}"
  {
    printf 'source_commit=%s\n' "$(source_commit)"
    printf 'installed_at=%s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)"
    printf 'host=%s\n' "$host"
  } >"$meta_path"
}

print_status() {
  local kind="$1" path="$2" meta_path="$3" head_commit="$4"
  local exists="false"
  case "$kind" in
    dir) [ -d "$path" ] && exists="true" ;;
    file) [ -f "$path" ] && exists="true" ;;
  esac

  if [ "$exists" != "true" ]; then
    echo "MISSING  $path"
  elif [ ! -f "$meta_path" ]; then
    echo "UNKNOWN  $path (no install meta)"
  else
    installed_commit="$(sed -n 's/^source_commit=//p' "$meta_path")"
    if [ "$installed_commit" = "$head_commit" ]; then
      echo "CURRENT  $path ($installed_commit)"
    else
      echo "STALE    $path (installed $installed_commit, repo at $head_commit)"
    fi
  fi
}

if [ "$STATUS" = "true" ]; then
  head_commit="$(source_commit)"
  echo "repo HEAD: $head_commit"
  for dest in "$HOME/.codex/skills/partner-skill" "$HOME/.claude/skills/partner-skill" "$HOME/.agents/skills/partner-skill"; do
    print_status dir "$dest" "$dest/.install-meta" "$head_commit"
  done
  print_status dir "$HOME/.claude/skills/idea-king" "$HOME/.claude/skills/idea-king/.install-meta" "$head_commit"
  print_status dir "$HOME/.agents/skills/idea-king" "$HOME/.agents/skills/idea-king/.install-meta" "$head_commit"
  print_status file "$HOME/.codex/prompts/idea-king.md" "$HOME/.codex/prompts/idea-king.md.install-meta" "$head_commit"
  exit 0
fi

case "$TARGET" in
  codex) DESTS=("$HOME/.codex/skills/partner-skill") ;;
  claude) DESTS=("$HOME/.claude/skills/partner-skill") ;;
  agents) DESTS=("$HOME/.agents/skills/partner-skill") ;;
  all) DESTS=("$HOME/.codex/skills/partner-skill" "$HOME/.claude/skills/partner-skill" "$HOME/.agents/skills/partner-skill") ;;
  *)
    echo "ERROR: unsupported target '$TARGET'." >&2
    usage
    exit 2
    ;;
esac

copy_payload() {
  # Package only the skill payload. Tracked files when git is available, so
  # local scratch files and logs never ship into the user's skills directory.
  local dest="$1"
  if git -C "$ROOT" rev-parse --is-inside-work-tree >/dev/null 2>&1; then
    git -C "$ROOT" ls-files -z -- . ':!:.github' ':!:docs/TEST.md' \
      | (cd "$ROOT" && tar -cf - --null -T -) \
      | tar -xf - -C "$dest"
  else
    (cd "$ROOT" && find . -type f \
      ! -path './.git/*' \
      ! -path './.github/*' \
      ! -path './docs/TEST.md' \
      ! -name '.DS_Store' \
      -print0 | tar -cf - --null -T -) \
      | tar -xf - -C "$dest"
  fi
}

# Resolve through both leaf and parent symlinks, including not-yet-created targets.
real_path() {
  python3 -B -c 'from pathlib import Path; import sys; print(Path(sys.argv[1]).resolve())' "$1"
}

INSTALLED_DESTS=("")
install_directory() {
  local kind="$1" dest="$2" source target previous
  source="$ROOT"
  [ "$kind" != "idea-king" ] || source="$ROOT/idea-king"
  source="$(real_path "$source")"
  target="$(real_path "$dest")"
  if [ "$source" = "$target" ]; then
    echo "Already installed at $dest (source is the same directory)"
    return 0
  fi
  for previous in "${INSTALLED_DESTS[@]}"; do
    if [ "$previous" = "$target" ] || { [ "$kind" = "idea-king" ] && [ "$target" = "$previous/idea-king" ]; }; then
      echo "Already updated $dest -> $target"
      return 0
    fi
  done
  if [[ "$source/" == "$target/"* || "$target/" == "$source/"* ]]; then
    echo "ERROR: source and install target overlap: $source -> $target" >&2
    return 1
  fi
  if [ -e "$target" ] && [ ! -d "$target" ]; then
    echo "ERROR: install target is not a directory: $target" >&2
    return 1
  fi
  echo "Install $kind -> $dest (real target: $target)"
  if [ "$DRY_RUN" = "true" ]; then
    return 0
  fi

  (
    # Stage beside the real target so replacement stays on the same filesystem.
    stage=""
    backup=""
    cleanup_install() {
      local status=$?
      trap - EXIT
      if [ -n "$backup" ] && [ -d "$backup" ] && [ ! -e "$target" ]; then
        if ! mv "$backup" "$target"; then
          echo "ERROR: restore failed; old install remains at $backup" >&2
          status=1
        fi
      fi
      [ -z "$stage" ] || rm -rf "$stage" # risk-ok: only this invocation's mktemp staging directory
      exit "$status"
    }
    trap cleanup_install EXIT
    trap 'exit 130' INT
    trap 'exit 143' TERM
    mkdir -p "$(dirname "$target")"
    stage="$(mktemp -d "$target.stage.XXXXXX")"
    mkdir "$stage/payload"
    if [ "$kind" = "Partner" ]; then
      copy_payload "$stage/payload"
      for required in install.sh scripts/partner-config.py scripts/partner-tryout.py idea-king/SKILL.md idea-king/codex-prompt.md; do
        if [ ! -s "$stage/payload/$required" ]; then
          echo "ERROR: incomplete install payload: $required" >&2
          exit 1
        fi
      done
      bash -n "$stage/payload/install.sh"
    else
      (cd "$source" && find . -type f ! -name '.DS_Store' ! -name 'codex-prompt.md' -print0 \
        | tar -cf - --null -T -) | tar -xf - -C "$stage/payload"
    fi
    if [ ! -s "$stage/payload/SKILL.md" ]; then
      echo "ERROR: incomplete install payload: SKILL.md" >&2
      exit 1
    fi
    write_install_meta "$stage/payload/.install-meta" "$(host_for_dest "$dest")"
    if [ -e "$target" ]; then
      backup="$target.backup.$(date +%Y%m%d%H%M%S).${stage##*.}"
      echo "Existing install found. Moving it to $backup"
      mv "$target" "$backup"
    fi
    mv "$stage/payload" "$target"
    # Prune only after the replacement succeeds; failed upgrades keep all backups.
    if [ -n "$backup" ]; then
      ls -dt "$target".backup.* 2>/dev/null | tail -n +"$((BACKUP_KEEP + 1))" \
        | while IFS= read -r old_backup; do
            rm -rf "$old_backup" # risk-ok: prunes only our own timestamped backups beyond BACKUP_KEEP
          done
    fi
  )
  INSTALLED_DESTS+=("$target")
}

for dest in "${DESTS[@]}"; do
  install_directory Partner "$dest"
done

install_idea_king_codex_prompt() {
  local dest="$HOME/.codex/prompts/idea-king.md"
  echo "Install idea-king codex prompt -> $dest"
  if [ "$DRY_RUN" = "true" ]; then
    return 0
  fi
  mkdir -p "$HOME/.codex/prompts"
  cp "$ROOT/idea-king/codex-prompt.md" "$dest"
  write_install_meta "$dest.install-meta" "codex"
}

for dest in "${DESTS[@]}"; do
  case "$dest" in
    "$HOME/.claude/skills/partner-skill") install_directory idea-king "$HOME/.claude/skills/idea-king" ;;
    "$HOME/.agents/skills/partner-skill") install_directory idea-king "$HOME/.agents/skills/idea-king" ;;
    "$HOME/.codex/skills/partner-skill") install_idea_king_codex_prompt ;;
  esac
done

echo "Done. Try: 用 Claude Code goal 先规划，你 Codex 来实现。或在 Claude Code 里说：搭子，分工给 codex。"
