"""Discover a small technology library from GitHub and the MCP Registry."""

import argparse
import csv
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import quote, urlsplit

import requests


DATA = Path(__file__).parent / "data"
GITHUB = "https://api.github.com"
REGISTRY = "https://registry.modelcontextprotocol.io/v0.1/servers"
QUERIES = {
    "MCP server": "topic:mcp-server archived:false",
    "AI agent": "topic:ai-agents archived:false",
}


def get_data(url, params=None, allow_missing=False):
    """Read an API response. Only optional repository/file lookups allow 404."""
    headers = {"User-Agent": "product-library-demo"}
    # Keep the GitHub token away from requests to other sources.
    if urlsplit(url).hostname == "api.github.com" and os.getenv("GITHUB_TOKEN"):
        headers["Authorization"] = f"Bearer {os.environ['GITHUB_TOKEN']}"
    response = requests.get(url, params=params, headers=headers, timeout=30)
    if allow_missing and response.status_code == 404:
        return None, response.url
    response.raise_for_status()
    return response.json(), response.url


def repository_key(url):
    """Normalize GitHub links; preserve paths for other repository hosts."""
    if not url:
        return ""
    parts = urlsplit(url)
    path = parts.path.rstrip("/").removesuffix(".git")
    if parts.hostname == "github.com":
        path = "/".join(path.split("/")[:3]).lower()
    return f"https://{parts.netloc.lower()}{path}"


def discover(count):
    """Collect the two sources, then follow a few repository and licence links."""
    records = []
    checked_at = datetime.now(timezone.utc).isoformat()
    # Search each topic separately so an entry can keep both categories.
    for category, query in QUERIES.items():
        data, url = get_data(f"{GITHUB}/search/repositories", {
            "q": query, "sort": "stars", "per_page": count,
        })
        if data["incomplete_results"]:
            raise RuntimeError("GitHub returned incomplete search results. Run again later.")
        records.extend({"source": "GitHub", "source_url": url,
                        "category": category, "data": item} for item in data["items"])
        print(f"GitHub / {category}: {len(data['items'])}")

    # Follow registry pages until we reach the requested sample size.
    params = {"limit": count, "version": "latest"}
    servers = []
    while len(servers) < count:
        data, url = get_data(REGISTRY, params)
        servers.extend({"source": "MCP Registry", "source_url": url,
                        "category": "MCP server", "data": item}
                       for item in data["servers"][:count - len(servers)])
        cursor = data.get("metadata", {}).get("nextCursor")
        if not cursor:
            break
        params["cursor"] = cursor
        params["limit"] = count - len(servers)
    records.extend(servers)
    print(f"MCP Registry: {len(servers)}")

    # Keep distinct GitHub links in discovery order, then look up the first five.
    repository_urls = (
        repository_key(item["data"]["server"].get("repository", {}).get("url", ""))
        for item in servers
    )
    linked_repos = dict.fromkeys(url for url in repository_urls if url.startswith("https://github.com/"))
    skipped = []
    for repo in list(linked_repos)[:5]:
        name = urlsplit(repo).path.strip("/")
        data, url = get_data(f"{GITHUB}/repos/{name}", allow_missing=True)
        if data is None:
            skipped.append(repo)
            continue
        records.append({"source": "GitHub", "source_url": url,
                        "category": "Linked repository", "data": data})

    # Ten direct licence-file checks keep the live demo small.
    repositories = list(dict.fromkeys(
        item["data"]["full_name"] for item in records if item["source"] == "GitHub"
    ))[:10]
    licenses = {}
    for name in repositories:
        data, _ = get_data(f"{GITHUB}/repos/{name}/license", allow_missing=True)
        licenses[repository_key(f"https://github.com/{name}")] = data
    return {"checked_at": checked_at, "records": records, "licenses": licenses,
            "unavailable_repository_links": skipped}


