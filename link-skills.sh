#!/usr/bin/env bash
#
# Wire this checkout into Claude Code as PROJECT skills instead of installing
# into ~/.claude/. Nothing is copied: .claude/skills/<name> is a relative
# symlink to skills/<name>, so `git diff` shows exactly what the agent reads and
# an edit to a SKILL.md is live on the next prompt.
#
# Why this directory and not a separate content folder: about thirty skills call
# their helpers with repository-relative paths (`python3 scripts/blog_render.py`,
# `python3 skills/blog-google/scripts/run.py`). Those resolve only when Claude
# Code runs with this repository root as its working directory.
#
# Usage:
#   ./link-skills.sh              link the blog skills and agents
#   ./link-skills.sh --with-seo   also link ../claude-seo (adds 25 skills)
#   ./link-skills.sh --unlink     remove the wiring, leave the repository alone
#
set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CLAUDE_DIR="${REPO}/.claude"
WITH_SEO=0
UNLINK=0

for arg in "$@"; do
    case "${arg}" in
        --with-seo) WITH_SEO=1 ;;
        --unlink)   UNLINK=1 ;;
        -h|--help)  sed -n '2,18p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//'; exit 0 ;;
        *) echo "unknown option: ${arg}" >&2; exit 2 ;;
    esac
done

if [ "${UNLINK}" -eq 1 ]; then
    # Only ever removes symlinks and the generated settings file. A real
    # directory under .claude/ is left in place, because it is not ours.
    find "${CLAUDE_DIR}/skills" "${CLAUDE_DIR}/agents" -maxdepth 1 -type l -delete 2>/dev/null || true
    rm -f "${CLAUDE_DIR}/settings.json"
    rmdir "${CLAUDE_DIR}/skills" "${CLAUDE_DIR}/agents" "${CLAUDE_DIR}" 2>/dev/null || true
    echo "unlinked. ~/.claude/ was never touched."
    exit 0
fi

mkdir -p "${CLAUDE_DIR}/skills" "${CLAUDE_DIR}/agents"

link_tree() {
    # $1 = absolute source repo, $2 = human label
    local src="$1" label="$2" count=0 name
    [ -d "${src}/skills" ] || { echo "  skipped ${label}: ${src}/skills not found"; return; }
    for path in "${src}"/skills/*/; do
        name="$(basename "${path}")"
        [ -f "${path}/SKILL.md" ] || continue
        ln -sfn "$(realpath --relative-to="${CLAUDE_DIR}/skills" "${src}/skills/${name}")" \
                "${CLAUDE_DIR}/skills/${name}"
        count=$((count + 1))
    done
    echo "  ${label}: ${count} skills"
    count=0
    for path in "${src}"/agents/*.md; do
        [ -f "${path}" ] || continue
        name="$(basename "${path}")"
        ln -sfn "$(realpath --relative-to="${CLAUDE_DIR}/agents" "${path}")" \
                "${CLAUDE_DIR}/agents/${name}"
        count=$((count + 1))
    done
    echo "  ${label}: ${count} agents"
}

echo "Linking project skills into ${CLAUDE_DIR}"
link_tree "${REPO}" "claude-blog"
if [ "${WITH_SEO}" -eq 1 ]; then
    link_tree "$(cd "${REPO}/.." && pwd)/claude-seo" "claude-seo"
fi

# The blog skill resolves its delivery-contract helpers through
# CLAUDE_BLOG_SCRIPTS_DIR, defaulting to $HOME/.claude/scripts. There is no
# global install here, so that default points at nothing and both variables have
# to name this checkout. Absolute paths are required: skills/blog/SKILL.md
# rejects a relative script dir, and the untrusted-context helper is deliberately
# never resolved from the working directory.
cat > "${CLAUDE_DIR}/settings.json" <<JSONEOF
{
  "env": {
    "CLAUDE_BLOG_SCRIPTS_DIR": "${REPO}/scripts",
    "CLAUDE_BLOG_LOAD_UNTRUSTED_HELPER": "${REPO}/scripts/load_untrusted_root.py"
  }
}
JSONEOF
echo "  wrote .claude/settings.json (machine-specific absolute paths)"

python3 -c "import json,sys; json.load(open('${CLAUDE_DIR}/settings.json'))" \
    && echo "  settings.json is valid JSON"

echo ""
echo "Done. Start Claude Code from this directory:"
echo "    cd ${REPO} && claude"
echo ""
echo "Verify with /skills once inside. ~/.claude/ was not modified."
