from __future__ import annotations

import logging
from typing import Optional

import requests
from requests import Session

from Field import Field
from data_structures import Direction, ItemKind

logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

class SnakeFieldAPI:
    def __init__(
        self,
        base_url: str,
        teamname: str,
        game_name: str,
        password: str,
        *,
        timeout: float = 0.5,
        session: Optional[Session] = None,
    ) -> None:
        self.team_name = teamname
        self.game_name = game_name
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.session = session or requests.Session()
        self.session.auth = (teamname, password)
        self.session.headers.update({"Accept": "application/json", "Content-Type": "application/json"})

    def _url(self, path: str) -> str:
        return f"{self.base_url}{path}"

    def get_field(self) -> Field:
        url = self._url(f"/games/{self.game_name}/state")
        resp = self.session.get(url, timeout=self.timeout)
        data = resp.json()
        return Field.from_dict(data)

    def set_direction(self, direction: Direction) -> None:
        url = self._url(f"/games/{self.game_name}/snake/direction")
        payload = {"direction": direction}
        self.session.post(url, json=payload, timeout=self.timeout)

    def activate_item(self, item: ItemKind) -> None:
        url = self._url(f"/games/{self.game_name}/snake/activate")
        payload = {"item": item}
        self.session.post(url, json=payload, timeout=self.timeout)
