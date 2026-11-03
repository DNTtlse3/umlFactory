"""Orchestrateur générique umlFactoryCode.

Exemple :
    python main.py generate models/example.puml -l cpp -o out_cpp

Les générateurs à démarrer sont déclarés dans agents.json.
L'ajout d'un nouveau langage ne nécessite donc aucune modification de ce fichier.
"""
import argparse
import asyncio
import json
import os
import subprocess
import sys
import time
from pathlib import Path

import httpx

from common.a2a.client import A2aClient
from common.a2a.registry import AgentCardRegistry
from common.analyzer.agent import UmlAnalyzerAgent


PROJECT_ROOT = Path(__file__).resolve().parent
DEFAULT_AGENTS_FILE = PROJECT_ROOT / "agents.json"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="umlFactoryCode — orchestrateur MCP + A2A"
    )
    sub = parser.add_subparsers(dest="command", required=True)

    generate = sub.add_parser(
        "generate", help="Génère le code depuis un diagramme PlantUML"
    )
    generate.add_argument("model", help="Chemin du fichier .puml")
    generate.add_argument(
        "--language", "-l", required=True,
        help="Langage cible déclaré dans agents.json (ex. java, python, cpp)"
    )
    generate.add_argument(
        "--out", "-o", default="out",
        help="Dossier de sortie (défaut : out)"
    )
    generate.add_argument(
        "--agents", default=str(DEFAULT_AGENTS_FILE),
        help="Fichier de configuration des générateurs"
    )
    generate.add_argument(
        "--host", default="127.0.0.1",
        help="Adresse d'écoute des agents (défaut : 127.0.0.1)"
    )
    generate.add_argument(
        "--startup-timeout", type=float, default=20.0,
        help="Délai maximal d'attente du démarrage de chaque agent"
    )
    return parser


def load_agent_config(config_path: str) -> list[dict]:
    """Charge et valide les agents à démarrer depuis le fichier JSON."""
    path = Path(config_path)
    if not path.is_absolute():
        path = (PROJECT_ROOT / path).resolve()

    if not path.is_file():
        raise FileNotFoundError(f"Configuration des agents introuvable : {path}")

    with path.open(encoding="utf-8") as file:
        config = json.load(file)

    # Accepte soit une liste directe, soit {"agents": [...]}.
    agents = config.get("agents") if isinstance(config, dict) else config
    if not isinstance(agents, list) or not agents:
        raise ValueError("agents.json doit contenir une liste non vide d'agents.")

    enabled_agents = []
    used_ports = set()
    used_languages = set()

    for index, agent in enumerate(agents):
        if not isinstance(agent, dict):
            raise ValueError(f"Entrée agent n°{index + 1} invalide : objet attendu.")

        if agent.get("enabled", True) is False:
            continue

        module = agent.get("module")
        language = agent.get("language")
        port = agent.get("port")

        if not module or not isinstance(module, str):
            raise ValueError(f"Module Python manquant pour l'agent n°{index + 1}.")
        if not language or not isinstance(language, str):
            raise ValueError(f"Langage manquant pour l'agent n°{index + 1}.")
        if not isinstance(port, int) or not 1 <= port <= 65535:
            raise ValueError(f"Port invalide pour l'agent '{language}'.")

        language = language.strip().lower()
        if language in used_languages:
            raise ValueError(f"Langage déclaré plusieurs fois : {language}")
        if port in used_ports:
            raise ValueError(f"Le port {port} est attribué à plusieurs agents.")

        used_languages.add(language)
        used_ports.add(port)
        enabled_agents.append({
            **agent,
            "module": module,
            "language": language,
            "port": port,
        })

    if not enabled_agents:
        raise ValueError("Aucun générateur activé dans la configuration.")

    return enabled_agents


def start_agent(module: str, port: int, host: str) -> subprocess.Popen:
    """Démarre un agent générateur dans un sous-processus."""
    command = [
        sys.executable, "-m", module,
        "--host", host,
        "--port", str(port),
    ]
    return subprocess.Popen(
        command,
        cwd=PROJECT_ROOT,
        env=os.environ.copy(),
    )


def wait_for_agent(
    process: subprocess.Popen, url: str, timeout: float
) -> None:
    """Attend que le endpoint /health réponde ou signale l'échec du processus."""
    deadline = time.monotonic() + timeout
    last_error = "aucune réponse"

    while time.monotonic() < deadline:
        exit_code = process.poll()
        if exit_code is not None:
            raise RuntimeError(
                f"L'agent {url} s'est arrêté au démarrage (code {exit_code})."
            )

        try:
            response = httpx.get(f"{url}/health", timeout=1.5)
            response.raise_for_status()
            if response.json().get("status") == "ok":
                return
            last_error = f"réponse inattendue : {response.text[:200]}"
        except (httpx.HTTPError, ValueError) as exc:
            last_error = str(exc)

        time.sleep(0.25)

    raise TimeoutError(
        f"Agent indisponible sur {url} après {timeout}s : {last_error}"
    )


def stop_agents(processes: list[subprocess.Popen]) -> None:
    """Arrête proprement les agents et force l'arrêt si nécessaire."""
    for process in processes:
        if process.poll() is None:
            process.terminate()

    for process in processes:
        if process.poll() is None:
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=5)


def run_generation(args: argparse.Namespace) -> dict:
    """Démarre les agents configurés, puis délègue la génération via A2A."""
    model_path = Path(args.model)
    if not model_path.is_absolute():
        model_path = (PROJECT_ROOT / model_path).resolve()

    if not model_path.is_file():
        raise FileNotFoundError(f"Fichier UML introuvable : {model_path}")
    if model_path.suffix.lower() != ".puml":
        raise ValueError("Le fichier modèle doit avoir l'extension .puml.")
    if args.startup_timeout <= 0:
        raise ValueError("--startup-timeout doit être strictement positif.")

    agents_config = load_agent_config(args.agents)
    requested_language = args.language.strip().lower()

    configured_languages = {agent["language"] for agent in agents_config}
    if requested_language not in configured_languages:
        available = ", ".join(sorted(configured_languages))
        raise ValueError(
            f"Aucun agent '{requested_language}' n'est configuré. "
            f"Langages disponibles : {available}"
        )

    processes: list[subprocess.Popen] = []
    agent_urls = []

    try:
        # Démarrage générique : aucun nom de langage n'est codé ici.
        for agent in agents_config:
            module = agent["module"]
            port = agent["port"]
            url = f"http://{args.host}:{port}"

            print(
                f"[orchestrateur] Démarrage de {agent['language']} "
                f"({module}) sur {url}",
                flush=True,
            )
            process = start_agent(module, port, args.host)
            processes.append(process)
            wait_for_agent(process, url, args.startup_timeout)
            agent_urls.append(url)

            print(f"[orchestrateur] Agent disponible : {url}", flush=True)

        # Le registre récupère les Agent Cards des agents qui viennent de démarrer.
        registry = AgentCardRegistry(urls=agent_urls)

        analyzer = UmlAnalyzerAgent(
            mcp_command=sys.executable,
            mcp_args=["-m", "common.mcp_server.server"],
            model_path=str(model_path),
            registry=registry,
            a2a=A2aClient(),
        )

        return asyncio.run(
            analyzer.generate(requested_language, args.out)
        )
    finally:
        stop_agents(processes)


def main() -> None:
    args = build_parser().parse_args()
    report = run_generation(args)
    print(json.dumps(report, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
