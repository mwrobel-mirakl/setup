#!/usr/bin/env python3
"""Per-repository, month-by-month count of PRs opened and PRs reviewed by a
GitHub user since a start date, plus a global total across all repositories.

Usage: gh-pr-stats.py <github-username> <start-date YYYY-MM-DD>
       [--min-contributions X] [--ignore REGEX ...] [--ignore-dependabot]
"""
import argparse
import calendar
import collections
import json
import re
import shutil
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from datetime import date

# GitHub's search API (REST and GraphQL alike) never returns more than 1000
# results for a single query, and silently stops paginating there. To get past
# that, every search is split into one query per calendar month, so the ceiling
# becomes 1000 per month rather than 1000 overall. Note that GitHub drops the
# filter entirely if you pass two range qualifiers on the same field
# (created:>=A created:<B), so the buckets use the inclusive A..B range form.
SEARCH_LIMIT = 1000

# Buckets are independent, so they run concurrently. Kept modest to stay clear
# of GitHub's secondary rate limits.
MAX_WORKERS = 6

OPENED_QUERY = """
query($q: String!, $endCursor: String) {
  search(query: $q, type: ISSUE, first: 100, after: $endCursor) {
    issueCount
    pageInfo { hasNextPage endCursor }
    nodes {
      ... on PullRequest {
        createdAt
        additions
        deletions
        repository { nameWithOwner }
      }
    }
  }
}
"""

# reviews(author:) filters server-side, so one paginated search yields every
# review timestamp directly - no need to walk each PR's reviews individually.
REVIEWED_QUERY = """
query($q: String!, $login: String!, $endCursor: String) {
  search(query: $q, type: ISSUE, first: 50, after: $endCursor) {
    issueCount
    pageInfo { hasNextPage endCursor }
    nodes {
      ... on PullRequest {
        number
        repository { nameWithOwner }
        reviews(first: 100, author: $login) {
          pageInfo { hasNextPage }
          nodes { submittedAt }
        }
      }
    }
  }
}
"""


def search_all(query_doc, search_query, **variables):
    """Run a paginated GraphQL search. Returns (nodes, total_matches)."""
    nodes, cursor, total = [], None, 0
    while True:
        cmd = ["gh", "api", "graphql", "-F", f"query={query_doc}", "-F", f"q={search_query}"]
        for key, value in variables.items():
            cmd += ["-F", f"{key}={value}"]
        if cursor is not None:
            cmd += ["-F", f"endCursor={cursor}"]

        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            sys.exit(f"gh api graphql failed:\n{result.stderr}")

        payload = json.loads(result.stdout)
        if "errors" in payload:
            sys.exit(f"GraphQL error: {json.dumps(payload['errors'])}")

        search = payload["data"]["search"]
        total = search["issueCount"]
        nodes += [node for node in search["nodes"] if node]

        if not search["pageInfo"]["hasNextPage"]:
            return nodes, total
        cursor = search["pageInfo"]["endCursor"]


def next_month(month):
    y, m = int(month[:4]), int(month[5:7])
    m += 1
    if m > 12:
        m = 1
        y += 1
    return f"{y:04d}-{m:02d}"


def month_range(start_month, end_month):
    months = []
    month = start_month
    while month <= end_month:
        months.append(month)
        month = next_month(month)
    return months


def month_buckets(start_date, end_month):
    """One inclusive A..B date range per month, clipped to start_date."""
    buckets = []
    for month in month_range(start_date[:7], end_month):
        last_day = calendar.monthrange(int(month[:4]), int(month[5:7]))[1]
        low = start_date if month == start_date[:7] else f"{month}-01"
        buckets.append((month, f"{low}..{month}-{last_day:02d}"))
    return buckets


def run_buckets(label, buckets, query_doc, query_template, **variables):
    """Fetch every monthly bucket concurrently, warning on any that truncates."""
    print(f"{label} ({len(buckets)} months, {MAX_WORKERS} at a time)...", file=sys.stderr)
    done = 0

    def fetch(bucket):
        month, date_range = bucket
        return month, search_all(query_doc, query_template.format(range=date_range), **variables)

    all_nodes = []
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as pool:
        for month, (nodes, total) in pool.map(fetch, buckets):
            done += 1
            sys.stderr.write(f"\r\033[K  {done}/{len(buckets)} months")
            sys.stderr.flush()
            if total > SEARCH_LIMIT:
                print(
                    f"\r\033[K  warning: {month} has {total} matches but GitHub caps a "
                    f"single search at {SEARCH_LIMIT}; that month is undercounted",
                    file=sys.stderr,
                )
            all_nodes += nodes
    sys.stderr.write("\n")
    return all_nodes


