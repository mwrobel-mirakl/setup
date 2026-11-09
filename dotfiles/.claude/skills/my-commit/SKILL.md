---
name: commit
description: Create a git commit whose subject and body follow Financial Services team commit message conventions (ticket-prefixed imperative subject, structured What/Why/How/Anything-else body). Use whenever the user asks to commit, create a commit, write or update a commit message, in any repository.
---

# Commit message conventions

## Subject line

`[TICKET-ID] Imperative, capitalized description`

- Prefix with the ticket ID in brackets (e.g. `[CIMA-2644]`) only when the change is tied to a tracked issue.
  Get the project key from `git log --oneline -20` or the branch name; never invent one.
  No ticket → omit the prefix entirely, don't substitute a `chore:`-style tag.
- Write the description in the imperative mood ("Add", "Fix", "Remove", "Improve", "Bump", ...), capitalized, no
  trailing period.
- Never append a PR number — the git host adds that automatically on merge.
- One line, as short as possible while staying descriptive.

Examples: `[CIMA-2622] Improve DR74 / DR75 error management`, `Reduce document sync retry duration when disabled`,
`Fix jooq generation`.

## Body

Leave a blank line after the subject, then structure the body as markdown sections, in this order, using this exact
heading text:

```
## What ?

<what the change does>

## Why ?

<the motivation / problem being solved>

## How ?

<implementation notes, only when they add information beyond "What">

## Anything else ?

<caveats, deliberately out-of-scope items, follow-ups, links, anything that doesn't fit above>
```

Rules for the body:

- Keep it brief — a few sentences per section at most. The body explains, it doesn't document; skip restating what the
  diff already shows.
- `## What ?` and `## Why ?` are the minimum for any non-trivial change.
- `## How ?` — only when there's implementation detail worth calling out beyond "What".
- `## Anything else ?` — only for out-of-scope notes, benchmarks, links, or follow-ups.
- A genuinely trivial commit (dependency bump, typo fix) may skip the body, or keep just What/Why.
- Use normal markdown inside sections: backticks, `**bold**`, `-` lists, `[text](url)` links.
- Don't hard-wrap prose — one sentence per line, however long, and let the terminal/host soft-wrap it.

## Workflow

1. Check `git status`/`git diff` and `git log --oneline -20` for the ticket-prefix convention.
2. Draft the subject and body per the rules above.
3. Commit via heredoc: `git commit -m "$(cat <<'EOF'\n...\nEOF\n)"`, plus any other repo/session commit rules already in
   effect (e.g. `Co-Authored-By:` trailers).
