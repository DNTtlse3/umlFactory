"""Registre A2A : découverte des Agent Cards des générateurs."""
import json
from pathlib import Path

from common.a2a.card import AgentCard


class NoGeneratorFoundError(Exception):
    def __init__(self, language: str):
        super().__init__(
            f"Aucun agent générateur ne gère le langage '{language}'"
        )


class AgentCardRegistry:
    def __init__(
        self,
        config_path: str = "agents.json",
        urls: list[str] | None = None,
    ):
        """Initialise le registre depuis une liste d'URLs ou un ancien JSON.

        `urls` est utilisé par main.py après le démarrage des agents.
        Sans `urls`, le format historique contenant une liste d'URLs reste accepté.
        """
        if urls is None:
            path = Path(config_path)
            with path.open(encoding="utf-8") as file:
                urls = json.load(file)

        self.cards = [AgentCard.from_url(url) for url in urls]

    def find_by_language(self, language: str) -> AgentCard:
        language = language.strip().lower()
        for card in self.cards:
            if card.supports_language(language):
                return card
        raise NoGeneratorFoundError(language)
