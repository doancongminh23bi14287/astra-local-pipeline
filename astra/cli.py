import argparse
import json
import sys
from pathlib import Path

from .config import ROOT, AstraError, load_config
from .context import collect_context
from .engine import MODES, Pipeline, new_state
from .prompts import PORTABLE, protocol_bundle
from .providers import Client
from .session import add_note, create_session, handoff_text, read_session, record_run, session_path, snapshot


def configure_parser():
    parser = argparse.ArgumentParser(prog="astra", description="Workflow local: plan → draft → review → repair. Python standard library only.")
    commands = parser.add_subparsers(dest="command", required=True)
    run = commands.add_parser("run", help="Chạy một yêu cầu")
    run.add_argument("task", nargs="?")
    run.add_argument("--task-file", type=Path)
    run.add_argument("--context", action="append", default=[], help="File UTF-8; có thể lặp lại")
    run.add_argument("--mode", choices=MODES)
    run.add_argument("--runs-dir", type=Path, default=ROOT / "runs")
    run.add_argument("--config", type=Path)
    run.add_argument("--model", help="Đổi toàn bộ vai trò sang model Ollama này")
    run.add_argument("--session", help="Dùng mục tiêu/bộ nhớ/model cố định của phiên")
    run.add_argument("--sessions-dir", type=Path, default=ROOT / "sessions")
    resume = commands.add_parser("resume", help="Tiếp tục run bị ngắt/lỗi/hết budget")
    resume.add_argument("directory", type=Path)
    resume.add_argument("--max-calls", type=int)
    resume.add_argument("--max-seconds", type=int)
    for command in ("doctor", "models"):
        subcommand = commands.add_parser(command, help="Kiểm tra kết nối/model" if command == "doctor" else "Liệt kê model")
        subcommand.add_argument("--config", type=Path)
    commands.add_parser("prompt", help="In bộ hướng dẫn dùng cho AI khác")
    export = commands.add_parser("export", help="Xuất prompt + Ollama Modelfile")
    export.add_argument("--output", type=Path, required=True)
    export.add_argument("--model", default="qwen3:1.7b")
    session = commands.add_parser("session", help="Tạo và quản lý bộ nhớ xuyên nhiều lượt chạy")
    actions = session.add_subparsers(dest="action", required=True)
    create = actions.add_parser("create", help="Tạo mục tiêu/model/quy trình cố định")
    create.add_argument("name")
    create.add_argument("--goal", required=True)
    create.add_argument("--constraint", action="append", default=[])
    create.add_argument("--config", type=Path)
    create.add_argument("--mode", choices=MODES, default="balanced")
    create.add_argument("--sessions-dir", type=Path, default=ROOT / "sessions")
    show = actions.add_parser("show", help="Đọc gói bàn giao và bộ nhớ đã chốt")
    show.add_argument("name")
    show.add_argument("--sessions-dir", type=Path, default=ROOT / "sessions")
    note = actions.add_parser("note", help="Ghi dữ kiện/quyết định/việc tiếp theo do người dùng xác nhận")
    note.add_argument("name")
    note.add_argument("--kind", choices=("decision", "fact", "open", "next"), required=True)
    note.add_argument("--text", required=True)
    note.add_argument("--source", default="")
    note.add_argument("--supersedes", help="ID ghi chú cũ được thay thế; lịch sử vẫn được giữ")
    note.add_argument("--sessions-dir", type=Path, default=ROOT / "sessions")
    return parser


def run_task(args):
    memory = None
    protocol = None
    mode = args.mode or "balanced"
    if args.session:
        directory = session_path(args.session, args.sessions_dir)
        data = read_session(directory)
        if args.config or args.model or (args.mode and args.mode != data["mode"]):
            raise AstraError("Phiên đã cố định config/model/mode. Tạo phiên mới để đổi thay vì ghi đè trong run.")
        config, mode = data["config"], data["mode"]
        memory, protocol = snapshot(data, directory), data["protocol"]
    else:
        config = load_config(args.config)
    if args.model:
        config["providers"] = {"local": {"type": "ollama", "base_url": "http://127.0.0.1:11434"}}
        config["roles"] = {role: {"provider": "local", "model": args.model} for role in ("planner", "worker", "reviewer")}
    files = list(args.context)
    checks = {}
    if args.task_file:
        if args.task:
            raise AstraError("Chỉ chọn task trực tiếp hoặc --task-file.")
        document = json.loads(args.task_file.read_text(encoding="utf-8"))
        if not isinstance(document, dict) or not isinstance(document.get("task"), str):
            raise AstraError("Task file cần object với trường task dạng chuỗi.")
        unknown = set(document) - {"task", "context_files", "checks"}
        if unknown:
            raise AstraError(f"Task file có trường không hỗ trợ: {sorted(unknown)}")
        references = document.get("context_files", [])
        if not isinstance(references, list) or any(not isinstance(path, str) for path in references):
            raise AstraError("context_files phải là danh sách đường dẫn.")
        files.extend(str(args.task_file.resolve().parent / filename) for filename in references)
        task, checks = document["task"], document.get("checks", {})
    else:
        task = args.task
    if not task:
        raise AstraError('Dùng: astra run "Câu hỏi của bạn"')
    context = collect_context(task, files, config["limits"]["context_bytes"])
    state = new_state(task, config, mode, context, checks, memory, protocol)
    pipeline = Pipeline.create(args.runs_dir, state, progress=lambda message: print(message, file=sys.stderr, flush=True))
    return finish(pipeline)


