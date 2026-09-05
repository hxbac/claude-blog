#!/usr/bin/env bash
#
# Provision a working folder for a non-technical content marketer: one directory
# they open, both claude-blog and claude-seo skills available, everything in
# Vietnamese, no environment variables to export and no paths to remember.
#
#   ./setup-workspace.sh ~/noi-dung
#
# What it creates, all of it regenerable and none of it a copy:
#
#   <target>/.claude/skills/        57 symlinks (32 blog + 25 seo)
#   <target>/.claude/agents/        23 symlinks
#   <target>/.claude/settings.json  absolute helper paths for this machine
#   <target>/scripts  -> claude-blog/scripts
#   <target>/skills   -> claude-blog/skills
#   <target>/CLAUDE.md              routing rules, loaded every session
#   <target>/HUONG-DAN.md           Vietnamese quickstart for the marketer
#   <target>/bai-viet/              where finished posts land
#   ~/.local/bin/claude-seo         exec shim so the seo runtime is on PATH
#
# The two root symlinks are not cosmetic. About thirty claude-blog skills call
# their helpers by repository-relative path (`python3 scripts/blog_render.py`,
# `python3 skills/blog-google/scripts/run.py`), 154 call sites in total, and
# those resolve nowhere unless `scripts` and `skills` exist beside the working
# directory. claude-seo needs neither: its skills go through the `claude-seo run`
# wrapper, whose runtime.py resolves its own location rather than the cwd.
#
# Reverse it by deleting <target>/.claude, the two symlinks, and the
# ~/.local/bin/claude-seo shim. Nothing is written to ~/.claude/.
#
set -euo pipefail

BLOG="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SEO="$(cd "${BLOG}/.." && pwd)/claude-seo"

