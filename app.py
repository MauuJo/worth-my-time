from __future__ import annotations

import os
from typing import Any

import gradio as gr
import pandas as pd
from dotenv import load_dotenv

import brief
import gh
from triage import verdict

load_dotenv()


def infer_languages(username: str) -> list[str]:
    """Infer the top 3 languages from a user's public repositories."""
    username = (username or "").strip()
    if not username:
        return []

    try:
        user_repos = gh.gh(f"/users/{username}/repos", per_page=100)
    except Exception:
        return []
    if not isinstance(user_repos, list):
        return []

    language_counts: dict[str, int] = {}
    for repo in user_repos[:30]:
        repo_name = repo.get("name")
        if not repo_name:
            continue
        try:
            repo_langs = gh.gh(f"/repos/{username}/{repo_name}/languages")
        except Exception:
            continue
        for language, bytes_count in repo_langs.items():
            language_counts[language] = language_counts.get(language, 0) + int(bytes_count)

    ranked = sorted(language_counts.items(), key=lambda item: item[1], reverse=True)
    return [language for language, _ in ranked[:3]]


def parse_languages(raw_value: str) -> list[str]:
    """Normalize a comma-separated language list into lowercase names."""
    if not raw_value:
        return []
    return [part.strip().lower() for part in raw_value.split(",") if part.strip()]


def issue_rows_for_language(language: str, include_hacktoberfest: bool) -> list[dict[str, Any]]:
    """Fetch candidate issues and score each one with triage rules."""
    issues = gh.find_issues(language, 15, include_hacktoberfest=include_hacktoberfest)
    rows: list[dict[str, Any]] = []
    for issue in issues:
        owner = issue.get("owner")
        repo = issue.get("repo")
        number = issue.get("number")
        if not owner or not repo or number is None:
            continue

        try:
            claimed = gh.claimed(owner, repo, number)
        except RuntimeError:
            claimed = None
        try:
            competing = gh.competing_prs(owner, repo, number)
        except RuntimeError:
            competing = None
        health = gh.repo_health(owner, repo)
        pushed_days = gh.days_since_push(owner, repo)
        try:
            contributing = gh.has_contributing(owner, repo)
        except RuntimeError:
            contributing = None
        label, reasons = verdict(issue, claimed, competing, health, pushed_days, contributing)

        rows.append(
            {
                "repo": f"{owner}/{repo}",
                "issue_title": issue.get("title", "Untitled issue"),
                "issue_url": issue.get("html_url"),
                "verdict": label,
                "reasons": "; ".join(reasons),
                "owner": owner,
                "repo_name": repo,
                "number": number,
            }
        )
    return rows


def find_issues_action(username: str, languages: str, include_hacktoberfest: bool) -> tuple[pd.DataFrame, gr.Dropdown, list[dict[str, Any]], str]:
    """Search GitHub and return a DataFrame of scored issues."""
    manual = parse_languages(languages)
    chosen_langs = infer_languages(username) if username else []
    if not chosen_langs and manual:
        chosen_langs = manual

    if not chosen_langs:
        empty_df = pd.DataFrame(columns=["repo", "issue title", "verdict", "reasons"])
        return empty_df, gr.Dropdown(choices=[]), [], "Enter a username or a comma-separated language list to search."

    rows: list[dict[str, Any]] = []
    status_message = "Ready."
    errors: list[str] = []
    for language in chosen_langs[:3]:
        remaining = 15 - len(rows)
        if remaining <= 0:
            break
        try:
            language_rows = issue_rows_for_language(language, include_hacktoberfest)
            rows.extend(language_rows[:remaining])
        except RuntimeError as exc:
            errors.append(str(exc))
            continue

    rows = sorted(
        rows,
        key=lambda item: (
            0 if item["verdict"] == "Go" else 1 if item["verdict"] == "Risky" else 2,
            item["repo"],
        ),
    )
    if not rows:
        empty_df = pd.DataFrame(columns=["repo", "issue title", "verdict", "reasons"])
        if errors:
            return empty_df, gr.Dropdown(choices=[]), [], "GitHub search failed: " + " ".join(dict.fromkeys(errors))
        return empty_df, gr.Dropdown(choices=[]), [], "No issues matched the current filters."

    data = pd.DataFrame(rows, columns=["repo", "issue_title", "verdict", "reasons"])
    data["issue title"] = data["issue_title"]
    data = data[["repo", "issue title", "verdict", "reasons"]]
    issue_dropdown = gr.Dropdown(
        choices=[f"{row['repo']} — {row['issue_title']}" for row in rows],
        value=None,
        label="Selected issue",
    )
    status_message = f"Found {len(rows)} candidate issues across {len(chosen_langs[:3])} languages."
    if errors:
        status_message += " Some searches failed: " + " ".join(dict.fromkeys(errors))
    return data, issue_dropdown, rows, status_message


