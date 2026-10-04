#!/usr/bin/env bash
# Deck Doctor — deploy a git ref to production (simtrack), with automatic rollback.
#
#   sudo /opt/deck-doctor/deploy/deploy.sh            # deploy origin/main
#   sudo /opt/deck-doctor/deploy/deploy.sh <ref>      # a branch, tag or sha
#   sudo /opt/deck-doctor/deploy/deploy.sh --force    # rebuild even if already at the ref
#
# Steps: fetch -> checkout ref (detached) -> pip install (if requirements changed)
#   -> npm ci (if lockfile changed) + next build -> assemble an immutable web release
#   (standalone server + .next/static + public/) under releases/ -> flip the
#   releases/current symlink -> restart deckdoctor-api + deckdoctor-web -> health-check.
# Any failure after the checkout rolls back to the previous commit AND the previous
# web release (no rebuild needed), restarts, and re-checks health. Exit 1 on rollback.
#
# Modelled on simmander-tracker/deploy/auto-deploy.sh, but manual (pushing to main
# does NOT deploy) and with rollback. Data refresh is separate (deckdoctor-refresh).
#
# Runs as root (git/pip/npm run as APP_USER via runuser; systemctl as root), or as
# APP_USER if it has passwordless `sudo -n systemctl restart deckdoctor-*`.

set -uo pipefail
export GIT_TERMINAL_PROMPT=0

# Re-exec from a temp copy: the checkout below rewrites this very file, and bash
# reads scripts incrementally.
if [[ -z "${DD_DEPLOY_REEXEC:-}" ]]; then
    tmp=$(mktemp /tmp/deckdoctor-deploy.XXXXXX.sh) && cp "$0" "$tmp" && chmod 755 "$tmp"
    DD_DEPLOY_REEXEC="$tmp" exec bash "$tmp" "$@"
fi
trap 'rm -f "$DD_DEPLOY_REEXEC"' EXIT

APP_DIR="${APP_DIR:-/opt/deck-doctor}"
APP_USER="${APP_USER:-simmander}"
REMOTE="${REMOTE:-origin}"
API_UNIT="${API_UNIT:-deckdoctor-api.service}"
WEB_UNIT="${WEB_UNIT:-deckdoctor-web.service}"
API_HEALTH="${API_HEALTH:-http://127.0.0.1:8002/health}"
WEB_URL="${WEB_URL:-http://127.0.0.1:3001/deck-doctor}"
WEB_ORIGIN="${WEB_URL%/deck-doctor}"
RELEASES="$APP_DIR/releases"
CURRENT="$RELEASES/current"          # deckdoctor-web WorkingDirectory points here
KEEP_RELEASES="${KEEP_RELEASES:-3}"
HEALTH_TIMEOUT="${HEALTH_TIMEOUT:-120}"   # seconds; the API loads ~30k cards + tables

REF="main"; FORCE=0
for a in "$@"; do
    case "$a" in
        --force) FORCE=1 ;;
        -h|--help) sed -n '2,20p' "$0"; exit 0 ;;
        -*) echo "unknown option: $a" >&2; exit 2 ;;
        *) REF="$a" ;;
    esac
done

T_START=$(date +%s)
log()  { printf '[deploy %s +%ss] %s\n' "$(date -u +%H:%M:%S)" "$(( $(date +%s) - T_START ))" "$*"; }
die()  { log "ERROR: $*"; exit 1; }

if [[ $EUID -eq 0 ]]; then
    as_app() { runuser -u "$APP_USER" -- "$@"; }
    sysctl_() { systemctl "$@"; }
elif [[ "$(id -un)" == "$APP_USER" ]]; then
    as_app() { "$@"; }
    sysctl_() { sudo -n systemctl "$@"; }
else
    die "run as root (sudo) or as $APP_USER"
fi
git_() { as_app git -C "$APP_DIR" "$@"; }

