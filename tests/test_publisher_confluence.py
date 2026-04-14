"""ConfluencePublisher: 인증 헤더 / publish 페이로드 / template 미구현 확인."""
import base64
from unittest.mock import MagicMock

import pytest

from publisher.confluence import ConfluencePublisher


def _make_pub():
    return ConfluencePublisher({
        "base_url": "https://example.atlassian.net/wiki/",
        "space_key": "TF",
        "parent_page_id": "123",
        "user_email": "user@example.com",
        "api_token": "direct-token",
    })


def test_env_var_substitution(monkeypatch):
    monkeypatch.setenv("CONF_KEY", "resolved")
    pub = ConfluencePublisher({
        "base_url": "https://example.atlassian.net/wiki",
        "space_key": "TF",
        "parent_page_id": "1",
        "user_email": "u@e.com",
        "api_token": "${CONF_KEY}",
    })
    expected = base64.b64encode(b"u@e.com:resolved").decode()
    assert pub.auth_header == expected


def test_base_url_trailing_slash_stripped():
    pub = _make_pub()
    assert pub.base_url == "https://example.atlassian.net/wiki"


def test_get_template_returns_empty_string():
    # 미구현 상태의 계약 명시. 구현 시 이 테스트를 업데이트해야 한다.
    assert _make_pub().get_template() == ""


def test_publish_posts_storage_representation(monkeypatch):
    pub = _make_pub()
    fake_resp = MagicMock()
    fake_resp.json.return_value = {"id": "999"}
    post_mock = MagicMock(return_value=fake_resp)

    import publisher.confluence as mod
    monkeypatch.setattr(mod.requests, "post", post_mock)

    url = pub.publish("제목", "<p>본문</p>")

    assert url == "https://example.atlassian.net/wiki/pages/999"
    call_args = post_mock.call_args
    assert call_args.args[0] == "https://example.atlassian.net/wiki/rest/api/content"
    payload = call_args.kwargs["json"]
    assert payload["type"] == "page"
    assert payload["title"] == "제목"
    assert payload["space"] == {"key": "TF"}
    assert payload["ancestors"] == [{"id": "123"}]
    assert payload["body"]["storage"]["representation"] == "storage"
    assert payload["body"]["storage"]["value"] == "<p>본문</p>"
    headers = call_args.kwargs["headers"]
    assert headers["Authorization"].startswith("Basic ")
