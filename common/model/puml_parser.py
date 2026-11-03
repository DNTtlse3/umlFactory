"""Parseur PlantUML : .puml (diagramme de classes) -> UmlModel pivot."""
import re
from collections import defaultdict

from common.model.uml_model import UmlModel, UmlClass, UmlRelation, Attribute, Operation

# ===== Regex (celles de umlfactory2Java, corrigées et regroupées côté lecture) =====
CLASS_RE = re.compile(
    r'(?:(abstract)\s+)?(class|interface)\s+(\w+)'
    r'(?:\s+"([^"]*)")?'                  # commentaire inline optionnel
    r'(?:\s+implements\s+[\w\s,]+)?'      # ignoré ici : géré par IMPLEMENT_RE
    r'(?:\s*\{([^}]*)\})?',               # corps optionnel
    re.MULTILINE)

ATTRIBUTE_RE = re.compile(r'([+\-#~])\s*(\w+)\s*:\s*(\w+)')
METHOD_RE    = re.compile(r'([+\-#~])\s*(\w+)\s*\(([^)]*)\)(?:\s*:\s*(\w+))?')

INHERITANCE_RE = re.compile(r'(\w+)\s*<\|--\s*(\w+)')     # parent <|-- enfant
IMPLEMENT_RE   = re.compile(r'(\w+)\s*\.\.\|>\s*(\w+)')    # classe ..|> interface

RELATION_RE = re.compile(
    r'(\w+)\s*'
    r'(?:"(?:(.*?)\s+)?([^"]*)")?\s*'    # rôle source (opt) + cardinalité source
    r'(-->|--|o--|\*--)\s*'              # type de relation
    r'(?:"(?:(.*?)\s+)?([^"]*)")?\s*'    # rôle cible (opt) + cardinalité cible
    r'(\w+)'
    r'(?:\s*:\s*"?([^"]*)"?\s*)?'         # libellé
)

KIND_MAP = {"-->": "association_dir", "--": "association",
            "o--": "aggregation", "*--": "composition"}


class PlantUmlParser:

    """
        Convertit un diagramme de classes PlantUML (.puml) en UmlModel pivot.
    """

    INLINE_COMMENT_RE = re.compile(
        r'(?:abstract\s+)?(?:class|interface)\s+(\w+)\s*"([^"]*)"')

    NOTE_RE = re.compile(
        r'note\s+(?:left|right|top|bottom)\s+of\s+(\w+)\s*(.*?)\s*end\s+note',
        re.DOTALL | re.IGNORECASE)

    def parse_file(self, path: str) -> UmlModel:

        with open(path, encoding="utf-8") as f:

            content = f.read()

        model = UmlModel()

        comments = self._parse_comments(content)            # inline + notes

        for name, (kind, body) in self._parse_classes(content).items():

            attributes, operations = self._parse_members(body)

            model.classes.append(UmlClass(
                name=name, kind=kind,
                attributes=attributes, operations=operations,
                comments=comments.get(name, [])))

        model.inheritance = {child: parent for parent, child
                             in INHERITANCE_RE.findall(content)}

        model.implementations = self._parse_implementations(content)

        model.relations = self._parse_relations(content)
        
        return model

    # --- classes / interfaces ---
    def _parse_classes(self, content: str) -> dict[str, tuple[str, str]]:

        classes: dict[str, tuple[str, str]] = {}

        for abstract, type_, name, _comment, body in CLASS_RE.findall(content):

            kind = "interface" if type_ == "interface" \
                   else ("abstract" if abstract else "class")

            classes[name] = (kind, body or "")

        return classes

    # --- commentaires (inline après le nom + notes PlantUML) ---
    def _parse_comments(self, content: str) -> dict[str, list[str]]:
        comments: dict[str, list[str]] = defaultdict(list)

        for name, comment in self.INLINE_COMMENT_RE.findall(content):
            if comment:

                comments[name].append(comment.strip())

        for name, text in self.NOTE_RE.findall(content):

            note = " ".join(line.strip() for line in text.strip().splitlines()
                            if line.strip())
            if note:

                comments[name].append(note)

        return comments

    # --- attributs et méthodes du corps d'une classe ---
    def _parse_members(self, body: str) -> tuple[list[Attribute], list[Operation]]:

        attributes = [Attribute(name, typ, self._vis(vis))
                      for vis, name, typ in ATTRIBUTE_RE.findall(body)]

        operations = [Operation(name, params or "", ret or "void", self._vis(vis))
                      for vis, name, params, ret in METHOD_RE.findall(body)]

        return attributes, operations

    @staticmethod
    def _vis(symbol: str) -> str:
        return {"+": "public", "-": "private", "#": "protected"}.get(symbol, "public")

    # --- implémentations d'interfaces / relations ---
    def _parse_implementations(self, content: str) -> dict[str, list[str]]:

        impl: dict[str, list[str]] = defaultdict(list)

        for cls, iface in IMPLEMENT_RE.findall(content):

            impl[cls].append(iface)

        return dict(impl)

    def _parse_relations(self, content: str) -> list[UmlRelation]:
        relations: list[UmlRelation] = []

        for (src, src_role, src_card, rel_type,
             dst_role, dst_card, dst, label) in RELATION_RE.findall(content):

            base = dict(kind=KIND_MAP[rel_type],
                        source_role=src_role or None,
                        target_role=dst_role or None,
                        label=label.strip())

            relations.append(UmlRelation(
                source=src, target=dst,
                source_card=src_card or "1", target_card=dst_card or "1", **base))

            if rel_type in ("--", "o--", "*--"):    # bidirectionnelle : lien inverse
                relations.append(UmlRelation(
                    source=dst, target=src,
                    source_card=dst_card or "1", target_card=src_card or "1", **base))

        return relations