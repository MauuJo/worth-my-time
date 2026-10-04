from __future__ import annotations

import base64
import os
import re
import statistics
import time
from datetime import datetime, timezone
from typing import Any
from urllib.parse import quote

import requests
from dotenv import load_dotenv

GITHUB_API = "https://api.github.com"
CACHE_TTL_SECONDS = 600
_CACHE: dict[tuple[str, tuple[tuple[str, str], ...]], tuple[float, Any]] = {}
load_dotenv()
CLAIM_PATTERNS = [
    re.compile(r"\bcan\s+i\s+(work on|take)\b", re.IGNORECASE),
    re.compile(r"\bi'd\s+like\s+to\s+work\s+on\b", re.IGNORECASE),
    re.compile(r"\bassign\s+(this\s+to\s+me|me)\b", re.IGNORECASE),
    re.compile(r"\bworking\s+on\s+this\b", re.IGNORECASE),
    re.compile(r"\bi['’]?ll\s+take\b", re.IGNORECASE),
]
NEWCOMER_ASSOCIATIONS = {"NONE", "FIRST_TIMER", "FIRST_TIME_CONTRIBUTOR"}


def gh(path: str, **params: Any) -> Any:
    """Call the GitHub REST API with a small in-memory cache and friendly errors."""
    url = path if path.startswith("http") else f"{GITHUB_API}{path}"
    cache_key = (url, tuple(sorted((str(k), str(v)) for k, v in params.items())))
    now = time.time()
    cached = _CACHE.get(cache_key)
    if cached is not None and (now - cached[0]) < CACHE_TTL_SECONDS:
        return cached[1]

    headers = {
        "Accept": "application/vnd.github+json",
        "User-Agent": "worth-my-time/1.0",
    }
    token = os.getenv("GITHUB_TOKEN")
    if token:
        headers["Authorization"] = f"Bearer {token}"

    try:
        response = requests.get(url, params=params or None, headers=headers, timeout=20)
    except requests.RequestException as exc:  # pragma: no cover - network path
        raise RuntimeError(f"GitHub request failed for {url}: {exc}") from exc

    if response.status_code == 403:
        remaining = response.headers.get("X-RateLimit-Remaining")
        if remaining == "0" or "rate limit" in response.text.lower():
            raise RuntimeError(
                "GitHub API rate limit reached. Add a GITHUB_TOKEN to the environment "
                "to avoid rate-limit failures."
            )
        raise RuntimeError(f"GitHub API request was forbidden: {response.text[:220]}")

    if response.status_code == 422:
        raise RuntimeError(
            "GitHub search returned a 422 error. The query or qualifier syntax may be invalid."
        )

    if response.status_code >= 400:
        raise RuntimeError(f"GitHub API error {response.status_code}: {response.text[:220]}")

    data = response.json()
    _CACHE[cache_key] = (now, data)
    return data


def parse_owner_repo(repository_url: str | None) -> tuple[str, str]:
    """Extract owner and repo from a repository URL or repository_url value."""
    if not repository_url:
        return "", ""
    cleaned = repository_url.rstrip("/")
    segments = [segment for segment in cleaned.split("/") if segment]
    if len(segments) >= 2 and "repos" in segments:
        index = segments.index("repos")
        if index + 2 < len(segments):
            return segments[index + 1], segments[index + 2]
    if len(segments) >= 2:
        return segments[-2], segments[-1]
    return "", ""


def find_issues(lang: str, n: int, include_hacktoberfest: bool = False) -> list[dict[str, Any]]:
    """Search open beginner-friendly issues in a given language, capped to n items."""
    normalized_lang = (lang or "").strip()
    if not normalized_lang:
        return []
    qualifiers = [
        f"language:{normalized_lang}",
        'label:"good first issue"',
        "is:issue",
        "is:open",
        "no:assignee",
    ]
    if include_hacktoberfest:
        qualifiers.append("label:hacktoberfest")

    payload = gh(
        "/search/issues",
        q=" ".join(qualifiers),
        sort="updated",
        order="desc",
        per_page=min(max(1, n), 100),
    )

    items = payload.get("items", [])[:n]
    issues: list[dict[str, Any]] = []
    for item in items:
        owner, repo = parse_owner_repo(item.get("repository_url"))
        issues.append(
            {
                "id": item.get("id"),
                "number": item.get("number"),
                "title": item.get("title"),
                "body": item.get("body") or "",
                "html_url": item.get("html_url"),
                "repository_url": item.get("repository_url"),
                "owner": owner,
                "repo": repo,
                "labels": [label.get("name", "") for label in item.get("labels", [])],
            }
        )
    return issues