def normalize(item, snapshot):
    """Give both sources the same field names without inventing missing details."""
    data = item["data"]
    if item["source"] == "GitHub":
        repo = repository_key(data["html_url"])
        record = {
            "id": f"github:{data['id']}", "name": data["full_name"],
            "description": data.get("description") or "", "url": data["html_url"],
            "repository_url": repo, "creator": data["owner"]["login"],
            "license": (data.get("license") or {}).get("spdx_id") or "UNKNOWN",
            "license_evidence": data["url"], "license_evidence_type": "GitHub metadata",
            "stars": data["stargazers_count"], "updated_at": data["pushed_at"],
            "tags": data.get("topics", []), "language": data.get("language") or "",
        }
        license_file = snapshot["licenses"].get(repo)
        # A direct file is stronger evidence than the repository's licence label.
        if license_file:
            record["license"] = license_file["license"]["spdx_id"]
            record["license_evidence"] = license_file["html_url"]
            record["license_evidence_type"] = "GitHub licence file"
    else:
        # A registry entry stays separate from its linked GitHub repository.
        server = data["server"]
        metadata = data["_meta"]["io.modelcontextprotocol.registry/official"]
        repo = repository_key(server.get("repository", {}).get("url", ""))
        record = {
            "id": f"mcp:{server['name']}", "name": server.get("title") or server["name"],
            "description": server.get("description", ""),
            "url": f"{REGISTRY}/{quote(server['name'], safe='')}/versions/latest",
            "repository_url": repo, "creator": server["name"].split("/")[0],
            "license": "UNKNOWN", "license_evidence": "",
            "license_evidence_type": "Not checked", "stars": None,
            "updated_at": metadata["updatedAt"], "tags": [], "language": "",
        }
    # These tracking fields work the same way for both sources.
    # Finding a licence never approves commercial use or resale.
    record.update({
        "group_id": repo or record["id"], "categories": [item["category"]],
        "sources": [item["source"]], "source_urls": [item["source_url"]],
        "rights_status": "REVIEW REQUIRED", "first_seen": snapshot["checked_at"],
        "last_checked": snapshot["checked_at"],
    })
    return record


def merge_records(records):
    """Remove repeated identities, keeping every discovery source."""
    unique = {}
    for record in records:
        previous = unique.get(record["id"])
        if previous:
            # Update details, but retain the first discovery and all source links.
            record = record.copy()
            record["first_seen"] = previous["first_seen"]
            for field in ("categories", "sources", "source_urls"):
                record[field] = sorted(set(previous[field] + record[field]))
        unique[record["id"]] = record
    return list(unique.values())


def summarize(snapshot, current, library):
    """Count discoveries, related repositories and available licence evidence."""
    groups = {}
    for record in library:
        groups.setdefault(record["group_id"], set()).update(record["sources"])
    return {
        "checked_at": snapshot["checked_at"],
        "raw_this_run": len(snapshot["records"]),
        "unique_this_run": len(current),
        "duplicates_this_run": len(snapshot["records"]) - len(current),
        "library_records": len(library),
        "repository_or_standalone_groups": len(groups),
        "groups_in_both_sources": sum(len(sources) > 1 for sources in groups.values()),
        "license_identified": sum(r["license"] not in ("UNKNOWN", "NOASSERTION") for r in library),
        "license_files_found_this_run": sum(bool(value) for value in snapshot["licenses"].values()),
        "review_required": len(library),
        "manually_verified": 0,
    }


def load_json(path):
    return json.loads(path.read_text(encoding="utf-8"))


def save_json(path, data):
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--count", type=int, choices=range(1, 101), default=100,
                        metavar="1-100", help="Records per GitHub query and registry sample")
    parser.add_argument("--offline", action="store_true", help="Replay the saved raw snapshot")
    parser.add_argument("--output", type=Path, default=DATA)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)

    # Use the saved responses for offline runs; otherwise collect a fresh sample.
    raw_path = args.output / "raw.json"
    snapshot = load_json(raw_path) if args.offline else discover(args.count)
    current = merge_records([normalize(item, snapshot) for item in snapshot["records"]])

    # Merge into the existing library so repeated runs update rather than duplicate.
    library_path = args.output / "library.json"
    previous = load_json(library_path) if library_path.exists() else []
    library = merge_records(previous + current)
    summary = summarize(snapshot, current, library)
    save_json(raw_path, snapshot)
    save_json(library_path, library)
    save_json(args.output / "summary.json", summary)
    # CSV needs text cells, so join list fields such as tags and discovery URLs.
    with (args.output / "library.csv").open("w", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(file, fieldnames=list(library[0]), lineterminator="\n")
        writer.writeheader()
        writer.writerows({key: " | ".join(value) if isinstance(value, list) else value
                         for key, value in record.items()} for record in library)
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
