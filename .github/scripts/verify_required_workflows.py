#!/usr/bin/env python3
import json
import os
import sys
import time
import urllib.request


def load_runs(repo: str, token: str, head_sha: str) -> list[dict]:
    req = urllib.request.Request(
        f"https://api.github.com/repos/{repo}/actions/runs"
        f"?branch=main&head_sha={head_sha}&event=push&per_page=100",
        headers={
            "Accept": "application/vnd.github+json",
            "Authorization": f"Bearer {token}",
            "X-GitHub-Api-Version": "2022-11-28",
        },
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.load(resp)["workflow_runs"]


def main() -> int:
    repo = os.environ["REPO"]
    token = os.environ["GH_TOKEN"]
    head_sha = os.environ["EVENT_HEAD_SHA"]
    required = {"ci", "deploy-checks", "prod-parity"}

    deadline = time.time() + 900
    latest: dict[str, dict] = {}
    while True:
        latest = {}
        for run in load_runs(repo, token, head_sha):
            name = run["name"]
            if name in required and name not in latest:
                latest[name] = run

        missing = sorted(required - set(latest))
        pending = sorted(
            name
            for name, run in latest.items()
            if run["status"] != "completed"
        )
        failed = sorted(
            name
            for name, run in latest.items()
            if run["status"] == "completed" and run["conclusion"] != "success"
        )
        if not missing and not pending:
            break
        if failed:
            break
        if time.time() >= deadline:
            print(
                "ERROR: timed out waiting for required workflows: "
                f"missing={missing} pending={pending}",
                file=sys.stderr,
            )
            return 1
        print(
            "Waiting for required workflows for "
            f"{head_sha[:7]}: missing={missing} pending={pending}"
        )
        time.sleep(20)

    failed = sorted(
        name
        for name, run in latest.items()
        if run["status"] != "completed" or run["conclusion"] != "success"
    )
    if failed:
        for name in sorted(required):
            run = latest.get(name)
            if run is None:
                print(f"{name}: missing", file=sys.stderr)
            else:
                print(
                    f"{name}: {run['status']} / {run['conclusion']} "
                    f"{run['html_url']}",
                    file=sys.stderr,
                )
        return 1

    for name in sorted(required):
        run = latest[name]
        print(f"{name}: success {run['html_url']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