[[ -d "$APP_DIR/.git" ]] || die "$APP_DIR is not a git checkout"
as_app mkdir -p "$RELEASES" || die "cannot create $RELEASES"

# One deploy at a time, and never while the nightly refresh is rewriting data.
exec 9>>"$RELEASES/.deploy.lock" || die "cannot open lock file"
flock -n 9 || die "another deploy is running"
if systemctl is-active --quiet deckdoctor-refresh.service; then
    die "deckdoctor-refresh is running (it executes code from $APP_DIR); retry when it finishes"
fi

# The web unit must serve from the release symlink, or a rebuild would delete the
# files of the running server (next build wipes frontend/.next).
WD=$(systemctl show -p WorkingDirectory --value "$WEB_UNIT" 2>/dev/null || true)
[[ "$WD" == "$CURRENT" ]] || die "$WEB_UNIT WorkingDirectory is '$WD', expected '$CURRENT' — install deploy/systemd/deckdoctor-web.service (see deploy/DEPLOY.md)"

# ── health checks ───────────────────────────────────────────────────────────────
wait_http_200() {   # url, timeout-seconds
    local url=$1 deadline=$(( $(date +%s) + $2 )) code
    while :; do
        code=$(curl -s -o /dev/null -w '%{http_code}' --max-time 10 "$url" || true)
        [[ "$code" == "200" ]] && return 0
        (( $(date +%s) >= deadline )) && { log "  $url -> HTTP $code (gave up)"; return 1; }
        sleep 2
    done
}
healthy() {
    wait_http_200 "$API_HEALTH" "$HEALTH_TIMEOUT" || return 1
    log "  api: $(curl -s --max-time 10 "$API_HEALTH")"
    wait_http_200 "$WEB_URL" 60 || return 1
    # One hashed bundle (.next/static) and one public/ asset must be served too.
    local html chunk
    html=$(curl -s --max-time 10 "$WEB_URL")
    chunk=$(grep -o '/deck-doctor/_next/static/[^"]*\.js' <<<"$html" | head -1)
    [[ -n "$chunk" ]] || { log "  no _next/static chunk referenced by the page"; return 1; }
    wait_http_200 "$WEB_ORIGIN$chunk" 10 || return 1
    if [[ -f "$CURRENT/public/golden-axe.svg" ]]; then
        wait_http_200 "$WEB_ORIGIN/deck-doctor/golden-axe.svg" 10 || return 1
    fi
    log "  web: page + $chunk + public assets 200"
}

restart_units() {
    sysctl_ restart "$API_UNIT" || return 1
    sysctl_ restart "$WEB_UNIT" || return 1
}

# ── resolve the target ──────────────────────────────────────────────────────────
PREV_SHA=$(git_ rev-parse HEAD) || die "cannot read current HEAD"
PREV_REL=$(readlink -f "$CURRENT" 2>/dev/null || true)
log "fetching $REMOTE"
git_ fetch --quiet --prune "$REMOTE" || die "git fetch failed"
if NEW_SHA=$(git_ rev-parse --verify --quiet "$REMOTE/$REF^{commit}"); then :
elif NEW_SHA=$(git_ rev-parse --verify --quiet "$REF^{commit}"); then :
else die "unknown ref '$REF'"; fi

if [[ "$NEW_SHA" == "$PREV_SHA" && "$FORCE" -eq 0 && -n "$PREV_REL" ]]; then
    log "already at ${NEW_SHA:0:7} — nothing to do (use --force to rebuild)"
    exit 0
fi
log "deploying ${PREV_SHA:0:7} -> ${NEW_SHA:0:7} ($REF)"
CHANGED=$(git_ diff --name-only "$PREV_SHA" "$NEW_SHA" || true)
changed() { [[ "$FORCE" -eq 1 ]] || grep -Eq "$1" <<<"$CHANGED"; }

