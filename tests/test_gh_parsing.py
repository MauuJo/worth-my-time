import gh
from brief import rank_issue_paths
import app


def test_claim_phrase_detection_positive(monkeypatch):
    def fake_gh(path, **params):
        return [{"body": "I'd like to work on this bug."}]

    monkeypatch.setattr(gh, "gh", fake_gh)
    assert gh.claimed("octo", "hello-world", 42) is True


def test_claim_phrase_detection_negative(monkeypatch):
    def fake_gh(path, **params):
        return [{"body": "Thanks for the suggestion. This is a great improvement."}]

    monkeypatch.setattr(gh, "gh", fake_gh)
    assert gh.claimed("octo", "hello-world", 42) is False


def test_parse_owner_repo():
    assert gh.parse_owner_repo("https://api.github.com/repos/octocat/hello-world") == ("octocat", "hello-world")
    assert gh.parse_owner_repo("https://github.com/octocat/hello-world") == ("octocat", "hello-world")


def test_find_issues_uses_issue_labels_and_optional_hacktoberfest_label(monkeypatch):
    queries = []

    def fake_gh(path, **params):
        queries.append(params["q"])
        return {"items": []}

    monkeypatch.setattr(gh, "gh", fake_gh)
    gh.find_issues("python", 15)
    gh.find_issues("python", 15, include_hacktoberfest=True)

    assert 'label:"good first issue"' in queries[0]
    assert "topic:hacktoberfest" not in queries[0]
    assert "label:hacktoberfest" in queries[1]


def test_find_issues_action_builds_selector_after_display_column_rename(monkeypatch):
    issue_row = {
        "repo": "octo/project",
        "issue_title": "Document setup",
        "issue_url": "https://github.com/octo/project/issues/1",
        "verdict": "Go",
        "reasons": "Has contribution guidance",
        "owner": "octo",
        "repo_name": "project",
        "number": 1,
    }
    monkeypatch.setattr(app, "infer_languages", lambda username: ["python"])
    monkeypatch.setattr(app, "issue_rows_for_language", lambda language, include: [issue_row])

    dataframe, selector, rows, status = app.find_issues_action("octo", "", False)

    assert list(dataframe.columns) == ["repo", "issue title", "verdict", "reasons"]
    assert [choice[0] for choice in selector.choices] == ["octo/project — Document setup"]
    assert rows == [issue_row]
    assert status.startswith("Found 1 candidate issue")


def test_issue_keyword_ranking():
    ranked = rank_issue_paths(
        "Fix README docs",
        "The CLI docs are missing examples for setup and troubleshooting.",
        [
            "src/cli.py",
            "README.md",
            "docs/troubleshooting.md",
            "docs/api.md",
            "tests/test_cli.py",
        ],
    )
    assert ranked
    assert "README.md" in ranked[:3]
    assert len(ranked) <= 10
