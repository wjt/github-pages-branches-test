#!/usr/bin/env python3
import requests
import os


def main():
    api_token = os.environ.get("GITHUB_TOKEN")
    repo = os.environ.get("GITHUB_REPOSITORY")

    session = requests.Session()
    session.headers.update({
        "Authorization": f"Bearer {api_token}",
        "Accept": f"application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    })

    response = session.get(f"https://api.github.com/repos/{repo}/actions/artifacts", params={"per_page": 100})
    response.raise_for_status()

    branch_artifacts = {}
    # TODO: pagination
    for artifact in response.json()["artifacts"]:
        if artifact["workflow_run"]["repository_id"] != artifact["workflow_run"]["head_repository_id"]:
            # TODO: external PRs
            continue
        if artifact["expired"]:
            continue

        head_branch = artifact["workflow_run"]["head_branch"]
        name = artifact["name"]
        branch_artifacts.setdefault(head_branch, {}).setdefault(name, []).append(artifact)

    print("main")
    print(branch_artifacts["main"]["web"])
    print()
    for branch in branch_artifacts:
        if branch != main:
            print(branch, branch_artifacts[branch]["pck"]["archive_download_url"])

if __name__ == "__main__":
    main()