def claimed(owner: str, repo: str, number: int) -> bool:
    """Checks the issue comments for claim phrases used by newcomers."""
    comments = gh(f"/repos/{owner}/{repo}/issues/{number}/comments", per_page=30)
    if not isinstance(comments, list):
        return False
    for comment in comments[:30]:
        body = (comment.get("body") or "")
        if any(pattern.search(body) for pattern in CLAIM_PATTERNS):
            return True
    return False


def competing_prs(owner: str, repo: str, number: int) -> int:
    """Count open PRs that reference this issue number using the GitHub search API."""
    query = f'repo:{owner}/{repo} is:pr is:open "#{number}"'
    payload = gh("/search/issues", q=query, per_page=100)
    return int(payload.get("total_count", 0))


def fetch_contributing(owner: str, repo: str) -> str | None:
    """Fetch the repository CONTRIBUTING file content if it exists."""
    try:
        entries = gh(f"/repos/{owner}/{repo}/contents")
    except RuntimeError:
        return None
    if not isinstance(entries, list):
        return None

    names = [entry.get("name", "") for entry in entries]
    chosen = None
    for name in names:
        normalized = name.lower()
        if normalized == "contributing" or normalized.startswith("contributing."):
            chosen = name
            break
    if not chosen:
        return None

    try:
        file_info = gh(f"/repos/{owner}/{repo}/contents/{quote(chosen)}")
    except RuntimeError:
        return None
    if not isinstance(file_info, dict):
        return None
    content = file_info.get("content")
    if not content:
        return None
    return base64.b64decode(content).decode("utf-8", errors="replace")


def has_contributing(owner: str, repo: str) -> bool:
    """Return True when a CONTRIBUTING file exists for the repo."""
    return fetch_contributing(owner, repo) is not None


def repo_file_paths(owner: str, repo: str) -> list[str]:
    """Return repository file paths from the git tree API, capped at 3000 entries."""
    try:
        repo_meta = gh(f"/repos/{owner}/{repo}")
    except RuntimeError:
        return []
    default_branch = repo_meta.get("default_branch")
    if not default_branch:
        return []
    try:
        root_tree = gh(f"/repos/{owner}/{repo}/git/trees/{default_branch}?recursive=1")
    except RuntimeError:
        return []
    tree = root_tree.get("tree", [])
    paths = [item.get("path") for item in tree if item.get("type") == "blob" and item.get("path")]
    return paths[:3000]


def days_since_push(owner: str, repo: str) -> int | None:
    """Return the age of the last push in days, if the repo metadata is available."""
    try:
        repo_meta = gh(f"/repos/{owner}/{repo}")
    except RuntimeError:
        return None
    pushed_at = repo_meta.get("pushed_at")
    if not pushed_at:
        return None
    pushed_at_dt = datetime.fromisoformat(pushed_at.replace("Z", "+00:00"))
    now = datetime.now(timezone.utc)
    return max(0, int((now - pushed_at_dt).total_seconds() // 86400))


def repo_health(owner: str, repo: str) -> dict[str, float | int | None] | None:
    """Summarize the health of a repository from recent closed PRs."""
    try:
        pulls = gh(f"/repos/{owner}/{repo}/pulls", state="closed", sort="updated", direction="desc", per_page=30)
    except RuntimeError:
        return None
    if not isinstance(pulls, list) or not pulls:
        return None

    merged_prs = []
    newcomer_merged = 0
    newcomer_total = 0
    for pull in pulls:
        if not pull.get("merged_at") and pull.get("state") == "closed":
            continue
        if pull.get("state") != "closed":
            continue

        if pull.get("merged_at"):
            created = datetime.fromisoformat(pull["created_at"].replace("Z", "+00:00"))
            merged = datetime.fromisoformat(pull["merged_at"].replace("Z", "+00:00"))
            days = (merged - created).total_seconds() / 86400
            merged_prs.append(days)

        author_association = pull.get("author_association")
        if author_association in NEWCOMER_ASSOCIATIONS:
            newcomer_total += 1
            if pull.get("merged_at"):
                newcomer_merged += 1

    if not pulls:
        return None

    total_closed = len(pulls)
    overall_rate = (sum(1 for pull in pulls if pull.get("merged_at")) / total_closed) if total_closed else None
    newcomer_rate = (newcomer_merged / newcomer_total) if newcomer_total else None
    median_days = statistics.median(merged_prs) if merged_prs else None
    return {
        "overall_merge_rate": overall_rate,
        "newcomer_merge_rate": newcomer_rate,
        "median_days_to_merge": median_days,
    }
