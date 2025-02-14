#!/usr/bin/env python3

import requests
import os
import tempfile
import zipfile
import shutil
import pathlib
import logging
import urllib.parse

INDEX_TEMPLATE = """
<!doctype html>
<html lang=en>
<head>
<meta charset=utf-8>
<title>{title}</title>
</head>
<body>
<ul>
{items}
</ul>
</body>
</html>
"""

ITEM_TEMPLATE = """
<li><a href="./{branch_dir}/">{branch}</a></li>
"""

def _paginate(session, url, params=None, item_key=None):
    while True:
        response = session.get(url, params=params)
        response.raise_for_status()
        j = response.json()
        if item_key:
            yield from j[item_key]
        else:
            yield from j
        if not response.links.get("next"):
            break
        url = response.links["next"]["url"]
        params = None


def find_workflow(session, repo, workflow_name):
    for workflow in _paginate(
        session,
        f"https://api.github.com/repos/{repo}/actions/workflows",
        item_key="workflows",
    ):
        if workflow["name"] == workflow_name:
            return workflow

    raise ValueError(f"Workflow '{workflow_name}' not found")


def find_artifact(session, artifacts_url, artifact_name):
    for artifact in _paginate(session, artifacts_url, item_key="artifacts"):
        if artifact["name"] == artifact_name:
            return artifact


def find_latest_artifacts(session, repo, workflow_id, artifact_name):
    artifacts = {}
    for run in _paginate(
        session,
        f"https://api.github.com/repos/{repo}/actions/workflows/{workflow_id}/runs",
        params={"status": "success"},
        item_key="workflow_runs",
    ):
        artifact = find_artifact(session, run["artifacts_url"], artifact_name)
        if not artifact or artifact["expired"]:
            continue

        if run["head_repository"]["full_name"] == repo:
            owner_label = "_"
        else:
            owner_label = run["head_repository"]["owner"]["login"]

        branch = run["head_branch"]
        key = f"{owner_label}/{branch}"

        # Assumes response is sorted, newest to oldest
        if key not in artifacts:
            artifacts[key] = artifact

    return artifacts


def download_and_extract(session, url, dest_dir):
    with session.get(url, stream=True) as response:
        response.raise_for_status()
        with tempfile.TemporaryFile() as f:
            shutil.copyfileobj(response.raw, f)
            zipfile.ZipFile(f).extractall(dest_dir)


def main():
    logging.basicConfig(level=logging.INFO)

    api_token = os.environ["GITHUB_TOKEN"]
    repo = os.environ["GITHUB_REPOSITORY"]
    workflow_name = os.environ["WORKFLOW_NAME"]
    artifact_name = os.environ["ARTIFACT_NAME"]

    session = requests.Session()
    session.headers.update(
        {
            "Authorization": f"Bearer {api_token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        }
    )

    workflow = find_workflow(session, repo, workflow_name)
    web_artifacts = find_latest_artifacts(session, repo, workflow["id"], artifact_name)

    tmpdir = pathlib.Path(tempfile.mkdtemp(prefix="godoctopus-"))
    logging.info("Assembling site at %s", tmpdir)

    items = []
    for branch, artifact in web_artifacts.items():
        url = artifact["archive_download_url"]
        logging.info("Fetching %s export from %s", branch, url)

        branch_quoted = urllib.parse.quote(branch)
        branch_dir = tmpdir / branch_quoted
        branch_dir.mkdir(parents=True)
        download_and_extract(session, url, branch_dir)

        items.append(ITEM_TEMPLATE.format(branch_dir=branch_quoted, branch=branch))

    with open(tmpdir / "index.html", "w") as f:
        f.write(
            INDEX_TEMPLATE.format(
                title="Branches",
                items="".join(items),
            )
        )

    github_output = os.environ.get("GITHUB_OUTPUT")
    if github_output:
        with open(github_output, "a") as f:
            f.write(f"path={tmpdir}\n")


if __name__ == "__main__":
    main()
