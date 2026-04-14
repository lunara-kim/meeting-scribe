import os
import base64
import requests


class ConfluencePublisher:
    def __init__(self, config: dict):
        self.base_url = config["base_url"].rstrip("/")
        self.space_key = config["space_key"]
        self.parent_page_id = config["parent_page_id"]

        email = config["user_email"]
        api_token = config.get("api_token", "")
        if api_token.startswith("${"):
            api_token = os.getenv(api_token[2:-1], "")
        self.auth_header = base64.b64encode(f"{email}:{api_token}".encode()).decode()

    def _headers(self):
        return {
            "Authorization": f"Basic {self.auth_header}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

    def get_template(self) -> str:
        """Confluence 양식은 현재 미지원 (추후 구현)."""
        return ""

    def publish(self, title: str, body_html: str) -> str:
        """Confluence에 새 페이지를 생성하고 URL을 반환한다."""
        url = f"{self.base_url}/rest/api/content"
        payload = {
            "type": "page",
            "title": title,
            "space": {"key": self.space_key},
            "ancestors": [{"id": self.parent_page_id}],
            "body": {
                "storage": {
                    "value": body_html,
                    "representation": "storage",
                }
            },
        }

        resp = requests.post(url, json=payload, headers=self._headers())
        resp.raise_for_status()

        data = resp.json()
        page_id = data["id"]
        return f"{self.base_url}/pages/{page_id}"
