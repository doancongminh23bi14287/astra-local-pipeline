import copy
import fcntl
import json
import os
import re
import time
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

from .config import AstraError, validate_config
from .context import validate_checks
from .prompts import protocol_bundle
from .providers import Client
from .session import config_digest, digest, memory_payload


MODES = {"fast": {"plan": False, "repairs": 0}, "balanced": {"plan": True, "repairs": 1}, "thorough": {"plan": True, "repairs": 2}}


class BudgetExceeded(AstraError):
    pass


def write_private(path, text):
    temporary = path.with_name(path.name + ".tmp")
    descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
        stream.write(text)
    os.replace(temporary, path)


@contextmanager
def run_lock(directory):
    with (directory / ".lock").open("a") as stream:
        try:
            fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise AstraError("Run này đang chạy ở terminal khác.") from None
        try:
            yield
        finally:
            fcntl.flock(stream, fcntl.LOCK_UN)


def check_answer(answer, checks, context):
    results = []
    for required in checks.get("contains", []):
        results.append({"check": f"contains: {required}", "passed": required.casefold() in answer.casefold()})
    for forbidden in checks.get("not_contains", []):
        results.append({"check": f"not_contains: {forbidden}", "passed": forbidden.casefold() not in answer.casefold()})
    if checks.get("json"):
        try:
            json.loads(answer)
            valid_json = True
        except ValueError:
            valid_json = False
        results.append({"check": "JSON thuần hợp lệ", "passed": valid_json})
    allowed = {entry["id"] for entry in context["excerpts"]}
    for source in sorted(set(re.findall(r"\[(S\d+)\]", answer))):
        results.append({"check": f"Nguồn {source} tồn tại", "passed": source in allowed})
    results.append({"check": "Nội dung không rỗng", "passed": bool(answer.strip())})
    return results


def parse_structured(text, role):
    stripped = text.strip()
    if stripped.startswith("```") and stripped.endswith("```"):
        stripped = stripped.split("\n", 1)[-1].rsplit("```", 1)[0]
    try:
        value = json.loads(stripped)
    except ValueError:
        raise AstraError("Model trả JSON không hợp lệ.") from None
    if not isinstance(value, dict):
        raise AstraError("Kết quả phải là JSON object.")
    if role == "planner":
        if set(value) != {"goal", "steps", "acceptance"} or not isinstance(value.get("goal"), str) or not value["goal"].strip():
            raise AstraError("Plan thiếu goal/steps/acceptance.")
        for field in ("steps", "acceptance"):
            entries = value[field]
            if not isinstance(entries, list) or not 1 <= len(entries) <= 3 or any(not isinstance(entry, str) or not entry.strip() for entry in entries):
                raise AstraError("Plan cần 1–3 bước và 1–3 tiêu chí dạng chuỗi.")
    else:
        if set(value) != {"verdict", "issues"} or value.get("verdict") not in ("pass", "revise", "uncertain"):
            raise AstraError("Review thiếu verdict hợp lệ.")
        if not isinstance(value["issues"], list) or len(value["issues"]) > 4 or any(not isinstance(entry, str) or not entry.strip() for entry in value["issues"]):
            raise AstraError("Review issues không hợp lệ.")
        if value["verdict"] == "pass" and value["issues"]:
            value["verdict"] = "revise"
        if value["verdict"] != "pass" and not value["issues"]:
            value["issues"] = ["Reviewer chưa xác nhận được câu trả lời."]
    return value