def finish(pipeline):
    print(f"Run: {pipeline.directory}", file=sys.stderr, flush=True)
    state = pipeline.run()
    try:
        record_run(state, pipeline.directory)
    except (AstraError, OSError, ValueError) as error:
        print(f"Không cập nhật được HANDOFF của phiên: {error}. Run và báo cáo vẫn được giữ.", file=sys.stderr)
    if state["answer"]:
        print(state["answer"])
    print(f"\nTrạng thái: {state['status']} · {len(state['calls'])} lượt gọi · {state['elapsed_seconds']:.1f}s", file=sys.stderr)
    print(f"Báo cáo: {pipeline.directory / 'report.md'}", file=sys.stderr)
    if state["error"]:
        print(state["error"], file=sys.stderr)
    if state.get("legacy_protocol_warning"):
        print(state["legacy_protocol_warning"], file=sys.stderr)
    return {"model_review_passed": 0, "needs_review": 2, "budget_exhausted": 3, "interrupted": 130}.get(state["status"], 1)


def doctor(config, only_models=False):
    client = Client(config)
    healthy = True
    for name in sorted({spec["provider"] for spec in config["roles"].values()}):
        provider = config["providers"][name]
        print(f"{name}: {provider['base_url']}")
        try:
            names = client.models(name)
            if only_models:
                for model in names:
                    print("  " + model)
            else:
                expected = sorted({spec["model"] for spec in config["roles"].values() if spec["provider"] == name})
                for model in expected:
                    present = model in names or model + ":latest" in names
                    print(f"  {'OK' if present else 'MISSING'} {model}")
                    healthy = healthy and present
        except AstraError as error:
            print(f"  ERROR: {error}")
            healthy = False
    if not only_models:
        print("Chạy tuần tự; doctor chỉ kiểm tra kết nối/danh sách model, không tạo câu trả lời.")
    return 0 if healthy else 1


def main(argv=None):
    args = configure_parser().parse_args(argv)
    try:
        if args.command == "run":
            return run_task(args)
        if args.command == "session":
            if args.action == "create":
                directory = create_session(args.name, args.goal, args.constraint, load_config(args.config), protocol_bundle(), args.mode, args.sessions_dir)
                print(f"Đã tạo phiên: {args.name}\nBàn giao: {directory / 'HANDOFF.md'}")
            elif args.action == "note":
                note_id = add_note(args.name, args.kind, args.text, args.source, args.supersedes, args.sessions_dir)
                print(f"Đã ghi {note_id}; lượt chạy mới sẽ nạp ghi chú này. Run đang chạy/resume giữ snapshot cũ.")
            else:
                directory = session_path(args.name, args.sessions_dir)
                print(handoff_text(read_session(directory), directory))
            return 0
        if args.command == "resume":
            pipeline = Pipeline.load(args.directory, progress=lambda message: print(message, file=sys.stderr, flush=True))
            for key in ("max_calls", "max_seconds"):
                value = getattr(args, key)
                if value is not None:
                    if value < pipeline.state["config"]["limits"][key]:
                        raise AstraError("Khi resume, chỉ tăng giới hạn tổng; không reset số lượt đã dùng.")
                    pipeline.state["config"]["limits"][key] = value
            return finish(pipeline)
        if args.command in ("doctor", "models"):
            return doctor(load_config(args.config), args.command == "models")
        if args.command == "prompt":
            print(PORTABLE)
            return 0
        if not args.model or any(character.isspace() for character in args.model) or '"' in args.model:
            raise AstraError("Tên model không hợp lệ.")
        target = args.output.expanduser()
        target.mkdir(parents=True, exist_ok=True)
        paths = [target / "AGENT_INSTRUCTIONS.md", target / "Modelfile"]
        if any(path.exists() for path in paths):
            raise AstraError("File export đã tồn tại; chọn thư mục mới để giữ bản cũ.")
        contents = [PORTABLE, f'FROM {args.model}\nPARAMETER num_ctx 4096\nPARAMETER temperature 0.2\nSYSTEM """\n{PORTABLE}\n"""\n']
        for path, content in zip(paths, contents):
            with path.open("x", encoding="utf-8") as stream:
                stream.write(content)
        print(f"Đã xuất: {target.resolve()}")
        print("Modelfile chỉ gắn system prompt; dùng astra run để chạy workflow nhiều lượt thực sự.")
        return 0
    except (AstraError, OSError, ValueError) as error:
        print(f"Lỗi: {error}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        return 130
