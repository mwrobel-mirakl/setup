#!/bin/bash
# Claude Code statusline: truecolor gradient status line
# Repo (bold yellow) | branch (bold cyan) | context bar (RGB gradient) + emoji + % | cost (yellow) | velocity (+green/-red) | model (magenta)

input=$(cat)

cwd=$(echo "$input" | jq -r '.workspace.current_dir // .cwd // "."')
model_name=$(echo "$input" | jq -r '.model.display_name // "unknown"')
repo_name=$(echo "$input" | jq -r '.workspace.repo.name // empty')
used_pct=$(echo "$input" | jq -r '.context_window.used_percentage // 0')
cost=$(echo "$input" | jq -r '.cost.total_cost_usd // 0')
lines_added=$(echo "$input" | jq -r '.cost.total_lines_added // 0')
lines_removed=$(echo "$input" | jq -r '.cost.total_lines_removed // 0')
effort=$(echo "$input" | jq -r '.effort.level // empty')
git_worktree=$(echo "$input" | jq -r '.workspace.git_worktree // empty')

[ -z "$repo_name" ] && repo_name=$(basename "$cwd")

# Git branch, skip optional locks to avoid contention
branch=$(git --no-optional-locks -C "$cwd" branch --show-current 2>/dev/null)

# Fallback worktree detection (in case the JSON field is absent): in a linked
# worktree, the git-dir (.git/worktrees/<name>) differs from the common
# (main repo) git-dir.
if [ -z "$git_worktree" ]; then
  git_dir=$(git --no-optional-locks -C "$cwd" rev-parse --git-dir 2>/dev/null)
  common_dir=$(git --no-optional-locks -C "$cwd" rev-parse --git-common-dir 2>/dev/null)
  if [ -n "$git_dir" ] && [ -n "$common_dir" ] && [ "$git_dir" != "$common_dir" ]; then
    git_worktree=$(basename "$(git --no-optional-locks -C "$cwd" rev-parse --show-toplevel 2>/dev/null)")
  fi
fi

RESET=$'\033[0m'
BOLD=$'\033[1m'
DIM=$'\033[2m'

rgb() { printf '\033[38;2;%d;%d;%dm' "$1" "$2" "$3"; }

PIPE="${DIM}$(rgb 100 100 100)|${RESET}"

# ---- Repo name: bold yellow ----
repo_seg="${BOLD}$(rgb 255 215 0)${repo_name}${RESET}"

# ---- Branch: bold cyan, leaf icon, parentheses ----
branch_seg=""
if [ -n "$branch" ]; then
  branch_seg="${BOLD}$(rgb 0 255 255)(🌿 ${branch})${RESET}"
fi

# ---- Worktree indicator: bold orange, only shown in a linked worktree ----
worktree_seg=""
if [ -n "$git_worktree" ]; then
  worktree_seg="${BOLD}$(rgb 255 140 0)🌳 worktree:${git_worktree}${RESET}"
fi

# ---- Context bar: 20 blocks, RGB gradient green->yellow->red, dark gray empty ----
used_int=$(printf '%.0f' "$used_pct" 2>/dev/null || echo 0)
[ -z "$used_int" ] && used_int=0
filled=$(( used_int * 20 / 100 ))
[ "$filled" -gt 20 ] && filled=20
[ "$filled" -lt 0 ] && filled=0

bar=""
for i in $(seq 0 19); do
  if [ "$i" -lt "$filled" ]; then
    read -r r g b <<< "$(awk -v i="$i" 'BEGIN{
      f=i/19;
      gr=0; gg=200; gb=80;
      yr=220; yg=200; yb=0;
      rr=220; rg=40; rb=20;
      if (f<=0.5) {
        t=f/0.5;
        r=gr+(yr-gr)*t; g=gg+(yg-gg)*t; b=gb+(yb-gb)*t;
      } else {
        t=(f-0.5)/0.5;
        r=yr+(rr-yr)*t; g=yg+(rg-yg)*t; b=yb+(rb-yb)*t;
      }
      printf "%d %d %d", r, g, b;
    }')"
    bar="${bar}$(rgb "$r" "$g" "$b")█"
  else
    bar="${bar}$(rgb 60 60 60)█"
  fi
done
bar="${bar}${RESET}"

# ---- Usage emoji + colored percentage ----
if [ "$used_int" -lt 20 ]; then
  emoji="🟢"; pct_color=$(rgb 0 200 80)
elif [ "$used_int" -lt 70 ]; then
  emoji="⚡"; pct_color=$(rgb 220 200 0)
elif [ "$used_int" -lt 90 ]; then
  emoji="🔥"; pct_color=$(rgb 255 140 0)
else
  emoji="🚨"; pct_color=$(rgb 220 40 20)
fi
context_seg="${bar} ${emoji} ${pct_color}${used_int}%${RESET}"

# ---- Session cost: yellow ----
cost_fmt=$(awk -v c="$cost" 'BEGIN{printf "%.4f", c}')
cost_seg="$(rgb 220 200 0)\$${cost_fmt}${RESET}"

# ---- Code velocity: +green / -red ----
velocity_seg="$(rgb 0 200 80)+${lines_added}${RESET} $(rgb 220 40 20)-${lines_removed}${RESET}"

# ---- Model: white, with effort in parentheses ----
model_label="${model_name}"
[ -n "$effort" ] && model_label="${model_label} (${effort})"
model_seg="$(rgb 255 255 255)🤖 ${model_label}${RESET}"

# ---- Assemble ----
segments=("$repo_seg")
[ -n "$branch_seg" ] && segments+=("$branch_seg")
[ -n "$worktree_seg" ] && segments+=("$worktree_seg")
segments+=("$context_seg" "$cost_seg" "$velocity_seg" "$model_seg")

output="${segments[0]}"
for ((i = 1; i < ${#segments[@]}; i++)); do
  output="${output} ${PIPE} ${segments[$i]}"
done

printf '%s' "$output"