ROLLED_BACK=0
rollback() {
    local why=$1
    log "FAILED: $why — rolling back to ${PREV_SHA:0:7}"
    ROLLED_BACK=1
    git_ checkout --quiet --force --detach "$PREV_SHA" || log "  !! git checkout $PREV_SHA failed"
    if changed '^backend/requirements\.txt$'; then
        as_app "$APP_DIR/.venv/bin/pip" install --quiet -r "$APP_DIR/backend/requirements.txt" \
            || log "  !! pip reinstall failed"
    fi
    if [[ -n "$PREV_REL" && -d "$PREV_REL" ]]; then
        as_app ln -sfn "$PREV_REL" "$CURRENT.tmp" && as_app mv -Tf "$CURRENT.tmp" "$CURRENT"
    fi
    restart_units || log "  !! restart failed"
    if healthy; then
        log "rollback OK — serving ${PREV_SHA:0:7} again"
    else
        log "!! ROLLBACK UNHEALTHY — manual attention needed (journalctl -u $API_UNIT -u $WEB_UNIT)"
    fi
    exit 1
}

# ── 1. checkout ─────────────────────────────────────────────────────────────────
git_ checkout --quiet --force --detach "$NEW_SHA" || rollback "git checkout"

# ── 2. backend deps ─────────────────────────────────────────────────────────────
if changed '^backend/requirements\.txt$'; then
    log "pip install -r backend/requirements.txt"
    as_app "$APP_DIR/.venv/bin/pip" install --quiet -r "$APP_DIR/backend/requirements.txt" \
        || rollback "pip install"
else
    log "skip pip (requirements.txt unchanged)"
fi

# ── 3. frontend build ───────────────────────────────────────────────────────────
FE="$APP_DIR/frontend"
if changed '^frontend/(package|package-lock)\.json$' || [[ ! -d "$FE/node_modules" ]]; then
    log "npm ci"
    as_app bash -c "cd '$FE' && npm ci --no-audit --no-fund --loglevel=error" || rollback "npm ci"
else
    log "skip npm ci (lockfile unchanged)"
fi
log "next build"
as_app env BACKEND_ORIGIN=http://127.0.0.1:8002 NEXT_TELEMETRY_DISABLED=1 \
    bash -c "cd '$FE' && npm run build --silent" || rollback "next build"
[[ -f "$FE/.next/standalone/server.js" ]] || rollback "build produced no .next/standalone/server.js"

# ── 4. assemble an immutable web release (standalone + static + public) ─────────
REL="$RELEASES/web-${NEW_SHA:0:12}-$(date -u +%Y%m%d%H%M%S)"
log "assembling $REL"
as_app bash -c "set -e
    cp -a '$FE/.next/standalone' '$REL'
    mkdir -p '$REL/.next'
    cp -a '$FE/.next/static' '$REL/.next/static'
    if [ -d '$FE/public' ]; then cp -a '$FE/public' '$REL/public'; fi
    echo '$NEW_SHA' > '$REL/REVISION'" || rollback "assembling release"
as_app ln -sfn "$REL" "$CURRENT.tmp" && as_app mv -Tf "$CURRENT.tmp" "$CURRENT" \
    || rollback "switching releases/current"

# ── 5. restart + health ─────────────────────────────────────────────────────────
log "restarting $API_UNIT $WEB_UNIT"
restart_units || rollback "systemctl restart"
log "health checks"
healthy || rollback "health check"

# ── 6. prune old releases (keep current, previous, and the newest N) ────────────
mapfile -t OLD < <(ls -1dt "$RELEASES"/web-* 2>/dev/null | tail -n +$(( KEEP_RELEASES + 1 )))
for d in "${OLD[@]}"; do
    [[ "$(readlink -f "$d")" == "$(readlink -f "$CURRENT")" || "$(readlink -f "$d")" == "$PREV_REL" ]] && continue
    as_app rm -rf "$d" && log "pruned $(basename "$d")"
done

log "deploy OK — ${NEW_SHA:0:7} live (previous ${PREV_SHA:0:7}, release $(basename "$REL"))"
