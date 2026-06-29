# Greptile Automation

Doomberg uses Greptile for automated pull request review. The repo-level behavior is controlled by [`greptile.json`](../greptile.json).

## Required GitHub Setup

Greptile review automation is not a normal GitHub Actions job. It requires the Greptile GitHub App to be installed and enabled for this repository.

Required external setup:

1. Install or update the Greptile GitHub App for `joshuajerin/doomberg`.
2. Grant the app access to this repository.
3. Enable reviews for the repository in the Greptile GitHub dashboard.
4. Open or update a pull request targeting `main` or `ui`.

When enabled, Greptile acts as the GitHub App and posts reviews, comments, reactions, and status checks.

## Repo Configuration

`greptile.json` configures automatic review behavior:

- `triggerOnUpdates: true` reviews every new commit pushed to an open PR.
- `statusCheck: true` creates a GitHub check for each review.
- `statusCommentsEnabled: true` keeps the main summary comment enabled.
- `includeBranches: ["main", "ui"]` reviews the production branch and the active UI branch.
- `ignorePatterns` excludes generated output, local build artifacts, lockfiles, and the archived v1 history.

The custom context points Greptile at the setup docs, installer script, and installer tests so it can reason about the expected behavior.

## Local Validation

The repository includes a lightweight workflow that validates `greptile.json` on every push and pull request:

```text
.github/workflows/greptile-config.yml
```

That workflow only validates the config file. The actual code review is performed by the Greptile GitHub App.

## Expected PR Signal

A healthy PR should show:

- GitHub Actions CI checks.
- A Vercel preview if the site or app changed.
- A Greptile status check or review summary after the Greptile app has processed the PR.

If no Greptile signal appears, check the GitHub App installation and the repository enablement in Greptile before changing repo code.
