from typing import Iterable

import networkx as nx



# def get_filtered_graph(G: nx.MultiDiGraph, start_node, start_column):
#     # Filter the nodes based on the node attribute and value
#     # In this case it is red color
#     def filter_edge(n1, n2):
#         return G[n1][n2].get("account_id", True)

#     prev_graph = G

#     for i in range(100):
#         cur_graph = nx.subgraph_view(G, filter_edge=filter_edge)
#         if cur_graph == prev_graph:
#             break
#         prev_graph = cur_graph

#     return prev_graph
#     # filtered_nodes = [x for x,y in G.nodes(data=True)
#     #                if y[ignore_attribute]!=ignore_val]

#     # Create the subgraph
#     H = G.subgraph(filtered_nodes)
#     return H


def get_ancestor_links(
    G, table: str, column: str, relevant_edges=set()
) -> set[tuple[str, str, str]]:
    """Get all ancestor columns for a specific column"""
    # print(f"{table=}, {column=}")
    # Copy the set
    relevant_edges = set(relevant_edges)
    edges: Iterable[tuple[str, str, str]] = G.out_edges(table, keys=True)
    for edge in edges:
        if edge in relevant_edges:
            continue

        from_col = G.get_edge_data(*edge)["from_column"]
        to_col = G.get_edge_data(*edge)["to_column"]
        if from_col == column:
            relevant_edges.add(edge)
            relevant_edges |= get_ancestor_links(
                G,
                edge[1],
                to_col,
                relevant_edges,
            )
    return relevant_edges


def show_edges(edges):
    all_edges = set(edges) | {(v, u, k) for (u, v, k) in edges}
    return lambda u, v, k: (u, v, k) in all_edges


def hide_edges(edges):
    all_edges = set(edges) | {(v, u, k) for (u, v, k) in edges}
    return lambda u, v, k: (u, v, k) not in all_edges


def get_minimum_edges(G, table, column):
    """Filter out edges from a table that don't point to the closest actual ancestor."""
    edges = get_ancestor_links(G, table, column)
    print(f"get_minimum_edges {table=} {column=}")
    # print(f"Ancestoral edges", edges)

    H = nx.subgraph_view(G, filter_edge=show_edges(edges))
    needed_edges = []
    for n1, n2, key in H.edges(keys=True):
        # Check if the nodes share an ancestor
        # Hide the edge we're evaluating (otherwise there's always an ancestor)
        loo_graph = nx.subgraph_view(
            H, filter_edge=hide_edges([(n1, n2, key)])
        ).reverse()
        # nx.draw(loo_graph, with_labels=True)
        lca = nx.lowest_common_ancestor(loo_graph, n1, n2)
        if lca is not None and lca != n1 and lca != n2:
            needed_edges.append((n1, n2, key))
        # if len(all_simple_paths(H, n1, n2)) > 1:

    # needed_edges = [
    #     (n1, n2, key)
    #     for (n1, n2, key) in H.edges(keys=True)
    #     # Check if the edge's nodes share an ancestor, when the edge itself is gone
    #     if nx.lowest_common_ancestor(
    #         # Hide the edge we're evaluating
    #         nx.subgraph_view(H, filter_edge=hide_edges([(n1, n2, key)])),
    #         n1,
    #         n2,
    #     )
    #     is not None
    # ]

    # nx.draw(H, with_labels=True)
    # def remove_siblings(n1, n2, key):
    #     H_prime = nx.subgraph_view(H, filter_edge=hide_edges([(n1, n2, key)]))
    #     return nx.lowest_common_ancestor(H_prime, n1, n2) is None

    # return list(nx.subgraph_view(H, filter_edge=remove_siblings).edges(keys=True))
    # list(H2.edges())
    return needed_edges


def clean_obsolete_links(G):
    H = G.copy()
    for table in G.nodes():
        for _, _, column in G.out_edges(table, keys=True):
            unneeded_edges = get_minimum_edges(H, table, column)
            print("Unneeded edges", unneeded_edges)
            for edge in unneeded_edges:
                H.remove_edge(*edge)
            # print(H.edges())
    return H


def get_incorrect_multiple_outgoing_edges(G: nx.MultiDiGraph, table, column):
    """Cleans a table's edges when there are multiple outgoing connections.

    When we have multiple outgoing edges, this means our data is a subset of multiple other subsets.
    This can happen when multiple tables use the same foreign key. However, at least one of these other
    subsets should again be a subset of the true "master" table.
    Sometimes, we also have multiple outgoing edges that don't connect further. This can happen for ID
    columns that just happen to be subsets of other columns. We thus also remove these fake "master"
    tables that only have one single path to them (when we have multiple tables).
    Note: this can also remove good parents when we have too many bad ones.
    Lastly, we know we can prune all connections that don't directly go to these master tables.
    """
    edges = get_ancestor_links(G, table, column)
    # edges = get_ancestor_links(G, "order", "account_id")
    H = nx.subgraph_view(G, filter_edge=show_edges(edges))  # .reverse()
    H = nx.subgraph_view(H, filter_node=nx.filters.hide_nodes(list(nx.isolates(H))))

    ultimate_ancestors = [n for n, d in H.out_degree() if d == 0]
    if len(ultimate_ancestors) > 1:
        ultimate_ancestors = [
            node for node in ultimate_ancestors if H.in_degree(node) > 1
        ]
    print(f"{ultimate_ancestors=}")

    actual_edges = [
        edge for node in ultimate_ancestors for edge in H.in_edges(node, keys=True)
    ]

    # J = nx.subgraph_view(H, filter_edge=show_edges(actual_edges))
    # nx.draw(J, with_labels=True)

    to_remove = H.edges(keys=True) - actual_edges
    return to_remove


def clean_stuff(G: nx.MultiDiGraph):
    H: nx.MultiDiGraph = G.copy()  # type: ignore
    for table in G.nodes():
        for _, _, column in G.out_edges(table, keys=True):
            to_remove = get_incorrect_multiple_outgoing_edges(H, table, column)
            H.remove_edges_from(to_remove)
    return H
