from triage import verdict


def test_verdict_go():
    issue = {"body": "A detailed bug report with many more than two hundred characters. " * 3}
    label, reasons = verdict(
        issue,
        claimed_flag=False,
        n_prs=0,
        health={"newcomer_merge_rate": 0.75, "median_days_to_merge": 4},
        days_since_push=7,
        has_contributing=True,
    )
    assert label == "Go"
    assert any("newcomer" in reason.lower() for reason in reasons)


def test_verdict_risky():
    issue = {"body": "A detailed issue body with plenty of context for a beginner to read. " * 4}
    label, reasons = verdict(
        issue,
        claimed_flag=False,
        n_prs=0,
        health={"newcomer_merge_rate": 0.45, "median_days_to_merge": 12},
        days_since_push=12,
        has_contributing=False,
    )
    assert label == "Risky"
    assert any("issue" in reason.lower() or "not enough data" in reason.lower() for reason in reasons)


def test_verdict_skip():
    issue = {"body": "Needs a fix and there is already active controversy. " * 5}
    label, reasons = verdict(
        issue,
        claimed_flag=True,
        n_prs=2,
        health={"newcomer_merge_rate": 0.2, "median_days_to_merge": 20},
        days_since_push=90,
        has_contributing=False,
    )
    assert label == "Skip"
    assert any("claimed" in reason.lower() for reason in reasons)


def test_verdict_missing_data():
    issue = {"body": ""}
    label, reasons = verdict(
        issue,
        claimed_flag=None,
        n_prs=None,
        health=None,
        days_since_push=None,
        has_contributing=None,
    )
    assert label == "Risky"
    assert any("not enough data" in reason.lower() for reason in reasons)
