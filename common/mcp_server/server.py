"""Serveur MCP : expose le modèle UML via des tools et des resources.

Lancement (depuis la racine du projet) :
    python -m common.mcp_server.server
Le fichier .puml lu est donné par la variable d'environnement PUML_FILE
(défaut : models/example.puml).
"""
import json
import os

from mcp.server.fastmcp import FastMCP

from common.model.puml_parser import PlantUmlParser
from common.model.uml_model import UmlModel

mcp = FastMCP("uml-model-server")
_model: UmlModel | None = None


def load_model() -> UmlModel:
    global _model
    if _model is None:
        path = os.environ.get("PUML_FILE", "models/model.puml")
        _model = PlantUmlParser().parse_file(path)
    return _model


@mcp.tool()
def list_classes() -> list[str]:    

    """
        Liste les noms des classes, interfaces et classes abstraites du modèle.
    """
    return [c.name for c in load_model().classes]


@mcp.tool()
def get_class_details(class_name: str) -> dict:

    """
        Détails d'une classe : genre, attributs, opérations, héritage,
        interfaces implémentées, relations et commentaires.
    """
    m = load_model()
    c = m.get_class(class_name)
    if c is None:
        return {"error": f"classe inconnue : {class_name}"}
    return {**c.to_dict(),
            "extends": m.inheritance.get(class_name),
            "implements": m.implementations.get(class_name, []),
            "relations": [r.to_dict() for r in m.relations_of(class_name)]}


@mcp.tool()
def list_relations() -> list[dict]:

    """
        Relations entre classes : type, cardinalités, rôles, libellés.
    """
    return [r.to_dict() for r in load_model().relations]


@mcp.resource("uml://model")
def model_resource() -> str:

    """
        Le modèle UML complet (pivot JSON issu du fichier .puml).
    """
    return json.dumps(load_model().to_dict(), indent=2)


@mcp.resource("uml://class/{name}")
def class_resource(name: str) -> str:

    """
        La description pivot d'une classe donnée.
    """
    c = load_model().get_class(name)
    if c is None:
        return json.dumps({"error": f"classe inconnue : {name}"})
    return json.dumps(c.to_dict(), indent=2)


if __name__ == "__main__":
    mcp.run()   # transport stdio