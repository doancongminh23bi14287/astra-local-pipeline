import copy
import fcntl
import hashlib
import json
import os
import re
import shlex
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

from .config import ROOT, AstraError, validate_config
from .context import clip_bytes


METHOD = "Clarify goal → use evidence → plan → produce → check → bounded repair. Keep assumptions explicit."


def digest(value):
    encoded = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def config_digest(config):
    stable = copy.deepcopy(config)
    for field in ("max_calls", "max_seconds"):
        stable["limits"].pop(field, None)
    return digest(stable)


def atomic_text(path, content):
    temporary = path.with_name(path.name + ".tmp")
    descriptor = os.open(temporary, os.O_CREAT | os.O_TRUNC | os.O_WRONLY, 0o600)
    with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
        stream.write(content)
    os.replace(temporary, path)


@contextmanager
def session_lock(directory):
    with (directory / ".lock").open("a") as stream:
        try:
            fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise AstraError("Phiên đang được cập nhật; thử lại sau.") from None
        try:
            yield
        finally:
            fcntl.flock(stream, fcntl.LOCK_UN)


def session_path(name, root=None):
    if not re.fullmatch(r"[A-Za-z0-9_-]{1,64}", name):
        raise AstraError("Tên phiên chỉ gồm chữ ASCII, số, dấu - hoặc _, tối đa 64 ký tự.")
    return Path(root or ROOT / "sessions").expanduser().resolve() / name


def verify_session(data):
    if data.get("version") != 1:
        raise AstraError("Phiên không đúng định dạng.")
    validate_config(data["config"])
    for value, checksum in (("contract", "contract_hash"), ("protocol", "protocol_hash")):
        if digest(data[value]) != data[checksum]:
            raise AstraError(f"{value} của phiên đã thay đổi ngoài lệnh quản lý. Tạo phiên mới để đổi mục tiêu/quy trình.")
    if config_digest(data["config"]) != data["config_hash"]:
        raise AstraError("Cấu hình model/prompt budget của phiên đã thay đổi. Tạo phiên mới cho cấu hình mới.")
    if data["mode"] not in ("fast", "balanced", "thorough"):
        raise AstraError("Mode phiên không hợp lệ.")
    if digest(data["mode"]) != data["mode_hash"]:
        raise AstraError("Mode phiên đã bị thay đổi ngoài lệnh quản lý.")


def read_session(directory):
    data = json.loads((directory / "session.json").read_text(encoding="utf-8"))
    verify_session(data)
    return data


def snapshot(data, directory):
    return {
        "name": data["name"], "id": data["id"], "revision": data["revision"],
        "directory": str(directory.resolve()), "contract": copy.deepcopy(data["contract"]),
        "contract_hash": data["contract_hash"], "config_hash": data["config_hash"],
        "protocol_hash": data["protocol_hash"],
        "mode": data["mode"], "mode_hash": data["mode_hash"],
        "notes": [copy.deepcopy(note) for note in data["notes"] if note["active"]],
        "recent_runs": copy.deepcopy(data["runs"][-3:]),
    }


def memory_payload(session):
    confirmed = [{"id": note["id"], "kind": note["kind"], "text": note["text"], "source": note["source"]}
                 for note in session["notes"] if note["kind"] in ("decision", "fact")]
    working = [{"id": note["id"], "kind": note["kind"], "text": note["text"]}
               for note in session["notes"] if note["kind"] in ("open", "next")]
    recent = [{"task": clip_bytes(run["task"], 300), "status": run["status"],
               "answer_preview": run.get("answer_preview", ""), "preview_truncated": run.get("preview_truncated", False)}
              for run in session["recent_runs"]]
    return {"contract": session["contract"], "user_records": confirmed}, working, recent


def handoff_text(data, directory):
    contract = data["contract"]
    root_argument = shlex.quote(str(directory.parent))
    lines = ["# Bàn giao phiên AI", "", f"Phiên: {data['name']} · revision {data['revision']}",
             f"Contract SHA-256: {data['contract_hash']}", f"Protocol SHA-256: {data['protocol_hash']}",
             "", "## Mục tiêu cố định", "", contract["goal"], "", "## Ràng buộc cố định", ""]
    lines.extend("- " + item for item in contract["constraints"])
    lines += ["", "## Cách làm việc", "", contract["method"], "", f"Mode: {data['mode']}", ""]
    lines.extend(f"- {role}: {spec['provider']} / {spec['model']}" for role, spec in data["config"]["roles"].items())
    lines += ["", "## Ghi chú do người dùng nhập", "", "Fact là dữ kiện người dùng cung cấp kèm nguồn, chưa phải xác minh tự động.", ""]
    for note in data["notes"]:
        if note["active"]:
            lines.append(f"- {note['id']} [{note['kind']}]: {note['text']}" + (f" — Nguồn: {note['source']}" if note["source"] else ""))
    lines += ["", "## Các lượt gần nhất", "", "Các kết quả này không tự trở thành sự thật hoặc quyết định đã chốt.", ""]
    for run in data["runs"][-5:]:
        lines += [f"- {run['task']} — {run['status']}", f"  Báo cáo: {run['directory']}/report.md"]
    lines += ["", "## Khôi phục công việc", "",
              "1. Đọc mục tiêu, ràng buộc, decisions, facts và việc còn mở trước khi xử lý yêu cầu mới.",
              "2. Giữ quy trình/model đã chọn; nếu yêu cầu mới xung đột mục tiêu, nêu xung đột trước khi đổi.",
              "3. Mở báo cáo và file nguồn liên quan; không suy diễn rằng run pass nghĩa là mọi dữ kiện đều đúng.",
              "4. Chỉ ghi quyết định/dữ kiện vào bộ nhớ khi người dùng chủ động xác nhận qua lệnh note.",
              "5. Lưu next/open cụ thể trước khi đổi terminal hoặc AI.", "", "```bash",
              f'astra session show {data["name"]} --sessions-dir {root_argument}',
              f'astra run "Yêu cầu tiếp theo" --session {data["name"]} --sessions-dir {root_argument}',
              "```", "", "Đây là bộ nhớ văn bản có thể đọc lại, không phải chuỗi suy luận nội bộ của model."]
    return "\n".join(lines) + "\n"


