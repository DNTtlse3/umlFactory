"""Base commune des agents générateurs (côté serveur A2A).

Ajouter un langage = sous-classer CodeGeneratorAgentBase + un LanguageProfile
+ un gabarit. Cette classe ne doit JAMAIS être modifiée pour un nouveau
langage (principe ouvert/fermé).
"""
import threading
import traceback
import uuid
from abc import ABC, abstractmethod
from pathlib import Path

import uvicorn
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from jinja2 import Environment, FileSystemLoader

from common.model.uml_model import UmlModel, UmlClass, is_multiple

REL_KIND_LABEL = {
    "association_dir": "association directionnelle",
    "association": "association bidirectionnelle",
    "aggregation": "agrégation",
    "composition": "composition",
}


class LanguageProfile(ABC):

    """
        Ce qui est spécifique à un langage cible.
    """

    file_extension: str = "txt"
    type_map: dict = {}

    def to_type(self, uml_type: str) -> str:
        return self.type_map.get(uml_type, uml_type)

    @abstractmethod
    def to_file_name(self, class_name: str) -> str: ...

    def collection_type(self, element_type: str) -> str:

        """
            Type rendu pour une cardinalité multiple.
        """
        return f"list[{element_type}]"


class CodeGeneratorAgentBase(ABC):
    target_language: str
    template_dir: Path
    profile: LanguageProfile

    def __init__(self, port: int, host: str = "127.0.0.1"):
        self.host = host
        self.port = port
        self.url = f"http://{host}:{port}"
        self.tasks: dict[str, dict] = {}

        self.env = Environment(
            loader=FileSystemLoader(str(self.template_dir), encoding="utf-8"),
            autoescape=False, keep_trailing_newline=True)

    # ---------- Agent Card ----------
    def build_card(self) -> dict:
        return {
            "name": f"{self.target_language}-codegen",
            "description": (f"Génère du code {self.target_language} à partir "
                            "d'un modèle UML (pivot JSON)."),
            "url": self.url,
            "skills": [{"id": f"{self.target_language}-gen",
                        "tags": ["code-generation",
                                 f"language:{self.target_language}"]}],
            "capabilities": {"artifacts": True},
        }

    # ---------- génération déterministe ----------
    def generate(self, payload: dict) -> list[dict]:

        model = UmlModel.from_dict(payload["model"])

        return [{"fileName": self.profile.to_file_name(cls.name),
                 "content": self.render(cls, model)}
                for cls in model.classes]

    def render(self, cls: UmlClass, model: UmlModel) -> str:

        template = self.env.get_template(
            f"class.{self.profile.file_extension}.j2")

        return template.render(**self.build_context(cls, model))

    def build_context(self, cls: UmlClass, model: UmlModel) -> dict:

        # relations dont la classe est la source -> attributs
        rel_attrs = []

        for rel in model.relations:

            if rel.source != cls.name:
                continue

            comment = f"{REL_KIND_LABEL[rel.kind]} avec {rel.target}"

            if rel.target_role and rel.target_role != rel.target:

                comment += f" (rôle '{rel.target_role}')"

            if rel.label:

                comment += f" ('{rel.label}')"

            rel_attrs.append({
                "name": (rel.target_role or rel.target).lower(),
                "type": rel.target,
                "collection": self.profile.collection_type(rel.target),
                "is_list": is_multiple(rel.target_card),
                "comment": comment,
            })

        attrs = [{"name": a.name, "type": a.type, "visibility": a.visibility,
                  "mapped_type": self.profile.to_type(a.type)}
                 for a in cls.attributes]

        ops = [self._op_dict(op) for op in cls.operations]

        # méthodes des interfaces implémentées (à surcharger)
        iface_ops = []
        if cls.kind != "interface":
            for iface_name in model.implementations.get(cls.name, []):

                iface = model.get_class(iface_name)

                if iface:
                    for op in iface.operations:
                        d = self._op_dict(op)
                        d["iface"] = iface_name
                        iface_ops.append(d)

        return {"name": cls.name, "kind": cls.kind, "comments": cls.comments,
                "attrs": attrs, "ops": ops, "rel_attrs": rel_attrs,
                "extends": model.inheritance.get(cls.name),
                "implements": model.implementations.get(cls.name, []),
                "iface_ops": iface_ops}

    def _op_dict(self, op) -> dict:

        return {"name": op.name, "visibility": op.visibility or "public",
                "return_type": self.profile.to_type(op.return_type),
                "params": [{"name": p.name, "type": self.profile.to_type(p.type)}
                           for p in op.parsed_parameters()]}

    # ---------- serveur A2A ----------
    def serve(self) -> None:

        app = self._build_app()

        print(f"[{self.target_language}] Agent Card : "
              f"{self.url}/.well-known/agent-card.json")

        uvicorn.run(app, host=self.host, port=self.port)

    def _build_app(self) -> FastAPI:

        app = FastAPI(title=f"generator-{self.target_language}")
        agent = self

        @app.get("/.well-known/agent-card.json")
        def agent_card() -> dict:
            return agent.build_card()

        @app.get("/health")
        def health() -> dict:
            return {"status": "ok", "language": agent.target_language}

        @app.post("/a2a")
        async def a2a(request: Request):

            body = await request.json()

            method = body.get("method")

            params = body.get("params", {})

            req_id = body.get("id")

            if method == "message/send":           # délégation -> tâche asynchrone

                task_id = uuid.uuid4().hex

                agent.tasks[task_id] = {"status": "working", "artifacts": []}

                threading.Thread(target=agent._run_task,
                                 args=(task_id, params), daemon=True).start()

                result = {"task_id": task_id, "status": "submitted"}

            elif method == "tasks/get":            # résultat retardé

                task = agent.tasks.get(params.get("task_id"))

                result = {"status": "unknown"} if task is None else {
                    "status": task["status"],
                    "artifacts": task["artifacts"],
                    "error": task.get("error")}
            else:

                return JSONResponse(
                    {"jsonrpc": "2.0", "id": req_id,
                     "error": {"code": -32601,
                               "message": f"méthode inconnue : {method}"}},
                    status_code=400)

            return {"jsonrpc": "2.0", "id": req_id, "result": result}

        return app

    def _run_task(self, task_id: str, params: dict) -> None:

        try:
            self.tasks[task_id]["artifacts"] = self.generate(params)

            self.tasks[task_id]["status"] = "completed"

        except Exception as exc:                    # noqa: BLE001

            traceback.print_exc()                   # traceback complet côté générateur

            self.tasks[task_id]["status"] = "failed"
            
            self.tasks[task_id]["error"] = f"{type(exc).__name__}: {exc}"