def print_table(title, months, counters, repo_filter=None, all_repos=None):
    """Added/removed lines cover the PRs the user opened, not the ones reviewed."""
    def cell(counter, month):
        if repo_filter is not None:
            return counter.get((repo_filter, month), 0)
        return sum(counter.get((repo, month), 0) for repo in all_repos)

    print(f"== {title} ==")
    print(f"{'Month':<10} {'Opened':>8} {'Reviewed':>9} {'Added':>10} {'Removed':>10}")
    totals = [0] * len(counters)
    for month in months:
        values = [cell(counter, month) for counter in counters]
        totals = [t + v for t, v in zip(totals, values)]
        o, r, added, removed = values
        if o == 0 and r == 0:
            continue
        print(f"{month:<10} {o:>8} {r:>9} {'+' + str(added):>10} {'-' + str(removed):>10}")
    o, r, added, removed = totals
    print(f"{'Total':<10} {o:>8} {r:>9} {'+' + str(added):>10} {'-' + str(removed):>10}")
    print()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("username", help="GitHub username")
    parser.add_argument("start_date", help="Start date, YYYY-MM-DD")
    parser.add_argument(
        "--min-contributions",
        type=int,
        default=0,
        metavar="X",
        help="Skip a repo's own table if opened+reviewed PRs total less than X "
        "(the GLOBAL table still includes it)",
    )
    parser.add_argument(
        "--ignore",
        action="append",
        default=[],
        metavar="REGEX",
        help="Regex matched against 'owner/repo' (e.g. 'config-.*'); matching repos "
        "are dropped entirely, including from the GLOBAL total. May be given "
        "multiple times",
    )
    parser.add_argument(
        "--ignore-dependabot",
        action="store_true",
        help="Exclude Dependabot-authored PRs from the 'reviewed' counts",
    )
    args = parser.parse_args()

    if not re.match(r"^\d{4}-\d{2}-\d{2}$", args.start_date):
        sys.exit("start-date must be YYYY-MM-DD")
    if shutil.which("gh") is None:
        sys.exit("gh CLI not found")

    try:
        ignore_patterns = [re.compile(p) for p in args.ignore]
    except re.error as e:
        sys.exit(f"invalid --ignore regex: {e}")

    def is_ignored(repo):
        return any(p.search(repo) for p in ignore_patterns)

    gh_user = args.username
    start = args.start_date
    start_month = start[:7]
    current_month = date.today().strftime("%Y-%m")
    buckets = month_buckets(start, current_month)

    opened_counts = collections.Counter()
    reviewed_counts = collections.Counter()
    added_counts = collections.Counter()
    removed_counts = collections.Counter()
    repos_seen = set()

    # ---- PRs opened ----
    opened = run_buckets(
        f"Fetching PRs opened by {gh_user} since {start}",
        buckets,
        OPENED_QUERY,
        f"is:pr author:{gh_user} created:{{range}}",
    )
    for pr in opened:
        repo = pr["repository"]["nameWithOwner"]
        if is_ignored(repo):
            continue
        key = (repo, pr["createdAt"][:7])
        opened_counts[key] += 1
        added_counts[key] += pr["additions"]
        removed_counts[key] += pr["deletions"]
        repos_seen.add(repo)

    # ---- PRs reviewed ----
    # Search has no "reviewed at" qualifier, so filter candidates on updated:
    # (any PR reviewed in a given month must have been updated on/after it) and
    # keep only the review timestamps that actually fall in range. The monthly
    # updated: buckets are disjoint, so no PR is counted twice.
    reviewed_query = f"is:pr reviewed-by:{gh_user} updated:{{range}}"
    if args.ignore_dependabot:
        reviewed_query += " -author:app/dependabot"
    reviewed = run_buckets(
        f"Fetching PRs reviewed by {gh_user} since {start}",
        buckets,
        REVIEWED_QUERY,
        reviewed_query,
        login=gh_user,
    )
    for pr in reviewed:
        repo = pr["repository"]["nameWithOwner"]
        if is_ignored(repo):
            continue
        reviews = pr["reviews"]
        if reviews["pageInfo"]["hasNextPage"]:
            print(
                f"  warning: {repo}#{pr['number']} has more than 100 reviews by "
                f"{gh_user}; only the first 100 are counted",
                file=sys.stderr,
            )
        for review in reviews["nodes"]:
            submitted = review["submittedAt"]
            if submitted and submitted[:7] >= start_month:
                reviewed_counts[(repo, submitted[:7])] += 1
                repos_seen.add(repo)

    months = month_range(start_month, current_month)
    counters = (opened_counts, reviewed_counts, added_counts, removed_counts)
    skipped = []
    for repo in sorted(repos_seen):
        total = sum(opened_counts.get((repo, m), 0) + reviewed_counts.get((repo, m), 0) for m in months)
        if total < args.min_contributions:
            skipped.append(repo)
            continue
        print_table(repo, months, counters, repo_filter=repo)
    if skipped:
        print(
            f"(skipped {len(skipped)} repo(s) with fewer than {args.min_contributions} "
            f"contributions: {', '.join(skipped)})",
            file=sys.stderr,
        )
    print_table("GLOBAL", months, counters, all_repos=repos_seen)


if __name__ == "__main__":
    main()
