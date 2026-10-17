import hashlib
import re
from pathlib import Path

from .config import AstraError


def clip_bytes(text, limit):
    return text.encode("utf-8")[:max(0, limit)].decode("utf-8", errors="ignore")


def collect_context(task, files, budget):
    if len(files) > 12:
        raise AstraError("Tối đa 12 file ngữ cảnh mỗi lượt.")
    query = set(re.findall(r"\w{3,}", task.casefold()))
    chunks = []
    documents = []
    for filename in dict.fromkeys(files):
        path = Path(filename).expanduser().resolve()
        with path.open("rb") as stream:
            data = stream.read(262145)
        if len(data) > 262144:
            raise AstraError(f"File quá 256 KB: {path}. Hãy trích phần cần dùng.")
        try:
            text = data.decode("utf-8")
        except UnicodeError:
            raise AstraError(f"Chỉ hỗ trợ file text UTF-8: {path}") from None
        if "\x00" in text:
            raise AstraError(f"Không hỗ trợ file nhị phân: {path}")
        documents.append({"path": str(path), "sha256": hashlib.sha256(data).hexdigest()})
        for offset in range(0, len(text), 600):
            chunk = text[offset:offset + 700]
            words = set(re.findall(r"\w{3,}", chunk.casefold()))
            chunks.append((len(query & words), len(chunks), str(path), offset, chunk))
    chunks.sort(key=lambda entry: (-entry[0], entry[1]))
    excerpts = []
    remaining = budget
    for score, order, path, offset, chunk in chunks:
        if remaining < 100:
            break
        source = f"S{len(excerpts) + 1}"
        excerpt = clip_bytes(chunk, min(remaining - 40, 1100))
        excerpts.append({"id": source, "path": path, "offset": offset, "text": excerpt})
        remaining -= len(excerpt.encode("utf-8")) + 40
    return {"documents": documents, "excerpts": excerpts}


def validate_checks(checks):
    if not isinstance(checks, dict) or set(checks) - {"contains", "not_contains", "json"}:
        raise AstraError("checks chỉ hỗ trợ contains, not_contains, json.")
    for key in ("contains", "not_contains"):
        entries = checks.get(key, [])
        if not isinstance(entries, list) or any(not isinstance(item, str) or not item for item in entries):
            raise AstraError(f"checks.{key} phải là danh sách chuỗi không rỗng.")
    if "json" in checks and type(checks["json"]) is not bool:
        raise AstraError("checks.json phải là boolean.")
    return checks
