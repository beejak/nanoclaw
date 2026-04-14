#!/usr/bin/env bash
# memory_backup.sh — back up Claude auto-memory files to fin-assistant store
#
# Run modes:
#   ./memory_backup.sh          one-shot backup (used by cron fallback)
#   ./memory_backup.sh --watch  inotifywait listener mode (used by systemd)
#
# On any change to /root/.claude/projects/-root/memory/:
#   - Copies all .md files to store/memory_backup/
#   - Writes a manifest with timestamps
#   - Logs to logs/memory_backup.log

set -euo pipefail

MEMORY_DIR="/root/.claude/projects/-root/memory"
BACKUP_DIR="/root/fin-assistant/store/memory_backup"
LOG="/root/fin-assistant/logs/memory_backup.log"
MANIFEST="$BACKUP_DIR/manifest.txt"

mkdir -p "$BACKUP_DIR"
mkdir -p "$(dirname "$LOG")"

log() { echo "[$(TZ=Asia/Kolkata date '+%Y-%m-%d %H:%M:%S IST')] $*" | tee -a "$LOG"; }

do_backup() {
    local reason="${1:-manual}"
    local count=0
    for f in "$MEMORY_DIR"/*.md; do
        [ -f "$f" ] || continue
        cp "$f" "$BACKUP_DIR/"
        count=$((count + 1))
    done
    # Write manifest
    {
        echo "backup_time=$(TZ=Asia/Kolkata date '+%Y-%m-%d %H:%M:%S IST')"
        echo "reason=$reason"
        echo "files=$count"
        for f in "$BACKUP_DIR"/*.md; do
            [ -f "$f" ] || continue
            echo "  $(basename "$f")  $(wc -l < "$f") lines  $(date -r "$f" '+%Y-%m-%d %H:%M')"
        done
    } > "$MANIFEST"
    log "Backed up $count memory files (reason: $reason)"
}

if [[ "${1:-}" == "--watch" ]]; then
    log "Memory watcher started — watching $MEMORY_DIR"
    # Initial backup on start
    do_backup "watcher_start"
    # Watch for create/modify/move events
    inotifywait -m -r -e close_write,create,moved_to "$MEMORY_DIR" 2>/dev/null \
    | while read -r _dir _event _file; do
        [[ "$_file" == *.md ]] || continue
        log "Change detected: $_event $_file"
        do_backup "$_event:$_file"
    done
else
    do_backup "cron_fallback"
fi
