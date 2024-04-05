from enum import Enum, StrEnum
from typing import NamedTuple


class PartialCardinality(StrEnum):
    NA = "NA"
    One = "One"
    Many = "Many"

    @classmethod
    def from_cardinality_factor(cls, cardinality_factor: float) -> "PartialCardinality":
        if cardinality_factor == 1:
            return cls.One
        elif cardinality_factor > 1:
            return cls.Many
        return cls.NA


class Cardinality(StrEnum):
    OneToOne = "OneToOne"
    OneToMany = "OneToMany"
    ManyToOne = "ManyToOne"
    ManyToMany = "ManyToMany"

    @classmethod
    def from_partials(
        cls, left: PartialCardinality, right: PartialCardinality
    ) -> "Cardinality | None":
        match left, right:
            case (PartialCardinality.One, PartialCardinality.One):
                return cls.OneToOne
            case (PartialCardinality.One, PartialCardinality.Many):
                return cls.OneToMany
            case (PartialCardinality.Many, PartialCardinality.One):
                return cls.ManyToOne
            case (PartialCardinality.Many, PartialCardinality.Many):
                return cls.ManyToMany
            case (_, _):
                return None

    @classmethod
    def flip(cls, cardinality: "Cardinality"):
        match cardinality:
            case Cardinality.OneToMany:
                return Cardinality.ManyToOne
            case Cardinality.ManyToOne:
                return Cardinality.OneToMany
            case _:
                return cardinality


class Relation(NamedTuple):
    from_table: str
    to_table: str
    from_column: str
    to_column: str
    cardinality: Cardinality
    strength: float
    # Nice for debugging
    from_strength: float
    to_strength: float
    # description: Optional[str] = None

    def flip_direction(self) -> "Relation":
        return self.__class__(
            from_table=self.to_table,
            from_column=self.to_column,
            to_table=self.from_table,
            to_column=self.from_column,
            strength=self.strength,
            to_strength=self.from_strength,
            from_strength=self.to_strength,
            cardinality=Cardinality.flip(self.cardinality),
        )


class OneWayRelation(NamedTuple):
    from_table: str
    from_column: str
    to_table: str
    to_column: str
    strength: float
    left_cardinality: PartialCardinality


class RelationIndicators(NamedTuple):
    strength: float
    cardinality: PartialCardinality