def save_session(directory, data):
    verify_session(data)
    atomic_text(directory / "session.json", json.dumps(data, ensure_ascii=False, indent=2) + "\n")
    atomic_text(directory / "HANDOFF.md", handoff_text(data, directory))


def create_session(name, goal, constraints, config, protocol, mode, root=None):
    if not goal.strip() or len(goal.encode("utf-8")) > 500:
        raise AstraError("Mục tiêu phiên cần 1–500 byte UTF-8, viết ngắn gọn.")
    if len(constraints) > 6 or any(not item.strip() or len(item.encode("utf-8")) > 250 for item in constraints):
        raise AstraError("Tối đa 6 ràng buộc, mỗi ràng buộc 1–250 byte UTF-8.")
    directory = session_path(name, root)
    directory.parent.mkdir(parents=True, exist_ok=True)
    if directory.exists():
        raise AstraError("Phiên đã tồn tại; dùng session show hoặc chọn tên khác.")
    data = {"version": 1, "name": name, "id": uuid.uuid4().hex, "revision": 1,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "contract": {"goal": goal.strip(), "constraints": constraints, "method": METHOD},
            "config": copy.deepcopy(config), "protocol": copy.deepcopy(protocol), "mode": mode,
            "notes": [], "runs": []}
    data.update({"contract_hash": digest(data["contract"]), "protocol_hash": digest(protocol),
                 "config_hash": config_digest(config), "mode_hash": digest(mode)})
    verify_session(data)
    directory.mkdir(mode=0o700)
    with session_lock(directory):
        save_session(directory, data)
    return directory


def add_note(name, kind, text, source="", supersedes=None, root=None):
    if kind not in ("decision", "fact", "open", "next") or not text.strip() or len(text.encode("utf-8")) > 400:
        raise AstraError("Ghi chú cần loại hợp lệ và nội dung 1–400 byte UTF-8.")
    if kind == "fact" and not source.strip():
        raise AstraError("Fact cần --source để biết dữ kiện lấy từ đâu.")
    if len(source.encode("utf-8")) > 250:
        raise AstraError("Nguồn quá dài; dùng đường dẫn/ngắn gọn tối đa 250 byte.")
    directory = session_path(name, root)
    with session_lock(directory):
        data = read_session(directory)
        if supersedes:
            replaced = next((note for note in data["notes"] if note["id"] == supersedes and note["active"]), None)
            if replaced is None:
                raise AstraError("Không tìm thấy ghi chú đang có hiệu lực để thay thế.")
            replaced["active"] = False
        note = {"id": f"N{len(data['notes']) + 1}", "kind": kind, "text": text.strip(), "source": source.strip(),
                "active": True, "origin": "user", "supersedes": supersedes}
        data["notes"].append(note)
        data["revision"] += 1
        save_session(directory, data)
    return note["id"]


def record_run(state, run_directory):
    session = state.get("session")
    if not session:
        return
    directory = Path(session["directory"])
    with session_lock(directory):
        data = read_session(directory)
        if data["id"] != session["id"] or data["contract_hash"] != session["contract_hash"]:
            raise AstraError("Phiên gốc đã bị thay thế; run giữ nguyên trong thư mục kết quả.")
        entry = {"directory": str(Path(run_directory).resolve()), "task": state["task"], "status": state["status"],
                 "memory_revision": session["revision"], "answer_preview": clip_bytes(state["answer"], 600),
                 "preview_truncated": len(state["answer"].encode("utf-8")) > 600}
        previous = next((run for run in data["runs"] if run["directory"] == entry["directory"]), None)
        if previous == entry:
            return
        if previous:
            previous.update(entry)
        else:
            data["runs"].append(entry)
        data["revision"] += 1
        save_session(directory, data)
