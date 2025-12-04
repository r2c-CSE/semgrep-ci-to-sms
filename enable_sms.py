#!/usr/bin/env python3
import os
import sys
import argparse
import urllib.parse
import requests

BASE_URL = "https://semgrep.dev/api/v1"


def get_headers(api_token: str) -> dict:
    return {
        "Authorization": f"Bearer {api_token}",
        "Accept": "application/json",
    }


def resolve_deployment_slug(api_token: str, explicit_slug: str = None) -> str:
    """
    If explicit_slug is provided, use it.
    Otherwise, fetch /deployments and use the first one from the list.
    """
    if explicit_slug:
        print(f"[INFO] Using provided deployment slug: {explicit_slug}")
        return explicit_slug

    url = f"{BASE_URL}/deployments"
    headers = get_headers(api_token)

    resp = requests.get(url, headers=headers)
    if resp.status_code != 200:
        print(f"[ERROR] Failed to list deployments ({resp.status_code}): {resp.text}", file=sys.stderr)
        sys.exit(1)

    data = resp.json()
    deployments = data.get("deployments") or []

    if not deployments:
        print("[ERROR] No deployments found for this token.", file=sys.stderr)
        sys.exit(1)

    if len(deployments) > 1:
        print(
            "[WARN] Multiple deployments found; using the first one. "
            "If this is not what you want, pass --deployment-slug explicitly.",
            file=sys.stderr,
        )

    chosen = deployments[0]
    slug = chosen.get("slug")
    if not slug:
        print("[ERROR] First deployment has no 'slug' field.", file=sys.stderr)
        print(chosen)
        sys.exit(1)

    print(f"[INFO] Auto-resolved deployment slug: {slug} (id={chosen.get('id')}, name={chosen.get('name')})")
    return slug


def get_all_projects(deployment_slug: str, api_token: str):
    """
    Step 1: Identify all projects for a deployment.
    """
    url = f"{BASE_URL}/deployments/{deployment_slug}/projects"
    headers = get_headers(api_token)

    resp = requests.get(url, headers=headers)
    if resp.status_code != 200:
        print(f"[ERROR] Failed to list projects ({resp.status_code}): {resp.text}", file=sys.stderr)
        sys.exit(1)

    data = resp.json()

    # Some APIs return a list directly; others wrap it in {"projects": [...]}
    if isinstance(data, list):
        projects = data
    elif isinstance(data, dict) and "projects" in data:
        projects = data["projects"]
    else:
        print("[ERROR] Unexpected response format when listing projects", file=sys.stderr)
        print(data)
        sys.exit(1)

    return projects


def get_project_details(deployment_slug: str, project_name: str, api_token: str):
    """
    Step 2 helper: Get details for a single project.

    Normalizes the response so callers get the project dict directly.
    Expected shape (from your example):
    {
      "project": {
        "id": ...,
        "name": "...",
        "managed_scan_config": { ... }
      }
    }
    """
    encoded_name = urllib.parse.quote(project_name, safe="")
    url = f"{BASE_URL}/deployments/{deployment_slug}/projects/{encoded_name}"
    headers = get_headers(api_token)

    resp = requests.get(url, headers=headers)
    if resp.status_code != 200:
        print(
            f"[WARN] Failed to get project '{project_name}' details "
            f"({resp.status_code}): {resp.text}",
            file=sys.stderr,
        )
        return None

    data = resp.json()
    # Unwrap {"project": {...}} if present
    if isinstance(data, dict) and "project" in data:
        return data["project"]
    return data


def project_has_sms_enabled(project_details: dict) -> bool:
    """
    Check if SMS is already fully enabled for this project.

    We discard projects with:
      "managed_scan_config": {
        "diff_scan": {"enabled": true},
        "full_scan": {"enabled": true}
      }
    """
    msc = project_details.get("managed_scan_config") or {}

    diff_scan = msc.get("diff_scan") or {}
    full_scan = msc.get("full_scan") or {}

    return bool(diff_scan.get("enabled") and full_scan.get("enabled"))


def enable_sms_for_project(
    deployment_slug: str, project_name: str, api_token: str, dry_run: bool = False
):
    """
    Step 3: Enable SMS (diff & full) for a single project using PATCH with JSON body:

    {
      "diff_scan": { "enabled": true },
      "full_scan": { "enabled": true }
    }
    """
    encoded_name = urllib.parse.quote(project_name, safe="")
    url = f"{BASE_URL}/deployments/{deployment_slug}/projects/{encoded_name}/managed-scan"

    headers = get_headers(api_token)
    headers["Content-Type"] = "application/json"

    payload = {
        "diff_scan": {"enabled": True},
        "full_scan": {"enabled": True},
    }

    if dry_run:
        print(f"[DRY-RUN] Would PATCH {url} with body={payload}")
        return

    resp = requests.patch(url, headers=headers, json=payload)
    if resp.status_code not in (200, 204):
        print(
            f"[ERROR] Failed to enable SMS for '{project_name}' "
            f"({resp.status_code}): {resp.text}",
            file=sys.stderr,
        )
    else:
        print(f"[OK] SMS enabled for '{project_name}'")


def main():
    parser = argparse.ArgumentParser(
        description=(
            "Enable Semgrep Managed Scans (SMS) for all projects in a deployment "
            "that don't already have SMS enabled."
        )
    )
    parser.add_argument(
        "--deployment-slug",
        required=False,
        help=(
            "Deployment slug (e.g., 'acme-corp'). "
            "If omitted, the script will auto-detect the first deployment from /deployments."
        ),
    )
    parser.add_argument(
        "--api-token",
        help="Semgrep API token. If not provided, SEMGREP_API_TOKEN env var will be used.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Do not send PATCH requests, only print what would be done.",
    )

    args = parser.parse_args()

    api_token = args.api_token or os.getenv("SEMGREP_API_TOKEN")
    if not api_token:
        print(
            "[ERROR] You must provide an API token via --api-token or SEMGREP_API_TOKEN env variable.",
            file=sys.stderr,
        )
        sys.exit(1)

    deployment_slug = resolve_deployment_slug(api_token, args.deployment_slug)

    print(f"[INFO] Listing projects for deployment '{deployment_slug}'...")
    projects = get_all_projects(deployment_slug, api_token)
    print(f"[INFO] Found {len(projects)} projects")

    to_enable = []

    # Step 2: discard projects already using SMS
    for p in projects:
        # Adjust key if your project objects use a different field (e.g., 'slug', 'project_name', etc.)
        project_name = p.get("name") or p.get("project_name") or p.get("slug")
        if not project_name:
            print(f"[WARN] Could not determine project name from object: {p}")
            continue

        details = get_project_details(deployment_slug, project_name, api_token)
        if not details:
            continue

        if project_has_sms_enabled(details):
            print(f"[SKIP] Project '{project_name}' already has SMS enabled")
        else:
            print(f"[TODO] Project '{project_name}' does NOT have SMS enabled")
            to_enable.append(project_name)

    print(f"[INFO] Projects to enable SMS on: {len(to_enable)}")

    # Step 3: enable SMS for remaining projects
    for project_name in to_enable:
        enable_sms_for_project(
            deployment_slug=deployment_slug,
            project_name=project_name,
            api_token=api_token,
            dry_run=args.dry_run,
        )


if __name__ == "__main__":
    main()
