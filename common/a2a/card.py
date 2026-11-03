from dataclasses import dataclass, field
from urllib.parse import urlparse

import httpx


@dataclass
class AgentCard:
    name: str
    url: str
    description: str = ""
    skills: list[dict] = field(default_factory=list)

    @classmethod
    def from_url(cls, url: str) -> "AgentCard":

        """
            Récupère et valide la carte publiée sur /.well-known/agent-card.json.
        """

        base = url.rstrip("/")

        parsed = urlparse(base)

        if parsed.scheme not in ("http", "https") or not parsed.netloc:
            raise ValueError(f"URL d'agent invalide : {url}")
        try:
            response = httpx.get(
                f"{base}/.well-known/agent-card.json", timeout=5.0
            )

            response.raise_for_status()
            data = response.json()

        except (httpx.HTTPError, ValueError) as exc:
            raise RuntimeError(f"Impossible de lire l'Agent Card {base}: {exc}") from exc

        if not isinstance(data, dict) or not isinstance(data.get("name"), str):
            raise ValueError(f"Agent Card invalide : champ 'name' absent ({base})")

        skills = data.get("skills", [])

        if not isinstance(skills, list):
            raise ValueError(f"Agent Card invalide : 'skills' doit être une liste ({base})")

        return cls(
            name=data["name"],
            url=base,
            description=data.get("description", ""),
            skills=skills,
        )

    def supports_language(self, language: str) -> bool:
        """
            Compare sans tenir compte de la casse.
        """
        expected = f"language:{language}".casefold()
        
        return any(
            expected in [str(tag).casefold() for tag in skill.get("tags", [])]
            for skill in self.skills
            if isinstance(skill, dict) and isinstance(skill.get("tags", []), list)
        )