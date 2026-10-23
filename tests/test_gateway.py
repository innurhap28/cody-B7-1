"""Codyssey HTTP contract tests with MockTransport; no external network or real key."""
import importlib.util
import json
import os
import unittest
from unittest.mock import patch

from async_runner import run

os.environ["SECRET_KEY"]="test-only-shortform-secret-at-least-32"
os.environ["LLM_API_KEY"]=""
AVAILABLE=bool(importlib.util.find_spec("httpx") and importlib.util.find_spec("pydantic_settings"))
if AVAILABLE:
    import httpx
    from app.config import settings
    from app.services import llm


@unittest.skipUnless(AVAILABLE,"HTTP client dependencies are not installed")
class CodysseyGatewayTests(unittest.TestCase):
    def invoke(self,handler,style="openai"):
        original=httpx.AsyncClient
        transport=httpx.MockTransport(handler)
        def factory(**kwargs):return original(transport=transport,**kwargs)
        with patch.object(settings,"LLM_API_KEY","test-only-key"),patch.object(settings,"LLM_API_STYLE",style),patch.object(llm.httpx,"AsyncClient",side_effect=factory):
            return run(llm.ask_llm("JSON 객체로 답해 주세요.",[{"role":"user","content":"숏폼 기획"}]))

    def test_codyssey_endpoint_model_auth_and_default_contract(self):
        seen=[]
        def handler(request):
            seen.append(request)
            return httpx.Response(200,json={"choices":[{"message":{"content":"{\"brief_patch\":{}}"},"finish_reason":"stop"}]})
        self.assertEqual(json.loads(self.invoke(handler)),{"brief_patch":{}})
        request=seen[0];body=json.loads(request.content)
        self.assertEqual(str(request.url),"https://copa.codyssey.kr/v1/chat/completions")
        self.assertEqual(request.headers["Authorization"],"Bearer test-only-key")
        self.assertEqual(body["model"],settings.LLM_MODEL)
        self.assertNotIn("response_format",body)
        self.assertEqual(body["max_completion_tokens"],settings.LLM_MAX_COMPLETION_TOKENS)
        self.assertNotIn("api_key",body)

    def test_json_mode_is_sent_only_when_explicitly_enabled(self):
        seen = []
        def handler(request):
            seen.append(json.loads(request.content))
            return httpx.Response(200,json={"choices":[{"message":{"content":"{}"}}]})
        with patch.object(settings, "LLM_JSON_MODE", True):
            self.invoke(handler)
        self.assertEqual(seen[0]["response_format"], {"type":"json_object"})

    def test_missing_key_does_not_open_client(self):
        with patch.object(settings,"LLM_API_KEY",""),patch.object(llm.httpx,"AsyncClient") as client:
            with self.assertRaises(llm.AIServiceError):run(llm.ask_llm("JSON",[]))
            client.assert_not_called()

    def test_timeout_maps_to_safe_exception(self):
        def handler(request):raise httpx.ReadTimeout("simulated",request=request)
        with self.assertRaises(llm.AITimeoutError):self.invoke(handler)

    def test_rate_limit_is_distinct_and_not_retried(self):
        seen=[]
        def handler(request):
            seen.append(request)
            return httpx.Response(429,json={"error":{"message":"private upstream detail"}})
        with self.assertRaises(llm.AIRateLimitError) as error:self.invoke(handler)
        self.assertEqual(len(seen),1)
        self.assertNotIn("private",str(error.exception))

    def test_http_failure_does_not_expose_body(self):
        def handler(request):return httpx.Response(503,text="private provider response")
        with self.assertRaises(llm.AIServiceError) as error:self.invoke(handler)
        self.assertNotIn("private",str(error.exception))

    def test_authentication_and_access_denial_are_distinct_without_body_leak(self):
        for status, expected in [(401, llm.AIAuthenticationError), (403, llm.AIAccessDeniedError)]:
            def handler(request):
                return httpx.Response(status, json={"error":{"message":"private provider response"}})
            with self.subTest(status=status), self.assertRaises(expected) as error:
                self.invoke(handler)
            self.assertNotIn("private", str(error.exception))

    def test_malformed_provider_json(self):
        def handler(request):return httpx.Response(200,text="not json")
        with self.assertRaises(llm.AIServiceError):self.invoke(handler)

    def test_empty_answer(self):
        def handler(request):return httpx.Response(200,json={"choices":[{"message":{"content":" "}}]})
        with self.assertRaises(llm.AIServiceError):self.invoke(handler)

    def test_truncated_answer_is_not_accepted(self):
        def handler(request):return httpx.Response(200,json={"choices":[{"message":{"content":"{}"},"finish_reason":"length"}]})
        with self.assertRaises(llm.AIServiceError):self.invoke(handler)

    def test_anthropic_contract_keeps_system_separate_and_reads_text_only(self):
        seen = []
        def handler(request):
            seen.append(request)
            return httpx.Response(200, json={"content": [
                {"type": "thinking", "thinking": "private reasoning"},
                {"type": "text", "text": "{\"brief_patch\":"},
                {"type": "text", "text": "{}}"},
            ], "stop_reason": "end_turn"})
        with patch.object(settings, "LLM_JSON_MODE", True):
            self.assertEqual(json.loads(self.invoke(handler, "anthropic")), {"brief_patch": {}})
        self.assertEqual(len(seen), 1)
        request = seen[0]
        body = json.loads(request.content)
        self.assertEqual(str(request.url), "https://copa.codyssey.kr/v1/messages")
        self.assertEqual(request.headers["x-api-key"], "test-only-key")
        self.assertEqual(request.headers["anthropic-version"], "2023-06-01")
        self.assertNotIn("Authorization", request.headers)
        self.assertEqual(body["system"], "JSON 객체로 답해 주세요.")
        self.assertEqual(body["messages"], [{"role": "user", "content": "숏폼 기획"}])
        self.assertEqual(body["model"], settings.LLM_MODEL)
        self.assertEqual(body["max_tokens"], settings.LLM_MAX_COMPLETION_TOKENS)
        self.assertNotIn("max_completion_tokens", body)
        self.assertNotIn("response_format", body)

    def test_anthropic_incomplete_nontext_or_malformed_output_is_rejected(self):
        cases = [
            {"content": [{"type": "text", "text": "{}"}], "stop_reason": reason}
            for reason in ["max_tokens", "tool_use", "refusal", None]
        ] + [
            {"content": [{"type": "thinking", "thinking": "private reasoning"}], "stop_reason": "end_turn"},
            {"content": [{"type": "text", "text": " "}], "stop_reason": "end_turn"},
            {"content": [{"type": "text", "text": 123}], "stop_reason": "end_turn"},
            {"content": "private provider response", "stop_reason": "end_turn"},
            {"content": [None], "stop_reason": "end_turn"},
            {"content": [{"type": "text"}], "stop_reason": "end_turn"},
        ]
        for data in cases:
            def handler(request):
                return httpx.Response(200, json=data)
            with self.subTest(data=data), self.assertRaises(llm.AIServiceError) as error:
                self.invoke(handler, "anthropic")
            self.assertNotIn("private", str(error.exception))

    def test_anthropic_http_failures_are_safe_and_not_retried(self):
        for status, error_type in [(401, llm.AIAuthenticationError), (403, llm.AIAccessDeniedError),
                                   (429, llm.AIRateLimitError), (503, llm.AIServiceError)]:
            seen = []
            def handler(request):
                seen.append(request)
                return httpx.Response(status, json={"error": {"message": "private response"}})
            with self.subTest(status=status), self.assertRaises(error_type) as error:
                self.invoke(handler, "anthropic")
            self.assertEqual(len(seen), 1)
            self.assertNotIn("private", str(error.exception))

    def test_anthropic_timeout_is_not_retried(self):
        seen = []
        def handler(request):
            seen.append(request)
            raise httpx.ReadTimeout("simulated", request=request)
        with self.assertRaises(llm.AITimeoutError):
            self.invoke(handler, "anthropic")
        self.assertEqual(len(seen), 1)


if __name__=="__main__":unittest.main()
