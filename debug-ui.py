from pathlib import Path
import tempfile
from textwrap import dedent
from typing import assert_never, cast, overload

import networkx as nx
import pandas as pd
import streamlit as st
from streamlit.runtime.uploaded_file_manager import UploadedFile

# from streamlit.elements.lib.column_config_utils import ColumnConfigMappingInput
import streamlit.components.v1 as components

from scheminer.conflict_resolution import detect_parent_child_confusion
from scheminer.graph_filtering import clean_stuff
from scheminer.mining import (
    filter_relations,
    flip_relations,
    merge_partial_relations,
    search_partial_relations,
)
from scheminer.types import Cardinality, OneWayRelation, Relation
from pyvis.network import Network

st.set_page_config(layout="wide")

COLUMN_CONFIG = {
    "weight": st.column_config.ProgressColumn("strength", format="%0.2f"),
    "strength": st.column_config.ProgressColumn("strength", format="%0.2f"),
    "from_strength": st.column_config.ProgressColumn("from_strength", format="%0.2f"),
    "to_strength": st.column_config.ProgressColumn("to_strength", format="%0.2f"),
    "from_table": "Child table",
    "from_column": "Child column",
    "to_table": "Parent table",
    "to_column": "Parent column",
}


@st.cache_data
def load_csv_files(csv_files: list[UploadedFile]) -> dict[str, pd.DataFrame]:
    return {f.name.removesuffix(".csv"): pd.read_csv(f) for f in csv_files}


@st.cache_data
def _search_partial_relations(items: dict[str, pd.DataFrame]) -> list[OneWayRelation]:
    return search_partial_relations(items)


@st.cache_data
def _merge_partial_relations(partial_relations: list[OneWayRelation]) -> list[Relation]:
    return merge_partial_relations(partial_relations)


# @st.cache_data(hash_funcs={Network: repr})
def _pyvis_html(network: Network) -> str:
    with tempfile.NamedTemporaryFile("w+", suffix=".html") as tmp:
        network.save_graph(tmp.name)
        return tmp.read()


def resolve_child_confusion(relations: list[Relation]) -> list[Relation]:
    df = pd.DataFrame(detect_parent_child_confusion(relations))
    df.insert(0, "action", "✔️ Keep")
    action_df = st.data_editor(
        df,
        column_config=COLUMN_CONFIG
        | {
            "action": st.column_config.SelectboxColumn(
                "Action", options=["✔️ Keep", "🔄 Invert", "❌ Discard"]
            )
        },
    ).set_index(["from_table", "from_column", "to_table", "to_column"])

    # Not pretty, but it works :)
    new_relations = []
    for relation in relations:
        idx = (
            relation.from_table,
            relation.from_column,
            relation.to_table,
            relation.to_column,
        )
        if idx in action_df.index:
            if action_df.loc[idx, "action"] == "❌ Discard":
                continue
            elif action_df.loc[idx, "action"] == "🔄 Invert":
                relation = relation.flip_direction()
        new_relations.append(relation)

    return new_relations


def remove_small_subset_relations(relations: list[Relation]) -> list[Relation]:
    tolerance = st.number_input(
        "Lower bound threshold",
        value=0.2,
        min_value=0.0,
        max_value=1.0,
        step=0.01,
    )

    df = pd.DataFrame(relations)
    df = df[df["to_strength"] < tolerance]
    df.insert(0, "action", "❌ Discard")
    action_df = st.data_editor(
        df,
        column_config=COLUMN_CONFIG
        | {
            "action": st.column_config.SelectboxColumn(
                "Action", options=["✔️ Keep", "❌ Discard"]
            )
        },
    ).set_index(["from_table", "from_column", "to_table", "to_column"])

    # Not pretty, but it works :)
    new_relations = []
    for relation in relations:
        idx = (
            relation.from_table,
            relation.from_column,
            relation.to_table,
            relation.to_column,
        )
        if idx in action_df.index and action_df.loc[idx, "action"] == "❌ Discard":
            continue
        new_relations.append(relation)

    return new_relations


tables = {}
with st.sidebar:
    database_type = st.selectbox("Database type", ["CSV Folder"])
    if database_type == "CSV Folder":
        files = st.file_uploader(
            "CSV Files",
            accept_multiple_files=True,
            help="Upload a set of CSV files, where each CSV file represents a table of the same database.",
        )
        if files:
            tables = load_csv_files(files)

if not tables:
    st.info("Please upload a database")
    st.stop()


st.header("Automatic relationship detection")

partial_relations = _search_partial_relations(tables)

partial_ralations = pd.DataFrame.from_records(
    partial_relations, columns=partial_relations[0]._fields
).rename({"strength": "weight"}, axis=1)
partial_ralations["left_cardinality"] = partial_ralations["left_cardinality"].map(
    lambda x: x.name
)

with st.expander("Find partial relations"):
    """For every column, we 1) check if its values are also found in any
    other column and 2) if this is a one-to-x or many-to-x relationship."""
    st.dataframe(partial_ralations, column_config=COLUMN_CONFIG)


with st.expander("Merge partial relations"):
    """Merge unidirectional partial relations into twodirectional fully qualified relations.
    If a relationship is many-to-many, the strenght is set to the maximum strenght of the two
    partial relationships. Else, we take the strenght of the source (left) relationship.
    """
    full_relations = _merge_partial_relations(partial_relations)
    st.dataframe(full_relations, column_config=COLUMN_CONFIG)