def build_messages(state, role, revision=False, correction=""):
    config = state["config"]
    limits = config["limits"]
    protocol = state.get("protocol") or protocol_bundle()
    if state.get("protocol_hash") and digest(protocol) != state["protocol_hash"]:
        raise AstraError("Bộ prompt/schema của run đã bị thay đổi; không tiếp tục bằng quy trình khác.")
    prompt = protocol["reviser" if role == "worker" and revision else role]
    system = prompt + " Answer in " + config["language"] + ". " + correction
    payload = {"task": state["task"], "acceptance_checks": state["checks"]}
    schema = protocol["plan_schema"] if role == "planner" else protocol["review_schema"] if role == "reviewer" else None
    output_limit = limits[{"planner": "plan_tokens", "worker": "answer_tokens", "reviewer": "review_tokens"}[role]]
    if role == "reviewer" or revision:
        payload["draft"] = state["answer"]
    if role == "reviewer":
        payload["machine_checks"] = state["check_results"]
    if revision:
        payload["review"] = state["review"]
        payload["failed_checks"] = [check for check in state["check_results"] if not check["passed"]]
    if role == "worker" and state.get("plan"):
        payload["plan"] = state["plan"]
    excerpts = state["context"]["excerpts"]
    payload["sources"] = [{"id": entry["id"], "text": entry["text"]} for entry in excerpts]
    if state.get("session"):
        session = state["session"]
        if digest(session["contract"]) != session["contract_hash"] or config_digest(config) != session["config_hash"]:
            raise AstraError("Mục tiêu hoặc cấu hình phiên đã thay đổi trong run.")
        if state["mode"] != session["mode"] or digest(state["mode"]) != session["mode_hash"]:
            raise AstraError("Không đổi mode giữa phiên; tạo phiên mới nếu cần đổi quy trình.")
        if session.get("protocol_hash") and state["protocol_hash"] != session["protocol_hash"]:
            raise AstraError("Bộ prompt của run không khớp phiên đã chọn.")
        if digest(session) != state["session_hash"]:
            raise AstraError("Bộ nhớ chụp cho run đã bị sửa; dùng run mới để nạp ghi chú mới.")
        pinned, working, recent = memory_payload(session)
        payload.update({"session_memory": pinned, "working_notes": working, "recent_runs_unverified": recent})
        system += " Keep the session goal, constraints and decisions. If this task conflicts, report the conflict. Prior run outcomes are not facts."
    omitted = []
    prompt_budget = limits["num_ctx"] - output_limit - 256
    while True:
        user = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
        byte_count = len((system + user + json.dumps(schema or {})).encode("utf-8"))
        if byte_count <= prompt_budget:
            break
        if payload.get("recent_runs_unverified"):
            payload["recent_runs_unverified"].pop(0)
            omitted.append("old_run_reference")
        elif payload.get("working_notes"):
            omitted.append("note:" + payload["working_notes"].pop(0)["id"])
        elif "plan" in payload:
            del payload["plan"]
            omitted.append("plan")
        elif payload["sources"]:
            omitted.append(payload["sources"].pop()["id"])
        else:
            raise AstraError("Prompt vượt ngân sách ngữ cảnh. Rút ngắn task/bộ nhớ hoặc tăng num_ctx ở phiên mới. Mục tiêu, quyết định, task và draft không bị cắt ngầm.")
    return [{"role": "system", "content": system}, {"role": "user", "content": user}], output_limit, schema, omitted


def new_state(task, config, mode, context, checks, session=None, protocol=None):
    if not task.strip():
        raise AstraError("Task không được để trống.")
    if len(task.encode("utf-8")) > config["limits"]["max_task_bytes"]:
        raise AstraError("Task quá dài. Đưa tài liệu vào --context, hoặc tăng max_task_bytes và num_ctx.")
    protocol = copy.deepcopy(protocol or protocol_bundle())
    session = copy.deepcopy(session)
    config = copy.deepcopy(config)
    return {
        "version": 1, "created_at": datetime.now(timezone.utc).isoformat(), "task": task,
        "config": config, "mode": mode, "context": context, "checks": validate_checks(checks),
        "phase": "planner" if MODES[mode]["plan"] else "draft", "status": "pending",
        "plan": None, "answer": "", "review": None, "check_results": [], "repairs": 0,
        "calls": [], "elapsed_seconds": 0.0, "error": None,
        "protocol": protocol, "protocol_hash": digest(protocol),
        "session": session, "session_hash": digest(session) if session else None,
    }


