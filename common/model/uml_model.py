"""Pivot neutre : résultat du parsing PlantUML et format d'échange A2A."""
from dataclasses import dataclass, field


def is_multiple(cardinality: str) -> bool:
    """True si la cardinalité implique une collection (0..*, *, 1..*, ...)."""
    return cardinality not in ("1", "1..1", "0..1")


@dataclass
class Attribute:
    name: str
    type: str
    visibility: str = "private"

    def to_dict(self) -> dict:
        return {"name": self.name, "type": self.type,
                "visibility": self.visibility}

    @classmethod
    def from_dict(cls, d: dict) -> "Attribute":
        return cls(d["name"], d["type"], d.get("visibility", "private"))


@dataclass
class Operation:
    name: str
    parameters: str = ""          # texte brut, ex. "montant: Float"
    return_type: str = "void"
    visibility: str = "public"

    def parsed_parameters(self) -> list[Attribute]:
        """Vue structurée des paramètres (utile aux générateurs)."""
        if not self.parameters:
            return []
        out = []
        for part in self.parameters.split(","):
            if ":" in part:
                name, typ = part.split(":", 1)
                out.append(Attribute(name.strip(), typ.strip()))
            else:
                out.append(Attribute(part.strip(), ""))
        return out

    def to_dict(self) -> dict:
        return {"name": self.name, "parameters": self.parameters,
                "return_type": self.return_type, "visibility": self.visibility}

    @classmethod
    def from_dict(cls, d: dict) -> "Operation":
        return cls(d["name"], d.get("parameters", ""),
                   d.get("return_type", "void"), d.get("visibility", "public"))


@dataclass
class UmlClass:
    name: str
    kind: str = "class"            # "class" | "abstract" | "interface"
    attributes: list[Attribute] = field(default_factory=list)
    operations: list[Operation] = field(default_factory=list)
    comments: list[str] = field(default_factory=list)   # inline + notes

    def to_dict(self) -> dict:
        return {"name": self.name, "kind": self.kind,
                "attributes": [a.to_dict() for a in self.attributes],
                "operations": [o.to_dict() for o in self.operations],
                "comments": list(self.comments)}

    @classmethod
    def from_dict(cls, d: dict) -> "UmlClass":
        return cls(d["name"], d.get("kind", "class"),
                   [Attribute.from_dict(a) for a in d.get("attributes", [])],
                   [Operation.from_dict(o) for o in d.get("operations", [])],
                   list(d.get("comments", [])))


@dataclass
class UmlRelation:
    source: str
    target: str
    kind: str = "association"   # association_dir | association | aggregation | composition
    source_card: str = "1"
    target_card: str = "1"
    source_role: str | None = None
    target_role: str | None = None
    label: str = ""

    def to_dict(self) -> dict:
        return {"source": self.source, "target": self.target, "kind": self.kind,
                "source_card": self.source_card, "target_card": self.target_card,
                "source_role": self.source_role, "target_role": self.target_role,
                "label": self.label}

    @classmethod
    def from_dict(cls, d: dict) -> "UmlRelation":
        return cls(d["source"], d["target"], d.get("kind", "association"),
                   d.get("source_card", "1"), d.get("target_card", "1"),
                   d.get("source_role"), d.get("target_role"), d.get("label", ""))


@dataclass
class UmlModel:
    classes: list[UmlClass] = field(default_factory=list)
    relations: list[UmlRelation] = field(default_factory=list)
    inheritance: dict[str, str] = field(default_factory=dict)            # enfant -> parent
    implementations: dict[str, list[str]] = field(default_factory=dict) # classe -> interfaces

    def get_class(self, name: str) -> UmlClass | None:
        return next((c for c in self.classes if c.name == name), None)

    def relations_of(self, name: str) -> list[UmlRelation]:
        """Relations dans lesquelles la classe participe (source ou cible)."""
        return [r for r in self.relations
                if r.source == name or r.target == name]

    def to_dict(self) -> dict:
        return {"classes": [c.to_dict() for c in self.classes],
                "relations": [r.to_dict() for r in self.relations],
                "inheritance": dict(self.inheritance),
                "implementations": {k: list(v) for k, v in self.implementations.items()}}

    @classmethod
    def from_dict(cls, d: dict) -> "UmlModel":
        return cls([UmlClass.from_dict(c) for c in d.get("classes", [])],
                   [UmlRelation.from_dict(r) for r in d.get("relations", [])],
                   dict(d.get("inheritance", {})),
                   {k: list(v) for k, v in d.get("implementations", {}).items()})