if [ $# -lt 1 ]; then
    sed -n '2,32p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//'
    exit 2
fi

TARGET="$(eval echo "$1")"
mkdir -p "${TARGET}"
TARGET="$(cd "${TARGET}" && pwd)"

if [ "${TARGET}" = "${BLOG}" ] || [ "${TARGET}" = "${SEO}" ]; then
    echo "ERROR: pick a folder outside the repositories. Drafts would be mixed" >&2
    echo "       into tracked source and show up in every git status." >&2
    exit 1
fi

echo "Workspace: ${TARGET}"
mkdir -p "${TARGET}/.claude/skills" "${TARGET}/.claude/agents" "${TARGET}/bai-viet"

link_into() {
    # $1 = repo root, $2 = label
    local src="$1" label="$2" skills=0 agents=0 name
    if [ ! -d "${src}/skills" ]; then
        echo "  ${label}: not found at ${src}, skipped"
        return
    fi
    for path in "${src}"/skills/*/; do
        name="$(basename "${path}")"
        [ -f "${path}/SKILL.md" ] || continue
        if [ -e "${TARGET}/.claude/skills/${name}" ] && [ ! -L "${TARGET}/.claude/skills/${name}" ]; then
            echo "  WARNING: ${name} exists as a real directory, left alone" >&2
            continue
        fi
        ln -sfn "${src}/skills/${name}" "${TARGET}/.claude/skills/${name}"
        skills=$((skills + 1))
    done
    for path in "${src}"/agents/*.md; do
        [ -f "${path}" ] || continue
        ln -sfn "${path}" "${TARGET}/.claude/agents/$(basename "${path}")"
        agents=$((agents + 1))
    done
    echo "  ${label}: ${skills} skills, ${agents} agents"
}

link_into "${BLOG}" "claude-blog"
link_into "${SEO}" "claude-seo"

# Repository-relative helper paths. See the header note.
ln -sfn "${BLOG}/scripts" "${TARGET}/scripts"
ln -sfn "${BLOG}/skills" "${TARGET}/skills"
echo "  scripts and skills symlinked to claude-blog"

cat > "${TARGET}/.claude/settings.json" <<JSONEOF
{
  "env": {
    "CLAUDE_BLOG_SCRIPTS_DIR": "${BLOG}/scripts",
    "CLAUDE_BLOG_LOAD_UNTRUSTED_HELPER": "${BLOG}/scripts/load_untrusted_root.py"
  }
}
JSONEOF
python3 -c "import json; json.load(open('${TARGET}/.claude/settings.json'))"
echo "  .claude/settings.json written and parsed"

# The claude-seo skills invoke `claude-seo run <script>`, so the wrapper has to
# be resolvable by name. ~/.local/bin is already on PATH on this machine.
#
# A symlink does NOT work here. bin/claude-seo locates runtime.py with
# `dirname "${BASH_SOURCE[0]}"` followed by `pwd -P`, which resolves the
# directory but not the link itself, so a link in ~/.local/bin makes it look for
# ~/.local/scripts/runtime.py and report "runtime is missing". A shim that execs
# the real path avoids changing the launcher, which deliberately uses shell
# built-ins only until it has found a Python interpreter.
if [ -x "${SEO}/bin/claude-seo" ]; then
    mkdir -p "${HOME}/.local/bin"
    rm -f "${HOME}/.local/bin/claude-seo"
    cat > "${HOME}/.local/bin/claude-seo" <<SHIMEOF
#!/usr/bin/env bash
exec "${SEO}/bin/claude-seo" "\$@"
SHIMEOF
    chmod +x "${HOME}/.local/bin/claude-seo"
    case ":${PATH}:" in
        *":${HOME}/.local/bin:"*) echo "  claude-seo shim written to ~/.local/bin (on PATH)" ;;
        *) echo "  claude-seo shim written to ~/.local/bin, but that is NOT on PATH."
           echo "    Add to ~/.bashrc:  export PATH=\"\$HOME/.local/bin:\$PATH\"" ;;
    esac
fi

# CLAUDE.md and HUONG-DAN.md are written once and never overwritten, so a
# marketer's own notes and house rules survive a re-run of this script.
if [ -f "${TARGET}/CLAUDE.md" ]; then
    echo "  CLAUDE.md already exists, left as is"
else
    cat > "${TARGET}/CLAUDE.md" <<'MDEOF'
# Working rules for this folder

This folder belongs to a Vietnamese SEO content marketer who does not write code
and does not type slash commands. They describe what they want in Vietnamese and
expect the work to happen.

## Language

Reply in Vietnamese whenever they write in Vietnamese, including gate failures,
review findings and error messages. Keep English only where it is the actual
token: code, file paths, frontmatter keys, metric names.

## Act, do not offer

"viết cho tôi bài về cách chọn máy pha cà phê" is an instruction to write the
post. Invoke the skill. Never answer a request with the name of the command that
would have satisfied it.

Ask at most one short question when two neighbouring skills genuinely fit. Never
present a menu of options.

## Which family of skills

The two sets overlap by name and not by subject.

| The request is about | Use | Not |
| --- | --- | --- |
| A post being written or already written here | `blog-*` | `seo-*` |
| A live website, its pages, speed, indexing, backlinks | `seo-*` | `blog-*` |
| Keyword volumes and competitor rankings | `seo-dataforseo` | `blog-*` |
| Whether AI assistants cite the content | `blog-geo` for a post, `seo-geo` for a site | |

"kiểm tra SEO bài này" means a draft in `bai-viet/`, so `blog-seo-check`.
"kiểm tra SEO web tôi" means a live URL, so `seo-page` or `seo-audit`.

## Vietnamese posts

- Always set `lang: vi` in the frontmatter unless another language is named.
  Getting this wrong silently scores the post against English patterns and
  costs roughly 30 of the 100 points.
- Always include `slug:` and `canonical:`. Gate 2 and Gate 5 hard-require them.
- A Vietnamese post has no free hero-image path. Openverse indexes English
  metadata only, so a Vietnamese query returns nothing and Gate 2 fails on a
  missing hero. If none of `PEXELS_API_KEY`, `PIXABAY_API_KEY`,
  `UNSPLASH_ACCESS_KEY` or `GOOGLE_AI_API_KEY` is set, say so before writing
  rather than after the gate blocks.
- Register (xưng hô) must not drift inside one post. `bạn` and `mình` for a
  peer voice, `quý khách` and `quý vị` for a formal one, `anh chị` for polite.
  Mixing them is a grammatical defect, not a stylistic choice.

## Where things go

Finished posts and their rendered artifacts belong in `bai-viet/<slug>/`. Do not
write into `scripts/` or `skills/`: both are symlinks into the claude-blog
checkout, and anything written there lands in tracked source.

## Credentials

Every key lives in `~/.claude/.env`. Never ask the user to export a variable,
never print a key, and never write one into a file in this folder. To see what
is configured: `python3 scripts/env_file.py --check`.
MDEOF
    echo "  CLAUDE.md written"
fi

if [ -f "${TARGET}/HUONG-DAN.md" ]; then
    echo "  HUONG-DAN.md already exists, left as is"
else
    cat > "${TARGET}/HUONG-DAN.md" <<MDEOF
# Hướng dẫn dùng thư mục này

Bạn không cần biết code. Chỉ cần mở đúng thư mục rồi nói chuyện bình thường.

## Mở lên

\`\`\`
cd ${TARGET}
claude
\`\`\`

Muốn gọn hơn, thêm dòng này vào cuối file \`~/.bashrc\` một lần:

\`\`\`
alias viet='cd ${TARGET} && claude'
\`\`\`

Từ lần sau chỉ cần gõ \`viet\`.

## Nói gì cũng được

Không cần gõ lệnh có dấu gạch chéo. Cứ nói như nói với đồng nghiệp:

| Bạn muốn | Cứ nói |
| --- | --- |
| Viết bài mới | viết cho tôi bài về cách chọn máy pha cà phê cho quán nhỏ |
| Xem bài được mấy điểm | chấm điểm bài máy pha cà phê giúp tôi |
| Sửa bài cũ cho tốt hơn | viết lại bài này cho chuẩn SEO hơn |
| Lên dàn ý trước | lên dàn ý bài về cách pha cold brew |
| Tra từ khoá | từ khoá "máy pha cà phê" có bao nhiêu lượt tìm kiếm |
| Xem người ta bàn gì | người ta đang nói gì về máy pha cà phê trên mạng |
| Kiểm tra website | kiểm tra SEO website cuahangcaphe.vn |
| Web chậm hay không | web tôi có chậm không |
| Tạo ảnh cho bài | làm ảnh bìa cho bài này |
| Cắt thành post Facebook | chuyển bài này thành mấy post ngắn cho Facebook |

Nói tiếng Việt là được. Nó sẽ trả lời tiếng Việt.

## Bài viết nằm ở đâu

Trong thư mục \`bai-viet/\`. Mỗi bài một thư mục con, bên trong có file
markdown, bản HTML, bản PDF và ảnh bìa.

## Nếu nó báo thiếu key ảnh

Bài tiếng Việt bắt buộc phải có một key ảnh, vì nguồn ảnh miễn phí không cần key
chỉ tìm được theo tiếng Anh. Nhờ người cài đặt mở file \`~/.claude/.env\` và điền
một trong các dòng \`PEXELS_API_KEY\`, \`PIXABAY_API_KEY\`, \`UNSPLASH_ACCESS_KEY\`.
Đăng ký miễn phí, mất khoảng hai phút.

## Có bốn thứ đừng xoá

\`.claude\`, \`scripts\`, \`skills\` và \`CLAUDE.md\`. Đó là phần nối thư mục này với
bộ công cụ. Xoá là mọi thứ ngừng hoạt động. Chúng không chứa bài viết của bạn.

## Muốn dùng phần SEO website

Lần đầu cần chạy một lệnh cài đặt. Mở Claude ở thư mục này rồi nói:

    cài đặt phần seo giúp tôi

Nó sẽ tự chạy \`/seo setup\`. Chỉ cần làm một lần.
MDEOF
    echo "  HUONG-DAN.md written"
fi

echo ""
echo "Done. Hand this to the marketer:"
echo ""
echo "    cd ${TARGET} && claude"
echo ""
echo "Then read ${TARGET}/HUONG-DAN.md"
