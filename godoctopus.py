import pdb
#!/usr/bin/env python3
# /// script
# requires-python = ">=3.12"
# dependencies = [
#     "requests",
# ]
# ///

import requests
import os
import tempfile
import zipfile
import shutil
import pathlib
import logging


def main():
    logging.basicConfig(level=logging.INFO)

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
    # TODO: sanitize branch names
    for artifact in response.json()["artifacts"]:
        if artifact["workflow_run"]["repository_id"] != artifact["workflow_run"]["head_repository_id"]:
            # TODO: external PRs
            continue
        if artifact["expired"]:
            continue

        head_branch = artifact["workflow_run"]["head_branch"]
        name = artifact["name"]
        branch_artifacts.setdefault(head_branch, {}).setdefault(name, []).append(artifact)

    tmpdir = pathlib.Path(tempfile.mkdtemp(prefix="godoctopus-"))
    branches_dir = tmpdir / "branches"
    branches_dir.mkdir()

    logging.info("Assembling site at %s", tmpdir)
    url = branch_artifacts["main"]["web"][0]["archive_download_url"]
    logging.info("Fetching main branch export from %s", url)
    with session.get(url, stream=True) as response:
        response.raise_for_status()
        with tempfile.NamedTemporaryFile(suffix=".zip") as f:
            shutil.copyfileobj(response.raw, f)
            zipfile.ZipFile(f).extractall(tmpdir)

    for branch in branch_artifacts:
        if branch == "main":
            continue

        # TODO: invert this, ignore branches without pck
        url = branch_artifacts[branch]["pck"][0]["archive_download_url"]
        logging.info("Fetching %s pck from %s", branch, url)
        with session.get(url, stream=True) as response:
            response.raise_for_status()
            with tempfile.NamedTemporaryFile(suffix=".zip") as f:
                shutil.copyfileobj(response.raw, f)
                zip = zipfile.ZipFile(f)
                pck = zip.open("index.pck", "r")
                with (branches_dir / f"{branch}.pck").open("wb") as target:
                    shutil.copyfileobj(pck, target)

    github_output = os.environ.get("GITHUB_OUTPUT")
    if github_output:
        with open(github_output, "a") as f:
            f.write(f"path={tmpdir}\n")

if __name__ == "__main__":
    main()
