import time
import uuid

import httpx


class A2aClient:
    def __init__(self, poll_interval: float = 0.5, timeout: float = 120):

        if poll_interval <= 0 or timeout <= 0:

            raise ValueError("poll_interval et timeout doivent être positifs")

        self.poll_interval = poll_interval
        self.timeout = timeout

    def _rpc(self, url: str, method: str, params: dict) -> dict:

        """
            Envoie une requête JSON-RPC et valide sa réponse avant utilisation.
        """
        request_id = uuid.uuid4().hex
        try:
            response = httpx.post(
                f"{url.rstrip('/')}/a2a",
                json={"jsonrpc": "2.0", "id": request_id,
                      "method": method, "params": params},
                timeout=30,
            )

            response.raise_for_status()

            data = response.json()

        except (httpx.HTTPError, ValueError) as exc:
            raise RuntimeError(f"Échec de l'appel A2A {method} vers {url}: {exc}") from exc

        if not isinstance(data, dict):
            raise RuntimeError("Réponse A2A invalide : un objet JSON était attendu.")

        if data.get("error"):
            raise RuntimeError(f"Erreur A2A ({method}) : {data['error']}")

        if data.get("id") != request_id or "result" not in data:
            raise RuntimeError(f"Réponse JSON-RPC invalide pour {method}.")

        if not isinstance(data["result"], dict):
            raise RuntimeError(f"Résultat A2A invalide pour {method}.")

        return data["result"]

    def send_message(self, card, payload: dict) -> str:
        """
            Délègue une tâche et retourne son identifiant.
        """
        result = self._rpc(card.url, "message/send", payload)

        task_id = result.get("task_id")

        if not isinstance(task_id, str) or not task_id:
            raise RuntimeError(f"Réponse message/send sans task_id : {result}")

        return task_id

    def get_result(self, card, task_id: str) -> dict:

        """
            Interroge la tâche jusqu'à son état terminal ou jusqu'au timeout.
        """
        deadline = time.monotonic() + self.timeout

        while time.monotonic() < deadline:

            result = self._rpc(card.url, "tasks/get", {"task_id": task_id})

            status = result.get("status")

            if status in ("completed", "failed"):
                return result

            if status == "unknown":
                raise RuntimeError(f"Tâche A2A inconnue : {task_id}")

            time.sleep(min(self.poll_interval, max(0, deadline - time.monotonic())))
            
        raise TimeoutError(f"Tâche A2A {task_id} non terminée après {self.timeout}s")