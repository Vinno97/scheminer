from itertools import combinations, product

import networkx as nx
import pandas as pd
from pandas.api.types import is_numeric_dtype
from tqdm import tqdm

from scheminer.types import Cardinality, OneWayRelation, PartialCardinality, Relation


def detect_relation(
    col_a: pd.Series, col_b: pd.Series, ignore_nulls: bool = True
) -> tuple[float, PartialCardinality]:
    """Find unidirectional relationships between pandas series.

    Check how many of a's values are present in b.

    Note: this works, but should we maybe check how many of a's unique values are present in b?
    That might be a better indication of relation strength.
    """
    if ignore_nulls:
        col_a = col_a.dropna()
        col_b = col_b.dropna()

    a_in_b = col_a[col_a.isin(col_b)]
    unique_a_in_b = col_a[col_a.isin(col_b)].drop_duplicates()

    # Fraction of how many rows of a are in b
    relation_strength = len(a_in_b) / len(col_a)
    # relation_strength = len(unique_a_in_b) / len(col_a.drop_duplicates())

    # cardinality_factor=1: One-to-X mapping
    # cardinality_factor>1: Many-to-X mapping
    cardinality_factor = (
        len(a_in_b) / len(unique_a_in_b) if relation_strength > 0 else 0
    )
    partial_cardinality = PartialCardinality.from_cardinality_factor(cardinality_factor)

    return relation_strength, partial_cardinality

    # cardinality = len(a_in_b) / len(a_in_b.drop_duplicates())

    # return Relation(
    #     left_table=col_a.name,  # type: ignore
    #     right_table=col_a.name,  # type: ignore
    #     strength=relation_strength,
    #     left_cardinality=Cardinality.OneToMany,
    # )


def search_partial_relations(items: dict[str, pd.DataFrame]) -> list[OneWayRelation]:
    """Searches for unidirectional relations between columns in Pandas dataframes."""

    partial_relations = []

    # Get a list of all combinations of tables
    table_pairs = list(combinations(items.items(), 2))
    for (t1_name, t1_df), (t2_name, t2_df) in tqdm(
        table_pairs, desc="Iterating over table pairs"
    ):
        # Get a list of all combinations of columns
        column_pairs = list(product(t1_df.columns, t2_df.columns))
        for t1_col_name, t2_col_name in tqdm(
            column_pairs,
            f"Comparing tables for `{t1_name}` and `{t2_name}`",
            leave=False,
        ):
            t1_col = t1_df[t1_col_name]
            t2_col = t2_df[t2_col_name]

            # Early termination to speed up processing
            # We assume mixed dtypes (e.g. strings vs ints) can never corrolate
            # Should be replaced by a less naive solution
            if t1_col.dtype != t2_col.dtype and not (
                # Don't skip comparing int32 and int64, etc.
                is_numeric_dtype(t1_col)
                and is_numeric_dtype(t2_col)
            ):
                continue

            a_to_b_strength, a_to_b_cardinality = detect_relation(t1_col, t2_col)
            b_to_a_strength, b_to_a_cardinality = detect_relation(t2_col, t1_col)

            if a_to_b_strength > 0:
                # Check to see if we can indeed merge the if-statements
                assert b_to_a_strength > 0

                partial_relations.append(
                    OneWayRelation(
                        from_table=t1_name,
                        from_column=t1_col_name,
                        to_table=t2_name,
                        to_column=t2_col_name,
                        strength=a_to_b_strength,
                        left_cardinality=a_to_b_cardinality,
                    )
                )

            if b_to_a_strength > 0:
                partial_relations.append(
                    OneWayRelation(
                        from_table=t2_name,
                        from_column=t2_col_name,
                        to_table=t1_name,
                        to_column=t1_col_name,
                        strength=b_to_a_strength,
                        left_cardinality=b_to_a_cardinality,
                    )
                )
    return partial_relations


# def search_relations(
#     items: Dict[str, pd.DataFrame],
#     check_for_key: Callable[[str], bool] = spot_id,
#     metric: Metric = jaccard_metric
# ) -> list[Relation]:
#     # Dict[str, List[str]]:

#     """
#     tba, use type hints for now
#     """

#     relations = []

#     for t1_name, t1_df in items.items():
#         for t2_name, t2_df in items.items():
#             if t1_name != t2_name:
#                 common_col = set(t1_df.columns) & set(t2_df.columns)
#                 # print(common_col)

#                 if len(common_col) > 0:
#                     for col in common_col:
#                         warnings.warn("Add helper cardinality func here")
#                         # more rows == intermediate. Think about adding row count score for intermediate tables and childless

#                         # calculate jaccard index with a twist (intersection over union with a twist)
#                         # mask with cardinality normalization missing in this implementation

#                         # print("Tables: {} and {} using Key {} have score of {}".format(t1_n, t2_n, col, similarity))
#                         # if similarity > threshold:
#                         similarity = metric(t1_df[col], t2_df[col])

#                         if check_for_key(col):  # to avoid duplicates
#                             relationship = Relation(t1_name, t2_name, col, similarity)
#                             relations.append(relationship)
#     return relations
#     # schema = funcFormat(items, relations)
#     # return schema


# def filter_relations(relations: list[Relation], threshold: float) -> list[Relation]:
#     return [relation for relation in relations if relation.strength > threshold]


def merge_partial_relations(partial_relations: list[OneWayRelation]) -> list[Relation]:
    # Assume our original method always produced pairs
    pairs = zip(partial_relations[::2], partial_relations[1::2])

    relations = []
    for left, right in pairs:
        assert left.from_table == right.to_table
        assert left.to_table == right.from_table
        assert left.from_column == right.to_column
        assert left.to_column == right.from_column

        if left.strength > right.strength:
            from_, to = left, right
        else:
            from_, to = right, left

        cardinality = Cardinality.from_partials(
            from_.left_cardinality, to.left_cardinality
        )
        if cardinality == Cardinality.ManyToMany:
            strength = max(from_.strength, to.strength)
        else:
            strength = from_.strength

        relations.append(
            Relation(
                from_table=from_.from_table,
                from_column=from_.from_column,
                to_table=from_.to_table,
                to_column=from_.to_column,
                cardinality=cardinality,  # type: ignore
                strength=strength,
                from_strength=from_.strength,
                to_strength=to.strength,
            )
        )
    return relations


def filter_relations(relations: list[Relation], tolerance=0.01) -> list[Relation]:
    filtered = []
    for rel in relations:
        # Any foreign key, should have every key represented in the other column
        # if rel.strength < 1:
        #     continue
        # Though we do allow for some tolerance
        if rel.strength < 1 - tolerance:
            continue

        # Assuming a database is set up correctly, we won't have any direct many-to-many relations
        # if rel.cardinality == Cardinality.ManyToMany:
        #     continue

        # Of course every table will have a full match with itself
        if rel.from_table == rel.to_table and rel.from_column == rel.to_column:
            continue

        filtered.append(rel)
    return filtered


def flip_relations(relations: list[Relation]) -> list[Relation]:
    """Flip directional relationships to point from the child to the parent."""
    outp_relations = []

    for relation in relations:
        if relation.cardinality == Cardinality.OneToMany:
            relation = relation.flip_direction()
        outp_relations.append(relation)

    return outp_relations
