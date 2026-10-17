import copy
import json
import os
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from unittest.mock import patch

from astra.config import DEFAULT
from astra.providers import Client, ProviderError


class ProviderTests(unittest.TestCase):
    def setUp(self):
        self.requests = []
        self.response = {"message": {"content": "Hello"}, "prompt_eval_count": 12, "eval_count": 3, "done_reason": "stop"}
        self.status = 200
        owner = self

        class Handler(BaseHTTPRequestHandler):
            def do_POST(self):
                payload = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
                owner.requests.append({"path": self.path, "payload": payload, "authorization": self.headers.get("Authorization")})
                self.send_response(owner.status)
                if owner.status == 307:
                    self.send_header("Location", f"http://127.0.0.1:{self.server.server_port}/redirected")
                self.end_headers()
                self.wfile.write(json.dumps(owner.response).encode())

            def log_message(self, format, *args):
                pass

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.config = copy.deepcopy(DEFAULT)
        self.config["providers"]["local"]["base_url"] = f"http://127.0.0.1:{self.server.server_port}"

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join()

    def complete(self, schema=None):
        return Client(self.config).complete("worker", [{"role": "user", "content": "Hi"}], 64, schema, 5)

    def test_local_adapter_disables_thinking_and_limits_cpu(self):
        result = self.complete({"type": "object"})
        request = self.requests[0]
        self.assertEqual(request["path"], "/api/chat")
        self.assertFalse(request["payload"]["think"])
        self.assertEqual(request["payload"]["options"]["num_thread"], 2)
        self.assertEqual(request["payload"]["options"]["num_predict"], 64)
        self.assertEqual(result["estimated_cost_usd"], 0.0)

    def test_compatible_adapter_and_accounting(self):
        self.config["providers"]["local"].update({"type": "compatible", "api_key_env": "ASTRA_TEST_KEY", "input_per_million": 1, "output_per_million": 2})
        self.response = {"choices": [{"message": {"content": "Hello"}, "finish_reason": "length"}], "usage": {"prompt_tokens": 100, "completion_tokens": 50}}
        with patch.dict(os.environ, {"ASTRA_TEST_KEY": "test-placeholder"}):
            result = self.complete({"type": "object"})
        request = self.requests[0]
        self.assertEqual(request["authorization"], "Bearer test-placeholder")
        self.assertEqual(request["path"], "/chat/completions")
        self.assertEqual(request["payload"]["response_format"], {"type": "json_object"})
        self.assertNotIn("think", request["payload"])
        self.assertAlmostEqual(result["estimated_cost_usd"], 0.0002)
        self.assertTrue(result["truncated"])

    def test_missing_cloud_usage_is_unknown_not_free(self):
        self.config["providers"]["local"]["type"] = "compatible"
        self.response = {"choices": [{"message": {"content": "Hello"}}]}
        self.assertIsNone(self.complete()["estimated_cost_usd"])

    def test_missing_key_prevents_network_call(self):
        self.config["providers"]["local"]["api_key_env"] = "ASTRA_TEST_MISSING_KEY"
        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaisesRegex(ProviderError, "ASTRA_TEST_MISSING_KEY"):
                self.complete()
        self.assertEqual(self.requests, [])

    def test_http_error_does_not_echo_provider_body_or_retry(self):
        self.status = 401
        self.response = {"error": "secret-placeholder"}
        with self.assertRaises(ProviderError) as captured:
            self.complete()
        self.assertNotIn("secret-placeholder", str(captured.exception))
        self.assertEqual(len(self.requests), 1)

    def test_malformed_key_is_rejected_without_echoing_secret(self):
        self.config["providers"]["local"]["api_key_env"] = "ASTRA_TEST_KEY"
        with patch.dict(os.environ, {"ASTRA_TEST_KEY": "test-placeholder\n"}):
            with self.assertRaises(ProviderError) as captured:
                self.complete()
        self.assertNotIn("test-placeholder", str(captured.exception))
        self.assertEqual(self.requests, [])

    def test_redirect_does_not_forward_credentials(self):
        self.status = 307
        self.config["providers"]["local"]["api_key_env"] = "ASTRA_TEST_KEY"
        with patch.dict(os.environ, {"ASTRA_TEST_KEY": "test-placeholder"}):
            with self.assertRaises(ProviderError):
                self.complete()
        self.assertEqual(len(self.requests), 1)

    def test_empty_model_response_fails(self):
        self.response["message"]["content"] = ""
        with self.assertRaises(ProviderError):
            self.complete()


if __name__ == "__main__":
    unittest.main()
