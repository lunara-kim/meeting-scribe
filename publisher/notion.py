import os
import requests


class NotionPublisher:
    def __init__(self, config: dict):
        self.parent_page_id = config["parent_page_id"]
        api_token = config.get("api_token", "")
        if api_token.startswith("${"):
            api_token = os.getenv(api_token[2:-1], "")
        self.api_token = api_token

    def _headers(self):
        return {
            "Authorization": f"Bearer {self.api_token}",
            "Content-Type": "application/json",
            "Notion-Version": "2022-06-28",
        }

    def publish(self, title: str, body_html: str) -> str:
        """Notion에 새 페이지를 생성하고 URL을 반환한다."""
        # HTML을 Notion 블록으로 변환 (paragraph 블록으로 처리)
        blocks = self._html_to_blocks(body_html)

        payload = {
            "parent": {"page_id": self.parent_page_id},
            "properties": {
                "title": [{"text": {"content": title}}]
            },
            "children": blocks,
        }

        resp = requests.post(
            "https://api.notion.com/v1/pages",
            json=payload,
            headers=self._headers(),
        )
        resp.raise_for_status()

        return resp.json()["url"]

    def _html_to_blocks(self, html: str) -> list:
        """HTML 문자열을 Notion 블록 리스트로 변환한다."""
        import re

        blocks = []
        # <h1>~<h3> → heading 블록, <p>/텍스트 → paragraph 블록
        parts = re.split(r"(<h[1-3][^>]*>.*?</h[1-3]>)", html, flags=re.DOTALL)

        for part in parts:
            text = re.sub(r"<[^>]+>", "", part).strip()
            if not text:
                continue

            h_match = re.match(r"<h([1-3])", part)
            if h_match:
                level = int(h_match.group(1))
                block_type = f"heading_{level}"
                blocks.append({
                    "object": "block",
                    "type": block_type,
                    block_type: {
                        "rich_text": [{"type": "text", "text": {"content": text}}]
                    },
                })
            else:
                # 긴 텍스트는 2000자 단위로 분할 (Notion API 제한)
                for i in range(0, len(text), 2000):
                    chunk = text[i:i + 2000]
                    blocks.append({
                        "object": "block",
                        "type": "paragraph",
                        "paragraph": {
                            "rich_text": [{"type": "text", "text": {"content": chunk}}]
                        },
                    })

        return blocks
