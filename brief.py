from __future__ import annotations

import os
import re
from collections import Counter
from typing import Any

STOPWORDS = {
    "a",
    "an",
    "and",
    "as",
    "at",
    "be",
    "by",
    "for",
    "from",
    "in",
    "is",
    "it",
    "of",
    "on",
    "or",
    "the",
    "to",
    "with",
    "this",
    "that",
    "into",
    "your",
    "you",
    "we",
    "can",
    "fix",
    "issue",
    "repo",
    "github",
    "project",
}


def _tokenize(text: str) -> list[str]:
    return re.findall(r"[a-z0-9]+", (text or "").lower())


def rank_issue_paths(issue_title: str, issue_body: str, repo_paths: list[str]) -> list[str]:
    """Rank repo file paths by overlap with the issue title and body."""
    if not repo_paths:
        return []

    issue_text = f"{issue_title or ''} {issue_body or ''}"
    issue_counts = Counter(token for token in _tokenize(issue_text) if token not in STOPWORDS)

    scored: list[tuple[int, str]] = []
    for path in repo_paths:
        path_tokens = [token for token in _tokenize(path.replace("/", " ").replace(".", " ")) if token not in STOPWORDS]
        if not path_tokens:
            continue
        score = sum(issue_counts.get(token, 0) for token in path_tokens)
        scored.append((score, path))

    ranked = [path for _, path in sorted(scored, key=lambda item: (-item[0], item[1]))[:10]]
    return ranked


def _summarize_with_ollama(prompt: str, model_name: str) -> str:
    """Call the local Ollama model and return the response text if available."""
    try:
        import ollama
    except ImportError:  # pragma: no cover - environment specific
        return "Briefs are disabled because Ollama is not installed in this environment."

    client = ollama.Client()
    try:
        response = client.generate(model=model_name, prompt=prompt, options={"temperature": 0.2})
        if isinstance(response, dict):
            if isinstance(response.get("response"), str):
                return response["response"].strip()
            if isinstance(response.get("content"), str):
                return response["content"].strip()
        return str(response).strip()
    except TypeError:
        response = client.chat(
            model=model_name,
            messages=[{"role": "user", "content": prompt}],
            options={"temperature": 0.2},
        )
        if isinstance(response, dict):
            message = response.get("message") or {}
            content = message.get("content") if isinstance(message, dict) else None
            if isinstance(content, str):
                return content.strip()
        return str(response).strip()


def generate_issue_brief(issue: dict[str, Any], repo_paths: list[str] | None = None, contributing_text: str | None = None) -> str:
    """Generate a short beginner brief for a candidate issue, falling back cleanly if the model is unavailable."""
    enabled = os.getenv("ENABLE_BRIEF", "true").lower() not in {"0", "false", "no"}
    if not enabled:
        return "Briefs are disabled because ENABLE_BRIEF is false. The verdicts are still available."

    model_name = os.getenv("OLLAMA_MODEL", "gemma3:4b")
    paths = repo_paths or []
    ranked_paths = rank_issue_paths(issue.get("title", ""), issue.get("body", ""), paths)

    issue_body = (issue.get("body") or "")[:3000]
    contributing = (contributing_text or "")[:3000]
    issue_title = issue.get("title") or "Untitled issue"
    list_text = ", ".join(ranked_paths) if ranked_paths else "not sure which files"

    prompt = (
        "You are helping a beginner contribute to an open-source project. "
        "Write a short beginner-friendly summary and a first contribution checklist.\n\n"
        f"Issue title: {issue_title}\nIssue body: {issue_body}\n\n"
        f"Candidate file paths (use only this list; if none fit, say not sure which files): {list_text}\n\n"
        f"CONTRIBUTING text: {contributing if contributing else 'No CONTRIBUTING text was provided.'}\n\n"
        "Requirements:\n"
        "1. Summarize the issue in 2-3 plain sentences for a beginner.\n"
        "2. List files from the provided list only. If none fit, say 'not sure which files'.\n"
        "3. Give a 4-step first-contribution checklist grounded in the provided CONTRIBUTING text. "
        "If no CONTRIBUTING text exists, say that the project does not provide clear guidance, then give generic steps.\n"
        "Keep the answer concise and easy to read."
    )

    try:
        return _summarize_with_ollama(prompt, model_name)
    except Exception:  # pragma: no cover - model runtime failure path
        return (
            "Brief generation is unavailable right now. Ollama may be offline or the model may not be installed. "
            "The verdict still works without a model-generated brief."
        )
