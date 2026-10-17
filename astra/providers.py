import json
import os
import socket
import urllib.error
import urllib.request

from .config import AstraError


class ProviderError(AstraError):
    pass


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, request, stream, code, message, headers, new_url):
        return None


def request_json(url, payload=None, headers=None, timeout=30):
    body = None if payload is None else json.dumps(payload, ensure_ascii=False).encode("utf-8")
    request = urllib.request.Request(url, data=body, headers={"Content-Type": "application/json", **(headers or {})})
    try:
        with urllib.request.build_opener(NoRedirect()).open(request, timeout=timeout) as response:
            raw = response.read(4_000_001)
        if len(raw) > 4_000_000:
            raise ProviderError("Response vượt giới hạn 4 MB.")
        value = json.loads(raw)
        if not isinstance(value, dict):
            raise ProviderError("Provider trả JSON không đúng định dạng.")
        return value
    except urllib.error.HTTPError as error:
        hints = {401: "Kiểm tra API key.", 404: "Kiểm tra endpoint/model; local cần ollama pull.", 429: "Hết quota hoặc rate limit; thử lại sau."}
        code = error.code
        error.close()
        raise ProviderError(f"HTTP {code}. {hints.get(code, 'Kiểm tra provider.')} Không tự gửi lại request.") from None
    except (urllib.error.URLError, TimeoutError, socket.timeout, ConnectionError):
        raise ProviderError("Không kết nối được hoặc quá thời gian. Kiểm tra service/mạng. Request có thể đã được xử lý; không tự gửi lại.") from None
    except (ValueError, UnicodeError):
        raise ProviderError("Provider trả dữ liệu không phải JSON hợp lệ.") from None


def auth_headers(provider):
    variable = provider.get("api_key_env")
    if not variable:
        return {}
    token = os.environ.get(variable)
    if not token:
        raise ProviderError(f"Thiếu biến môi trường {variable}. Nhập key ở terminal; không ghi key vào config.")
    if "\r" in token or "\n" in token:
        raise ProviderError("API key chứa ký tự xuống dòng; nhập lại key trong terminal.")
    return {"Authorization": f"Bearer {token}"}


def nonnegative_count(value):
    return value if type(value) is int and value >= 0 else None


class Client:
    def __init__(self, config):
        self.config = config

    def complete(self, role, messages, max_tokens, schema, timeout):
        spec = self.config["roles"][role]
        provider = self.config["providers"][spec["provider"]]
        limits = self.config["limits"]
        payload = {"model": spec["model"], "messages": messages, "stream": False}
        if provider["type"] == "ollama":
            payload.update({"think": False, "keep_alive": limits["keep_alive"], "options": {
                "num_ctx": limits["num_ctx"], "num_predict": max_tokens,
                "num_thread": limits["num_thread"], "temperature": 0 if schema else 0.2,
            }})
            if schema:
                payload["format"] = schema
            endpoint = "/api/chat"
        else:
            payload["max_tokens"] = max_tokens
            if schema and provider.get("json_mode", "object") == "object":
                payload["response_format"] = {"type": "json_object"}
            endpoint = "/chat/completions"
        response = request_json(provider["base_url"].rstrip("/") + endpoint, payload, auth_headers(provider), timeout)
        if response.get("error"):
            raise ProviderError("Provider báo lỗi; kiểm tra model và cấu hình.")
        try:
            if provider["type"] == "ollama":
                text = response["message"]["content"]
                input_tokens = nonnegative_count(response.get("prompt_eval_count"))
                output_tokens = nonnegative_count(response.get("eval_count"))
                truncated = response.get("done_reason") == "length"
            else:
                choice = response["choices"][0]
                text = choice["message"]["content"]
                usage = response.get("usage") or {}
                input_tokens = nonnegative_count(usage.get("prompt_tokens"))
                output_tokens = nonnegative_count(usage.get("completion_tokens"))
                truncated = choice.get("finish_reason") == "length"
        except (KeyError, IndexError, TypeError, AttributeError):
            raise ProviderError("Response thiếu content/usage đúng định dạng.") from None
        if not isinstance(text, str) or not text.strip():
            raise ProviderError("Model không trả nội dung. Kiểm tra hỗ trợ chat và tắt thinking ở provider nếu cần.")
        rates = (provider.get("input_per_million"), provider.get("output_per_million"))
        cost = 0.0 if provider["type"] == "ollama" else None
        if provider["type"] != "ollama" and None not in (*rates, input_tokens, output_tokens):
            cost = (input_tokens * rates[0] + output_tokens * rates[1]) / 1_000_000
        return {"text": text.strip(), "input_tokens": input_tokens, "output_tokens": output_tokens,
                "estimated_cost_usd": cost, "truncated": truncated}

    def models(self, provider_name):
        provider = self.config["providers"][provider_name]
        is_local = provider["type"] == "ollama"
        result = request_json(provider["base_url"].rstrip("/") + ("/api/tags" if is_local else "/models"), headers=auth_headers(provider), timeout=10)
        entries = result.get("models" if is_local else "data", [])
        return [entry.get("name" if is_local else "id", "") for entry in entries if isinstance(entry, dict)]
