"""Browse the saved sample without making API calls."""

import json

import streamlit as st

from pipeline import DATA


def main():
    st.set_page_config(page_title="Technology Library", page_icon="📚", layout="wide")
    library = json.loads((DATA / "library.json").read_text())
    summary = json.loads((DATA / "summary.json").read_text())
    st.title("Technology Library")
    st.write("Discover resources. Keep their sources. Review their licences.")
    st.caption(f"Real API snapshot · {summary['checked_at'][:10]} · Small Python demo")
    columns = st.columns(5)
    for column, label, key in zip(columns, ["Collected this run", "Unique this run", "Library entries", "Licence identified", "Needs review"],
                                   ["raw_this_run", "unique_this_run", "library_records", "license_identified", "review_required"]):
        column.metric(label, summary[key])
    st.info("Licence detection is evidence, not resale approval. Every entry needs rights review.")
    search = st.text_input("Search name or description", placeholder="Search tools, frameworks, integrations…")
    left, right = st.columns(2)
    category = left.selectbox("Category", ["All", "MCP server", "AI agent", "Linked repository"])
    source = right.selectbox("Source", ["All", "GitHub", "MCP Registry"])
    filtered = [r for r in library
                if search.lower() in f"{r['name']} {r['description']}".lower()
                and (category == "All" or category in r["categories"])
                and (source == "All" or source in r["sources"])]
    st.caption(f"{len(filtered)} entries · {summary['duplicates_this_run']} repeated discoveries merged · "
               f"{summary['groups_in_both_sources']} repository groups found in both sources")
    st.dataframe([{key: r[key] for key in ["name", "categories", "sources", "license", "stars", "rights_status"]}
                  for r in filtered], hide_index=True, use_container_width=True)
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
    st.download_button("Download full library CSV", (DATA / "library.csv").read_bytes(), "library.csv", "text/csv")
    st.download_button("Download full library JSON", (DATA / "library.json").read_bytes(), "library.json", "application/json")


if __name__ == "__main__":
    main()
