import copy
import json
import math
from pathlib import Path
from urllib.parse import urlparse


ROOT = Path(__file__).resolve().parent.parent
DEFAULT = {
    "providers": {
        "local": {"type": "ollama", "base_url": "http://127.0.0.1:11434"}
    },
    "roles": {
        role: {"provider": "local", "model": "qwen3:1.7b"}
        for role in ("planner", "worker", "reviewer")
    },
    "limits": {
        "max_calls": 7,
        "max_seconds": 900,
        "request_timeout": 180,
        "num_ctx": 4096,
        "num_thread": 2,
        "plan_tokens": 192,
        "answer_tokens": 384,
        "review_tokens": 256,
        "context_bytes": 1400,
        "max_task_bytes": 1600,
        "keep_alive": "2m",
    },
    "language": "Vietnamese",
}


class AstraError(Exception):
    pass


def validate_config(config):
    if not isinstance(config, dict):
        raise AstraError("Config phải là JSON object.")
    for section in ("providers", "roles", "limits"):
        if not isinstance(config.get(section), dict):
            raise AstraError(f"Config thiếu object {section}.")
    limits = config["limits"]
    for field in DEFAULT["limits"]:
        if field == "keep_alive":
            if not isinstance(limits.get(field), str):
                raise AstraError("keep_alive phải là chuỗi, ví dụ 2m.")
        elif type(limits.get(field)) is not int or limits[field] < 1:
            raise AstraError(f"limits.{field} phải là số nguyên dương.")
    if limits["num_ctx"] < 2048:
        raise AstraError("num_ctx tối thiểu 2048.")
    if max(limits[key] for key in ("plan_tokens", "answer_tokens", "review_tokens")) > limits["num_ctx"] // 2:
        raise AstraError("Số token đầu ra mỗi bước không được vượt nửa num_ctx.")
    if not isinstance(config.get("language"), str) or not config["language"].strip():
        raise AstraError("language phải là chuỗi không rỗng.")
    for name, provider in config["providers"].items():
        if not isinstance(provider, dict) or provider.get("type") not in ("ollama", "compatible"):
            raise AstraError(f"Provider {name}: type phải là ollama hoặc compatible.")
        allowed = {"type", "base_url", "api_key_env", "json_mode", "input_per_million", "output_per_million"}
        if set(provider) - allowed:
            raise AstraError(f"Provider {name}: có trường không hỗ trợ. Key chỉ khai báo qua tên biến api_key_env.")
        base_url = provider.get("base_url", "")
        if not isinstance(base_url, str):
            raise AstraError(f"Provider {name}: base_url phải là chuỗi.")
        parsed = urlparse(base_url)
        if parsed.scheme not in ("http", "https") or not parsed.hostname or parsed.username or parsed.password or parsed.query or parsed.fragment:
            raise AstraError(f"Provider {name}: URL không hợp lệ hoặc chứa thông tin đăng nhập.")
        if parsed.scheme == "http" and parsed.hostname not in ("127.0.0.1", "localhost", "::1"):
            raise AstraError("Endpoint từ xa phải dùng HTTPS.")
        if provider.get("json_mode", "object") not in ("object", "none"):
            raise AstraError("json_mode phải là object hoặc none.")
        if "api_key_env" in provider and not isinstance(provider["api_key_env"], str):
            raise AstraError("api_key_env phải là tên biến môi trường.")
        for field in ("input_per_million", "output_per_million"):
            value = provider.get(field)
            if value is not None and (type(value) not in (int, float) or not math.isfinite(value) or value < 0):
                raise AstraError(f"{field} phải là đơn giá không âm hoặc null.")
    if set(config["roles"]) != {"planner", "worker", "reviewer"}:
        raise AstraError("roles phải gồm planner, worker, reviewer.")
    for role in ("planner", "worker", "reviewer"):
        spec = config["roles"].get(role)
        if not isinstance(spec, dict) or spec.get("provider") not in config["providers"]:
            raise AstraError(f"Vai trò {role} tham chiếu provider không tồn tại.")
        if set(spec) != {"provider", "model"}:
            raise AstraError(f"Vai trò {role} chỉ hỗ trợ provider và model.")
        if not isinstance(spec.get("model"), str) or not spec["model"].strip():
            raise AstraError(f"Vai trò {role} thiếu model.")
    return config


def load_config(path=None):
    config = copy.deepcopy(DEFAULT)
    if path:
        raw = json.loads(Path(path).read_text(encoding="utf-8"))
        if not isinstance(raw, dict):
            raise AstraError("Config phải là JSON object.")
        for key, value in raw.items():
            if key not in DEFAULT:
                raise AstraError(f"Trường config không được hỗ trợ: {key}")
            if key == "limits" and isinstance(value, dict):
                unknown = set(value) - set(DEFAULT["limits"])
                if unknown:
                    raise AstraError(f"Giới hạn không hợp lệ: {sorted(unknown)}")
                config[key].update(value)
            else:
                config[key] = value
    return validate_config(config)
