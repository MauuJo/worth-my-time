# worth-my-time

A beginner-focused Hacktoberfest issue triage app. It checks a handful of deterministic signals to decide whether a "good first issue" is worth a newcomer's time, then optionally uses a local Ollama model to write a short beginner brief.

## What this project does

The app is designed to help new contributors avoid low-value or hard-to-enter issues. It searches for open GitHub issues labeled "good first issue" and filters them using rules such as:

- whether the issue already looks claimed
- whether there is an open competing PR
- whether the repository is stale or inactive
- whether the repo has a healthy newcomer merge rate
- whether the project includes a CONTRIBUTING guide

It then presents up to 15 candidates with a verdict of Go / Risky / Skip and a reason summary. If the local Ollama model is available, the app can generate a short beginner brief for the selected issue.

## The problem it addresses

Labels like "good first issue" are not enough. A beginner may chase an issue that is already claimed, blocked by a competing PR, or sitting in a repo that does not accept new contributors. This project makes those signals visible and explainable before the contributor spends time on the issue.

## Setup

1. Create and activate a virtual environment:
   - `python -m venv .venv`
   - `source .venv/bin/activate` on macOS/Linux
   - `.venv\Scripts\activate` on Windows
2. Install dependencies:
   - `pip install -r requirements.txt`
   - If you already installed dependencies before updating `requirements.txt`, run `pip install --upgrade -r requirements.txt` in the activated virtual environment.
3. Copy the example environment file:
   - `copy .env.example .env` or `cp .env.example .env`
4. Optional token:
   - Add `GITHUB_TOKEN` to `.env` if you want higher GitHub API limits. The app loads this file automatically.
5. Start Ollama locally and pull the default model:
   - `ollama pull gemma3:4b`

## Running locally

```bash
python app.py
```

Then open the Gradio URL shown in the terminal. The app reads the environment variables below:

- `GITHUB_TOKEN`: optional but recommended for GitHub API rate limits
- `OLLAMA_MODEL`: local model name, default `gemma3:4b`
- `ENABLE_BRIEF`: set to `true` or `false`; default is `true`
- `PORT`: web port, default `7860`

If Ollama is unavailable or `ENABLE_BRIEF=false`, the app still shows verdicts and a clear disabled message for the brief.

## Running tests

```bash
pytest
```

## Render deployment

This project is ready for Render as a Python web service. The included config installs dependencies and starts the app with:

```yaml
buildCommand: pip install -r requirements.txt
startCommand: python app.py
```

The deployed version has briefs disabled because the model runs locally on the machine that starts the app. In `render.yaml`, `ENABLE_BRIEF` is set to `"false"` to keep the deployment simple and reliable. If you want local brief generation, run the model on the same machine that hosts the app or use a dedicated Ollama host.

## Verdict rules

The verdict logic is deterministic and explainable:

- `Go`: score >= 2
- `Risky`: score 0 or 1
- `Skip`: score < 0

Rules used for scoring:

- -3 if the issue looks claimed
- -3 if there are competing open PRs
- -2 if the repository has been inactive for 60+ days
- +2 if newcomer merge rate is >= 0.5
- +1 if median merge time is <= 7 days
- +1 if the issue body is longer than 200 characters
- +1 if a CONTRIBUTING guide exists

Missing data adds a "not enough data" reason instead of guessing.

## Known limitations

- Heuristics are not predictions: they help triage, but do not prove an issue is good or bad.
- GitHub rate limits can still affect live searches, especially without a token.
- The issue search query is based on public GitHub search syntax and may vary if GitHub changes qualifiers.
- GitHub issue search filters by issue labels, not repository topics; the optional Hacktoberfest filter therefore looks for the `hacktoberfest` issue label.
- Local small models can make mistakes when choosing files to mention in a brief.

## How I validated it

- `pytest` passes for the triage and GitHub parsing logic.
- The app can start locally with Python and Gradio.
- Brief generation is intentionally graceful when Ollama is unavailable or disabled.

## License

This project is available under the MIT license as included in the repository.
