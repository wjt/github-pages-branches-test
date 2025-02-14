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

ARTIFACT_NAME = "web"


def main():
    logging.basicConfig(level=logging.INFO)

    api_token = os.environ.get("GITHUB_TOKEN")
    repo = os.environ.get("GITHUB_REPOSITORY")

    session = requests.Session()
    session.headers.update(
        {
            "Authorization": f"Bearer {api_token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        }
    )

    response = session.get(
        f"https://api.github.com/repos/{repo}/actions/artifacts",
        params={
            "name": ARTIFACT_NAME,
            "per_page": 100,
        },
    )
    response.raise_for_status()

    web_artifacts = {}
    # TODO: pagination in case of >100
    # TODO: sanitize branch names?
    for artifact in response.json()["artifacts"]:
        if (
            artifact["workflow_run"]["repository_id"]
            != artifact["workflow_run"]["head_repository_id"]
        ):
            # TODO: external PRs
            continue

        if artifact["expired"]:
            continue

        head_branch = artifact["workflow_run"]["head_branch"]

        # Assumes response is sorted, newest to oldest
        if head_branch not in web_artifacts:
            web_artifacts[head_branch] = artifact

    tmpdir = pathlib.Path(tempfile.mkdtemp(prefix="godoctopus-"))
    logging.info("Assembling site at %s", tmpdir)

    items = []
    for branch in web_artifacts:
        url = web_artifacts[branch]["archive_download_url"]
        logging.info("Fetching %s export from %s", branch, url)
        with session.get(url, stream=True) as response:
            response.raise_for_status()
            with tempfile.TemporaryFile() as f:
                shutil.copyfileobj(response.raw, f)

                branch_quoted = urllib.parse.quote(branch)
                branch_dir = tmpdir / branch_quoted
                branch_dir.mkdir()
                zipfile.ZipFile(f).extractall(branch_dir)

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
