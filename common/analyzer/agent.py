import json
import os
from pathlib import Path

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


class UmlAnalyzerAgent:

    def __init__(self, mcp_command: str, mcp_args: list[str], model_path: str,
                 registry, a2a):

        self.mcp_command = mcp_command
        self.mcp_args = list(mcp_args)
        self.model_path = str(Path(model_path).resolve())
        self.registry = registry
        self.a2a = a2a

        if not Path(self.model_path).is_file():

            raise FileNotFoundError(f"Modèle UML introuvable : {self.model_path}")

    async def read_model(self, session: ClientSession) -> dict:

        """
            Lit d'abord le tool, puis la resource pivot complète.
        """
        await self._call_tool(session, "list_classes", {})

        model = await self._read_resource_json(session, "uml://model")

        if not isinstance(model, dict) or not isinstance(model.get("classes"), list):

            raise RuntimeError("Le serveur MCP a retourné un modèle UML invalide.")

        return model

    async def generate(self, language: str, out_dir: str) -> dict:

        params = StdioServerParameters(
            command=self.mcp_command,
            args=self.mcp_args,
            env={**os.environ, "PUML_FILE": self.model_path},
        )

        # Le contexte garantit la fermeture du processus MCP même si une étape échoue.
        async with stdio_client(params) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                model = await self.read_model(session)

        card = self.registry.find_by_language(language)

        task_id = self.a2a.send_message(
            card, {"model": model, "action": "generate"}
        )

        result = self.a2a.get_result(card, task_id)

        if result.get("status") != "completed":
            raise RuntimeError(
                f"Génération échouée : {result.get('error') or result}"
            )

        artifacts = result.get("artifacts")

        if not isinstance(artifacts, list):

            raise RuntimeError("L'agent générateur n'a pas retourné une liste d'artifacts.")

        files = self._write_artifacts(artifacts, out_dir)

        return {
            "language": language, "generator": card.name,
            "task_id": task_id, "out_dir": str(Path(out_dir).resolve()),
            "files": files,
        }

    @staticmethod
    async def _call_tool(session, tool: str, arguments: dict):

        result = await session.call_tool(tool, arguments or {})

        if getattr(result, "isError", False):

            raise RuntimeError(f"Le tool MCP {tool} a signalé une erreur.")

        for item in result.content:

            content = getattr(item, "text", None)

            if content is not None:
                try:
                    return json.loads(content)
                except ValueError:
                    return content

        raise RuntimeError(f"Réponse MCP illisible pour le tool {tool}")

    @staticmethod
    async def _read_resource_json(session, uri: str):

        result = await session.read_resource(uri)

        contents = getattr(result, "contents", None) or [result]

        if not contents or not getattr(contents[0], "text", None):

            raise RuntimeError(f"Resource MCP vide ou illisible : {uri}")
        try:
            return json.loads(contents[0].text)
        except ValueError as exc:

            raise RuntimeError(f"JSON invalide dans la resource MCP {uri}") from exc

    @staticmethod
    def _write_artifacts(artifacts: list[dict], out_dir: str) -> list[str]:

        """
            Écrit uniquement des noms de fichiers simples, sans effacer l'existant.
        """
        output = Path(out_dir).resolve()

        output.mkdir(parents=True, exist_ok=True)

        written = []

        for artifact in artifacts:

            if not isinstance(artifact, dict):

                raise ValueError("Artifact invalide : un objet était attendu.")

            filename = artifact.get("fileName")

            content = artifact.get("content")

            # Refuse les chemins absolus, ../ et les sous-dossiers fournis par l'agent.
            if (not isinstance(filename, str) or not filename
                    or Path(filename).name != filename
                    or filename in (".", "..")):

                raise ValueError(f"Nom de fichier d'artifact non autorisé : {filename!r}")

            if not isinstance(content, str):

                raise ValueError(f"Contenu invalide pour l'artifact {filename}")

            destination = output / filename

            destination.write_text(content, encoding="utf-8")

            written.append(str(destination))
            
        return written