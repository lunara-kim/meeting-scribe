"""NotionPublisher: UTF-16 chunking / HTML → blocks 변환 / publish 호출 페이로드 테스트.

UTF-16 chunking은 commit 20ba05c의 회귀 방지용 골든 경로. Python 문자 수로 자르면
BMP 외 문자(예: 일부 이모지)에서 Notion 2000자 제한을 초과한다.
"""
from unittest.mock import MagicMock

import pytest

from publisher.notion import NotionPublisher


def _make_pub():
    return NotionPublisher({
        "parent_page_id": "parent",
        "template_page_id": "",
        "api_token": "direct-token",
    })


def test_env_var_substitution(monkeypatch):
    monkeypatch.setenv("NOTION_KEY", "resolved")
    pub = NotionPublisher({
        "parent_page_id": "p",
        "api_token": "${NOTION_KEY}",
    })
    assert pub.api_token == "resolved"


def test_split_utf16_under_limit():
    pub = _make_pub()
    chunks = pub._split_utf16("짧은 텍스트", limit=1900)
    assert chunks == ["짧은 텍스트"]


def test_split_utf16_splits_bmp_text():
    pub = _make_pub()
    text = "가" * 1000  # BMP 한글, 각 1 code unit → 1000 units
    chunks = pub._split_utf16(text, limit=400)
    assert all(len(c) <= 400 for c in chunks)
    assert "".join(chunks) == text
    assert len(chunks) >= 2


def test_split_utf16_counts_surrogate_pair_as_two_units():
    """BMP 밖 문자(예: 😀 U+1F600)는 UTF-16에서 surrogate pair (2 units)로 세어야 한다."""
    pub = _make_pub()
    emoji = "😀"  # ord > 0xFFFF → 2 units
    # limit=2면 emoji 한 글자당 딱 맞으므로 3개 이모지는 3개 청크
    chunks = pub._split_utf16(emoji * 3, limit=2)
    assert chunks == ["😀", "😀", "😀"]
    assert "".join(chunks) == emoji * 3


def test_split_utf16_mixed_content_roundtrip():
    pub = _make_pub()
    text = "회의록 시작 😀 중요 결정사항 🎉 끝"
    chunks = pub._split_utf16(text, limit=10)
    assert "".join(chunks) == text


def test_html_to_blocks_headings_and_paragraphs():
    pub = _make_pub()
    html = "<h1>제목</h1><p>본문 문단</p><h2>소제목</h2>"
    blocks = pub._html_to_blocks(html)
    types = [b["type"] for b in blocks]
    assert types == ["heading_1", "paragraph", "heading_2"]
    assert blocks[0]["heading_1"]["rich_text"][0]["text"]["content"] == "제목"
    assert blocks[1]["paragraph"]["rich_text"][0]["text"]["content"] == "본문 문단"


def test_html_to_blocks_skips_empty():
    pub = _make_pub()
    html = "<p></p><p>  </p><p>실제 내용</p>"
    blocks = pub._html_to_blocks(html)
    assert len(blocks) == 1
    assert blocks[0]["paragraph"]["rich_text"][0]["text"]["content"] == "실제 내용"


def test_html_to_blocks_long_paragraph_is_chunked():
    pub = _make_pub()
    long_text = "가" * 2500  # 2000 limit 초과
    html = f"<p>{long_text}</p>"
    blocks = pub._html_to_blocks(html)
    assert len(blocks) >= 2
    assert all(b["type"] == "paragraph" for b in blocks)
    combined = "".join(
        b["paragraph"]["rich_text"][0]["text"]["content"] for b in blocks
    )
    assert combined == long_text


def test_publish_posts_expected_payload(monkeypatch):
    pub = _make_pub()
    fake_resp = MagicMock(ok=True)
    fake_resp.json.return_value = {"url": "https://notion.so/new-page"}
    post_mock = MagicMock(return_value=fake_resp)

    import publisher.notion as mod
    monkeypatch.setattr(mod.requests, "post", post_mock)

    url = pub.publish("회의록 - 2026-04-14", "<p>본문</p>")

    assert url == "https://notion.so/new-page"
    call_args = post_mock.call_args
    assert call_args.args[0] == "https://api.notion.com/v1/pages"
    payload = call_args.kwargs["json"]
    assert payload["parent"] == {"page_id": "parent"}
    assert payload["properties"]["title"]["title"][0]["text"]["content"] == "회의록 - 2026-04-14"
    assert len(payload["children"]) == 1
    assert payload["children"][0]["type"] == "paragraph"


def test_get_template_empty_when_no_template_id():
    pub = _make_pub()  # template_page_id=""
    assert pub.get_template() == ""