with st.expander("Filter out weak relations"):
    st.write(
        dedent(
            """
            If a column has a relation to another column, this relation should hold for every value in
            that column. In a correctly set-up database, we should thus be able to filter out all
            relationships with a strength < 1. In practice, not all databases have correctly set-up
            constraints and we thus tolerate a margin.

            > "But what about optional relationships? Not every account necessarily has an order?"

            Yes, but in such a case, the order would have a full 100% relationship to the account.

            > "But what about a nullable foreign key to an object that may exist also without any direct
            reference from the current table/column?"

            We ignore nulls in the partial relationship search,
            so there would still be a 100% correlation.
            """
        )
    )
    filter_tolerance = st.number_input(
        "Filter tolerance",
        value=0.01,
        help="In perfect database, every relation would have strength of 100%. "
        "The world isn't perfect, but we tolerate that.",
    )
    filtered_relations = filter_relations(full_relations, tolerance=filter_tolerance)
    st.dataframe(filtered_relations, column_config=COLUMN_CONFIG)


with st.expander("Flip relationships"):
    """Flip directional relationships to point from the child to the parent."""

    flipped_relations = flip_relations(filtered_relations)
    st.dataframe(flipped_relations, column_config=COLUMN_CONFIG)


relations = flipped_relations

st.header("Manual intervention")


with st.expander("Parent-child confusion"):
    """Sometimes two columns both contain 100% of each other's values and we cannot automatically
    detect the correct parent-child direction. This can lead to errors further down the line.
    """
    relations = resolve_child_confusion(relations)

with st.expander("Filter out low-corrolation relations"):
    """Some columns may be spurious subsets of other columns. A catagorical [1, 2, 3] column, for
    example, can be a perfect subset of a numerical index. Such columns will have very little
    overlap the other way around, however, which we can filter for."""
    relations = remove_small_subset_relations(relations)

# Prepare for graph conversion
selected_relations = (
    pd.DataFrame.from_records(relations, columns=relations[0]._fields)
    .rename({"strength": "weight"}, axis=1)
    .sort_values(["to_column", "to_table", "from_column", "from_table"])
)
selected_relations.insert(0, "enabled", True)
# selected_relations["cardinality"]= = selected_relations["cardinality"].map(lambda x: x.name)
selected_relations = st.data_editor(selected_relations, column_config=COLUMN_CONFIG)
selected_relations = selected_relations[selected_relations["enabled"]]


# Convert to graph
G = nx.from_pandas_edgelist(
    selected_relations,
    "from_table",
    "to_table",
    edge_attr=True,
    edge_key="from_column",
    create_using=nx.MultiDiGraph(),
)


st.header("Database graph")


if st.checkbox(
    "Remove multiple parents",
    help="""
    If a node has multiple outgoing connections (parent columns), there's likely only one true parent.
    The other column is more likely a sibling.
    """,
    value=True,
):
    G = clean_stuff(G)


net = Network(
    directed=True,
    filter_menu=True,
    select_menu=True,
    cdn_resources="in_line",
    notebook=False,
    height="500px",
)
net.from_nx(G)


for node in net.nodes:
    node["value"] = G.in_degree(node["id"])

for edge in net.edges:
    edge["arrows"] = {"to": {"enabled": True, "type": "arrow"}}
    edge["value"] = edge["to_strength"] / 2
    edge["label"] = edge["from_column"]
    if edge["to_column"] != edge["from_column"]:
        edge["label"] += " -> " + edge["to_column"]

    if edge["cardinality"] == Cardinality.OneToOne:
        edge["color"] = "#000"
        # In one-to-one, there is no actual directionality
        # edge["arrows"] = {}
    elif edge["cardinality"] == Cardinality.ManyToMany:
        edge["color"] = "#AEE"
    elif edge["cardinality"] == Cardinality.ManyToOne:
        edge["color"] = "#AFA"
    elif edge["cardinality"] == Cardinality.OneToMany:
        # Red, as it shouldn't happen
        st.warning(
            """Spurious one-to-many relation found in graph. Should only
            contain many-to-one relations, as children point to their parents."""
        )
        edge["color"] = "#FAA"
        # In many-to-many, we can point arrows both ways
        # edge["arrows"] = {
        #     "to": {"enabled": True, "type": "arrow"},
        #     "from": {"enabled": True, "type": "arrow"},
        # }
    else:
        assert_never(edge["cardinality"])

    edge["title"] = dedent(
        f"""\
        From: {edge["from"]}
        Column: {edge["from_column"]}
        Strength: {edge["from_strength"]:.2f}

        To: {edge["to"]}
        Column: {edge["to_column"]}
        Strength: {edge["to_strength"]:.2f}

        Cardinality: {edge["cardinality"]}
        Strength: {edge["width"]}
        """
    )

graph_container = st.empty()

if st.checkbox(
    "Show visualization controls",
    help="Hint: Scroll down in the graph view with the cursor over the top toolbars",
):
    net.show_buttons()

# net.set_edge_smooth("dynamic")

net.toggle_stabilization(False)
net.barnes_hut(gravity=-5000)
# net.toggle_physics(False)

with graph_container:
    components.html(_pyvis_html(net), height=500 + 80 + 80, scrolling=True)


"""
## TODO:

* [ ] Add detection of multi-column keys
  * If any of the tables have multiple relations of the same type between different column pairs, do they form a multi-column row?
  * We can go back to the database and check, or allow users to select this.

"""
