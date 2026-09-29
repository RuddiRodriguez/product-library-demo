"""Small checks for the demo's important promises, using its real snapshot."""

import json
import shutil
import subprocess
import sys

from streamlit.testing.v1 import AppTest

from pipeline import DATA, merge_records, normalize, repository_key


def test_repeated_discovery_keeps_sources_and_first_seen():
    snapshot = json.loads((DATA / "raw.json").read_text())
    original = normalize(snapshot["records"][0], snapshot)
    updated = dict(original, description="Updated description", first_seen="later",
                   last_checked="later", source_urls=["https://example.org/discovery"])
    result = merge_records([original, updated])
    assert len(result) == 1
    assert result[0]["first_seen"] == original["first_seen"]
    assert result[0]["last_checked"] == "later"
    assert result[0]["description"] == "Updated description"
    assert set(result[0]["source_urls"]) == set(original["source_urls"] + updated["source_urls"])


def test_shared_repository_does_not_merge_different_servers():
    snapshot = json.loads((DATA / "raw.json").read_text())
    item = next(item for item in snapshot["records"] if item["source"] == "MCP Registry")
    first = normalize(item, snapshot)
    second = dict(first, id="mcp:another/server")
    assert len(merge_records([first, second])) == 2
    assert repository_key("https://github.com/Owner/Repo.git?ref=main") == "https://github.com/owner/repo"


def test_offline_rerun_is_identical(tmp_path):
    for name in ("raw.json", "library.json"):
        shutil.copy(DATA / name, tmp_path / name)
    command = [sys.executable, str(DATA.parent / "pipeline.py"), "--offline", "--output", str(tmp_path)]
    subprocess.run(command, check=True, capture_output=True)
    first = (tmp_path / "library.json").read_bytes()
    subprocess.run(command, check=True, capture_output=True)
    assert (tmp_path / "library.json").read_bytes() == first
    library = json.loads(first)
    assert len(library) == len({r["id"] for r in library})
    assert all(r["rights_status"] == "REVIEW REQUIRED" for r in library)


def test_app_search_and_source_filter():
    app = AppTest.from_file(str(DATA.parent / "app.py")).run(timeout=20)
    assert not app.exception
    app.selectbox[1].set_value("MCP Registry").run()
    assert not app.exception
    assert all("MCP Registry" in sources for sources in app.dataframe[0].value["sources"])
    app.text_input[0].set_value("no-matching-resource-xyz").run()
    assert not app.exception
    assert app.dataframe[0].value.empty