class Pipeline:
    def __init__(self, directory, state, client=None, progress=None):
        self.directory = Path(directory)
        self.state = state
        self.client = client or Client(state["config"])
        self.progress = progress or (lambda message: None)
        self.base_elapsed = state["elapsed_seconds"]
        self.started = time.monotonic()
        self.loaded_checkpoint = None

    @classmethod
    def create(cls, root, state, **kwargs):
        root = Path(root).expanduser()
        root.mkdir(parents=True, exist_ok=True)
        directory = root / (datetime.now().strftime("%Y%m%d-%H%M%S-") + uuid.uuid4().hex[:8])
        directory.mkdir(mode=0o700)
        instance = cls(directory, state, **kwargs)
        instance.save()
        return instance

    @classmethod
    def load(cls, directory, **kwargs):
        directory = Path(directory).expanduser().resolve()
        checkpoint = (directory / "state.json").read_text(encoding="utf-8")
        state = json.loads(checkpoint)
        if state.get("version") != 1:
            raise AstraError("Checkpoint không đúng phiên bản.")
        validate_config(state["config"])
        validate_checks(state["checks"])
        if state.get("mode") not in MODES or state.get("phase") not in ("planner", "draft", "review", "revise", "done"):
            raise AstraError("Checkpoint có mode/phase không hợp lệ.")
        if "protocol" not in state:
            state["protocol"] = protocol_bundle()
            state["protocol_hash"] = digest(state["protocol"])
            state["legacy_protocol_warning"] = "Run cũ chưa lưu prompt; dùng bộ prompt hiện tại từ lần resume này."
        instance = cls(directory, state, **kwargs)
        instance.loaded_checkpoint = checkpoint
        return instance

    def elapsed(self):
        return self.base_elapsed + time.monotonic() - self.started

    def save(self):
        self.state["elapsed_seconds"] = round(self.elapsed(), 3)
        write_private(self.directory / "state.json", json.dumps(self.state, ensure_ascii=False, indent=2))

    def call(self, role, revision=False, structured=False):
        for attempt in range(2 if structured else 1):
            correction = "Your previous JSON was invalid. Follow the exact JSON shape; no extra fields." if attempt else ""
            messages, output_limit, schema, omitted = build_messages(self.state, role, revision, correction)
            limits = self.state["config"]["limits"]
            remaining = limits["max_seconds"] - self.elapsed()
            if len(self.state["calls"]) >= limits["max_calls"] or remaining <= 0:
                raise BudgetExceeded("Đã chạm giới hạn lượt gọi hoặc thời gian; giữ lại bản nháp.")
            spec = self.state["config"]["roles"][role]
            trace = {"role": role, "phase": self.state["phase"], **spec, "status": "started",
                     "omitted": omitted, "messages": messages, "max_output_tokens": output_limit}
            self.state["calls"].append(trace)
            trace["protocol_hash"] = self.state.get("protocol_hash")
            if self.state.get("session"):
                trace["session_revision"] = self.state["session"]["revision"]
                trace["session_hash"] = self.state["session_hash"]
            self.save()
            self.progress(f"[{len(self.state['calls'])}/{limits['max_calls']}] {self.state['phase']} · {spec['model']}")
            started = time.monotonic()
            try:
                result = self.client.complete(role, messages, output_limit, schema, max(0.1, min(limits["request_timeout"], remaining)))
            except (AstraError, KeyboardInterrupt) as error:
                trace.update({"status": "interrupted" if isinstance(error, KeyboardInterrupt) else "failed", "seconds": round(time.monotonic() - started, 3)})
                self.save()
                raise
            trace.update({"status": "completed", "seconds": round(time.monotonic() - started, 3), **result})
            self.save()
            if not structured:
                self.state["answer_truncated"] = result["truncated"]
                return result["text"]
            try:
                if result["truncated"]:
                    raise AstraError("JSON bị cắt do giới hạn token; tăng plan_tokens/review_tokens.")
                parsed = parse_structured(result["text"], role)
                if role == "reviewer":
                    cited = set(re.findall(r"\[(S\d+)\]", self.state["answer"]))
                    if cited.intersection(omitted):
                        parsed["verdict"] = "uncertain"
                        parsed["issues"].append("Có nguồn được trích nhưng không vừa ngữ cảnh reviewer; cần kiểm tra nguồn đó.")
                return parsed
            except AstraError as error:
                trace["schema_error"] = str(error)
                self.save()
                if attempt:
                    raise

    def run(self):
        with run_lock(self.directory):
            if self.loaded_checkpoint is not None and (self.directory / "state.json").read_text(encoding="utf-8") != self.loaded_checkpoint:
                raise AstraError("Checkpoint đã đổi ở process khác; gọi resume lại để đọc bản mới.")
            self.loaded_checkpoint = None
            if self.state["phase"] == "done":
                return self.state
            self.state.update({"status": "running", "error": None})
            try:
                while self.state["phase"] != "done":
                    phase = self.state["phase"]
                    if phase == "planner":
                        self.state["plan"] = self.call("planner", structured=True)
                        self.state["phase"] = "draft"
                    elif phase == "draft":
                        self.state["answer"] = self.call("worker")
                        self.state["phase"] = "review"
                    elif phase == "revise":
                        self.state["answer"] = self.call("worker", revision=True)
                        self.state["review"] = None
                        self.state["repairs"] += 1
                        self.state["phase"] = "review"
                    else:
                        self.state["check_results"] = check_answer(self.state["answer"], self.state["checks"], self.state["context"])
                        self.state["review"] = self.call("reviewer", structured=True)
                        passed = all(check["passed"] for check in self.state["check_results"])
                        if not passed:
                            self.state["review"]["verdict"] = "revise"
                            failures = ["Failed machine check: " + check["check"] for check in self.state["check_results"] if not check["passed"]]
                            self.state["review"]["issues"] = failures + self.state["review"]["issues"]
                        if self.state.get("answer_truncated"):
                            self.state["review"]["verdict"] = "revise"
                            self.state["review"]["issues"].append("Bản nháp đã chạm giới hạn token; cần trả lời gọn và đầy đủ hơn.")
                        if passed and self.state["review"]["verdict"] == "pass":
                            self.state.update({"status": "model_review_passed", "phase": "done"})
                        elif self.state["repairs"] < MODES[self.state["mode"]]["repairs"]:
                            self.state["phase"] = "revise"
                        else:
                            self.state.update({"status": "needs_review", "phase": "done"})
                    self.save()
            except BudgetExceeded as error:
                self.state.update({"status": "budget_exhausted", "error": str(error)})
            except KeyboardInterrupt:
                self.state.update({"status": "interrupted", "error": "Đã dừng; có thể resume từ checkpoint."})
            except AstraError as error:
                self.state.update({"status": "failed", "error": str(error)})
            finally:
                self.save()
                self.export()
        return self.state

    def export(self):
        state = self.state
        write_private(self.directory / "answer.md", state["answer"] + "\n")
        for name, value in (("review.json", state["review"]), ("checks.json", state["check_results"]), ("sources.json", state["context"])):
            write_private(self.directory / name, json.dumps(value, ensure_ascii=False, indent=2) + "\n")
        complete_costs = all(entry.get("estimated_cost_usd") is not None for entry in state["calls"])
        cost = f"${sum(entry['estimated_cost_usd'] for entry in state['calls']):.6f} (ước tính)" if complete_costs else "Chưa biết: thiếu đơn giá/usage hoặc request chưa hoàn tất."
        lines = ["# Kết quả workflow", "", f"- Trạng thái: {state['status']}", f"- Số lượt gọi: {len(state['calls'])}",
                 f"- Thời gian hoạt động: {state['elapsed_seconds']:.1f}s", f"- Vòng sửa: {state['repairs']}",
                 f"- Chi phí API: {cost}", "", "Model review không phải chứng minh đáp án đúng. Checks chỉ kiểm tra điều kiện đã khai báo.", "",
                 "## Kết quả kiểm tra", ""]
        lines.extend(f"- {'PASS' if entry['passed'] else 'FAIL'}: {entry['check']}" for entry in state["check_results"])
        lines += ["", "## Vấn đề còn lại", ""]
        lines.extend("- " + issue for issue in (state["review"] or {}).get("issues", []))
        if state["error"]:
            lines.append("- " + state["error"])
        if state.get("session"):
            lines += ["", "## Bộ nhớ phiên", "", f"- Phiên: {state['session']['name']}",
                      f"- Revision bộ nhớ: {state['session']['revision']}",
                      f"- Contract: {state['session']['contract_hash']}",
                      f"- Protocol: {state.get('protocol_hash')}"]
            write_private(self.directory / "memory.json", json.dumps(state["session"], ensure_ascii=False, indent=2) + "\n")
        if state.get("legacy_protocol_warning"):
            lines += ["", state["legacy_protocol_warning"]]
        lines += ["", "## Các lượt gọi", "", "| Vai trò | Model | Trạng thái | Giây | Input token | Output token |", "|---|---|---|---:|---:|---:|"]
        for entry in state["calls"]:
            lines.append(f"| {entry['role']} | {entry['model']} | {entry['status']} | {entry.get('seconds', '?')} | {entry.get('input_tokens', '?')} | {entry.get('output_tokens', '?')} |")
        write_private(self.directory / "report.md", "\n".join(lines) + "\n")