def generate_brief_from_selection(selection: str | None, issue_rows: list[dict[str, Any]]) -> str:
    """Generate a brief for the chosen issue row."""
    if not selection or not issue_rows:
        return "Select an issue to generate a brief."

    selected_name = selection.split(" — ", 1)[0]
    selected_issue = None
    for row in issue_rows:
        if row.get("repo") == selected_name:
            selected_issue = row
            break
    if selected_issue is None:
        return "The selected issue could not be found."

    owner = selected_issue["owner"]
    repo = selected_issue["repo_name"]
    number = selected_issue["number"]
    try:
        issue = gh.gh(f"/repos/{owner}/{repo}/issues/{number}")
    except RuntimeError:
        issue = {
            "title": selected_issue["issue_title"],
            "body": "",
        }

    repo_paths = gh.repo_file_paths(owner, repo)
    contributing_text = gh.fetch_contributing(owner, repo)
    brief_text = brief.generate_issue_brief(issue, repo_paths=repo_paths, contributing_text=contributing_text)
    return brief_text


with gr.Blocks(title="worth-my-time") as demo:
    gr.Markdown("# worth-my-time\nFind Hacktoberfest-friendly issues that are worth your time.")

    with gr.Row():
        username_box = gr.Textbox(label="GitHub username", placeholder="octocat")
        language_box = gr.Textbox(label="Languages (comma-separated)", placeholder="python, javascript")
        hacktoberfest_box = gr.Checkbox(label="Only issues with hacktoberfest label", value=False)

    with gr.Row():
        find_button = gr.Button("Find issues")

    result_table = gr.DataFrame(
        value=pd.DataFrame(columns=["repo", "issue title", "verdict", "reasons"]),
        headers=["repo", "issue title", "verdict", "reasons"],
        interactive=False,
    )
    issue_selector = gr.Dropdown(label="Selected issue", choices=[])
    issue_state = gr.State(value=[])
    status_line = gr.Markdown("Ready to search.")

    with gr.Row():
        generate_button = gr.Button("Generate brief")
        clear_button = gr.Button("Clear")

    brief_output = gr.Markdown("Select an issue to generate a brief.")

    with gr.Accordion("How the verdict works", open=False):
        gr.Markdown(
            "- Go: score >= 2.\n"
            "- Risky: score is 0 or 1.\n"
            "- Skip: score is negative.\n"
            "- Points: -3 for claimed issues or competing PRs, -2 for repos inactive 60+ days, +2 for strong newcomer merge rates, +1 for quick merges, +1 for detailed issue bodies, +1 for a CONTRIBUTING guide.\n"
            "- Missing data adds a 'not enough data' reason instead of guessing."
        )

    def _search(username: str, languages: str, include_hacktoberfest: bool):
        data, issue_dropdown, rows, status = find_issues_action(username, languages, include_hacktoberfest)
        return data, issue_dropdown, rows, status

    find_button.click(
        _search,
        inputs=[username_box, language_box, hacktoberfest_box],
        outputs=[result_table, issue_selector, issue_state, status_line],
    )

    def _brief_for_selection(selection: str, rows: list[dict[str, Any]]):
        return generate_brief_from_selection(selection, rows)

    generate_button.click(
        _brief_for_selection,
        inputs=[issue_selector, issue_state],
        outputs=[brief_output],
    )

    clear_button.click(
        lambda: (
            pd.DataFrame(columns=["repo", "issue title", "verdict", "reasons"]),
            [],
            "Select an issue to generate a brief.",
            "Ready to search.",
        ),
        outputs=[result_table, issue_state, brief_output, status_line],
    )

    if __name__ == "__main__":
        demo.launch(server_name="0.0.0.0", server_port=int(os.getenv("PORT", "7860")))
