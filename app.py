"""Browse the saved sample without making API calls."""

import streamlit as st

from pipeline import DATA, load_json


def main():
    st.set_page_config(page_title="Technology Library", page_icon="📚", layout="wide")
    # Read the saved sample; opening the screen makes no API requests.
    library = load_json(DATA / "library.json")
    summary = load_json(DATA / "summary.json")
    st.title("Technology Library")
    st.write("Discover resources. Keep their sources. Review their licences.")
    st.caption(f"Real API snapshot · {summary['checked_at'][:10]} · Small Python demo")
    # Keep each visible label beside the count it displays.
    metrics = {
        "Collected this run": "raw_this_run",
        "Unique this run": "unique_this_run",
        "Library entries": "library_records",
        "Licence identified": "license_identified",
        "Needs review": "review_required",
    }
    for column, (label, key) in zip(st.columns(len(metrics)), metrics.items()):
        column.metric(label, summary[key])
    st.info("Licence detection is evidence, not resale approval. Every entry needs rights review.")
    search = st.text_input("Search name or description", placeholder="Search tools, frameworks, integrations…")
    left, right = st.columns(2)
    category = left.selectbox("Category", ["All", "MCP server", "AI agent", "Linked repository"])
    source = right.selectbox("Source", ["All", "GitHub", "MCP Registry"])
    # Apply each filter separately so the selection is easy to follow.
    filtered = [r for r in library if search.lower() in f"{r['name']} {r['description']}".lower()]
    if category != "All":
        filtered = [r for r in filtered if category in r["categories"]]
    if source != "All":
        filtered = [r for r in filtered if source in r["sources"]]
    st.caption(f"{len(filtered)} entries · {summary['duplicates_this_run']} repeated discoveries merged · "
               f"{summary['groups_in_both_sources']} repository groups found in both sources")
    fields = ["name", "categories", "sources", "license", "stars", "rights_status"]
    rows = [{field: record[field] for field in fields} for record in filtered]
    st.dataframe(rows, hide_index=True, use_container_width=True)
    # Inspect one matching entry, including evidence and related resources.
    if filtered:
        selected = st.selectbox("Inspect an entry", range(len(filtered)), format_func=lambda i: filtered[i]["name"])
        record = filtered[selected]
        st.subheader(record["name"])
        st.write(record["description"])
        st.link_button("Open source entry", record["url"])
        if record["license_evidence"]:
            st.link_button(f"Licence evidence: {record['license_evidence_type']}", record["license_evidence"])
        related = [r["name"] for r in library if r["group_id"] == record["group_id"] and r["id"] != record["id"]]
        st.write("Other entries sharing this repository:", ", ".join(related) or "None in this sample")
        with st.expander("Full record and discovery sources"):
            st.json(record)
    # Downloads always contain the full library, regardless of screen filters.
    for extension, mime in [("csv", "text/csv"), ("json", "application/json")]:
        filename = f"library.{extension}"
        st.download_button(f"Download full library {extension.upper()}",
                           (DATA / filename).read_bytes(), filename, mime)


if __name__ == "__main__":
    main()
