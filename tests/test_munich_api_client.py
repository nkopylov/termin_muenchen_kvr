# ABOUTME: Tests for MunichAPIClient's result-returning calls: status and API error codes reach callers.
# ABOUTME: HTTP is stubbed at requests.get/post with real requests.Response objects.

import json

import pytest
import requests

from src import munich_api_client
from src.munich_api_client import ApiResponse, MunichAPIClient


def response(status: int, body) -> requests.Response:
    r = requests.Response()
    r.status_code = status
    r._content = body if isinstance(body, bytes) else json.dumps(body).encode()
    r.url = "https://example.invalid/api"
    return r


@pytest.fixture
def http(monkeypatch):
    calls = []
    replies = []

    def fake(url, **kwargs):
        calls.append((url, kwargs))
        reply = replies.pop(0)
        if isinstance(reply, Exception):
            raise reply
        return reply

    monkeypatch.setattr(munich_api_client.requests, "get", fake)
    monkeypatch.setattr(munich_api_client.requests, "post", fake)
    return calls, replies


class TestGetResult:
    def test_success(self, http):
        calls, replies = http
        replies.append(response(200, {"availableDays": []}))

        result = MunichAPIClient().get_result("available-calendar/", {"a": 1})

        assert result == ApiResponse({"availableDays": []}, 200, ())
        assert result.ok
        url, kwargs = calls[0]
        assert url.endswith("/available-calendar/")
        assert kwargs["params"] == {"a": 1}

    def test_error_codes_from_400_body(self, http):
        _, replies = http
        replies.append(
            response(
                400, {"errors": [{"errorCode": "captchaInvalid"}, {"errorCode": "x"}]}
            )
        )

        result = MunichAPIClient().get_result("available-calendar/", {})

        assert result == ApiResponse(None, 400, ("captchaInvalid", "x"))
        assert not result.ok

    def test_top_level_error_code(self, http):
        _, replies = http
        replies.append(
            response(400, {"errorCode": "invalidLocationAndServiceCombination"})
        )
        result = MunichAPIClient().get_result("available-calendar/", {})
        assert result.error_codes == ("invalidLocationAndServiceCombination",)

    def test_error_code_in_200_body_is_an_error(self, http):
        _, replies = http
        replies.append(response(200, {"errorCode": "tooManyAppointmentsWithSameMail"}))
        result = MunichAPIClient().get_result("x/", {})
        assert result.data is None
        assert result.error_codes == ("tooManyAppointmentsWithSameMail",)

    def test_non_json_error_body(self, http):
        _, replies = http
        replies.append(response(502, b"<html>bad gateway</html>"))
        assert MunichAPIClient().get_result("x/", {}) == ApiResponse(None, 502, ())

    def test_network_error(self, http):
        _, replies = http
        replies.append(requests.ConnectionError("down"))
        assert MunichAPIClient().get_result("x/", {}) == ApiResponse(None, None, ())


class TestPostResult:
    def test_success_and_error(self, http):
        calls, replies = http
        replies.append(response(200, {"processId": 1}))
        replies.append(response(400, {"errors": [{"errorCode": "captchaExpired"}]}))
        client = MunichAPIClient()

        assert client.post_result("reserve-appointment/", {"t": 1}).data == {
            "processId": 1
        }
        assert calls[0][1]["json"] == {"t": 1}
        assert client.post_result("reserve-appointment/", {}).error_codes == (
            "captchaExpired",
        )


class TestGetAndPost:
    def test_get_returns_none_on_error(self, http):
        _, replies = http
        replies.append(response(400, {"errors": [{"errorCode": "captchaInvalid"}]}))
        assert MunichAPIClient().get("x/") is None

    def test_post_returns_json(self, http):
        _, replies = http
        replies.append(response(200, {"ok": True}))
        assert MunichAPIClient().post("x/", {}) == {"ok": True}
