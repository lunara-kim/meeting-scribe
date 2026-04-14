import os
import requests


class NotionPublisher:
    def __init__(self, config: dict):
        self.parent_page_id = config["parent_page_id"]
        self.template_page_id = config.get("template_page_id", "")
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

    def get_template(self) -> str:
        """양식 페이지 내용을 플레인 텍스트로 반환한다. 설정이 없으면 빈 문자열."""
        if not self.template_page_id:
            return ""

        resp = requests.get(
            f"https://api.notion.com/v1/blocks/{self.template_page_id}/children?page_size=100",
            headers=self._headers(),
        )
        resp.raise_for_status()

        lines = []
        for block in resp.json().get("results", []):
            btype = block.get("type")
            content = block.get(btype, {})
            rich_text = content.get("rich_text", [])
            text = "".join(rt.get("plain_text", "") for rt in rich_text)
            if not text.strip():
                continue

            if btype == "heading_1":
                lines.append(f"# {text}")
            elif btype == "heading_2":
                lines.append(f"## {text}")
            elif btype == "heading_3":
                lines.append(f"### {text}")
            elif btype == "bulleted_list_item":
                lines.append(f"- {text}")
            elif btype == "numbered_list_item":
                lines.append(f"1. {text}")
            else:
                lines.append(text)

        return "\n".join(lines)

    def publish(self, title: str, body_html: str) -> str:
        """Notion에 새 페이지를 생성하고 URL을 반환한다."""
        # HTML을 Notion 블록으로 변환 (paragraph 블록으로 처리)
        blocks = self._html_to_blocks(body_html)

        payload = {
            "parent": {"page_id": self.parent_page_id},
            "properties": {
                "title": {
                    "title": [{"type": "text", "text": {"content": title[:2000]}}]
                }
            },
            "children": blocks,
        }

        resp = requests.post(
            "https://api.notion.com/v1/pages",
            json=payload,
            headers=self._headers(),
        )
        if not resp.ok:
            print(f"[Notion] {resp.status_code} 응답 본문: {resp.text}")
            resp.raise_for_status()

        return resp.json()["url"]

    def _split_utf16(self, text: str, limit: int = 1900) -> list:
        """Notion의 2000자 제한(UTF-16 code unit 기준)에 맞춰 텍스트를 분할한다."""
        chunks = []
        buf = ""
        buf_units = 0
        for ch in text:
            # BMP 외 문자는 UTF-16 surrogate pair (2 units)
            units = 2 if ord(ch) > 0xFFFF else 1
            if buf_units + units > limit:
                chunks.append(buf)
                buf = ch
                buf_units = units
            else:
                buf += ch
                buf_units += units
        if buf:
            chunks.append(buf)
        return chunks

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
                # heading도 길면 잘라야 하므로 첫 청크만 사용하거나 뒷 청크는 paragraph로 추가
                heading_chunks = self._split_utf16(text)
                blocks.append({
                    "object": "block",
                    "type": block_type,
                    block_type: {
                        "rich_text": [{"type": "text", "text": {"content": heading_chunks[0]}}]
                    },
                })
                for extra in heading_chunks[1:]:
                    blocks.append({
                        "object": "block",
                        "type": "paragraph",
                        "paragraph": {
                            "rich_text": [{"type": "text", "text": {"content": extra}}]
                        },
                    })
            else:
                for chunk in self._split_utf16(text):
                    blocks.append({
                        "object": "block",
                        "type": "paragraph",
                        "paragraph": {
                            "rich_text": [{"type": "text", "text": {"content": chunk}}]
                        },
                    })

        return blocks
