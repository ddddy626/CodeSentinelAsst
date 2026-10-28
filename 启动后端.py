"""Double-click to start the local CodeSentinel API and review worker."""

import argparse
import ctypes
import json
import os
import socket
import subprocess
import sys
import time
from ctypes import wintypes
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse
from urllib.request import urlopen


ROOT = Path(__file__).resolve().parent
BACKEND = ROOT / "backend"
DATA = BACKEND / "data"
PYTHON = BACKEND / ".venv" / "Scripts" / "python.exe"
READY_URL = "http://127.0.0.1:8000/api/ready"


def load_settings() -> dict[str, str]:
    settings_file = ROOT / ".env"
    if not settings_file.is_file():
        raise RuntimeError("项目根目录缺少 .env 配置文件。")
    settings = os.environ.copy()
    for line in settings_file.read_text(encoding="utf-8").splitlines():
        if line.strip() and not line.lstrip().startswith("#") and "=" in line:
            key, value = line.split("=", 1)
            settings[key.strip()] = value.strip()
    database = settings.get("CODESENTINEL_DATABASE_URL", "")
    if not database.startswith("mysql://"):
        raise RuntimeError(".env 中的 CODESENTINEL_DATABASE_URL 没有指向 MySQL。")
    if not PYTHON.is_file():
        raise RuntimeError("缺少后端 Python 环境：backend/.venv/Scripts/python.exe。")
    return settings


def port_open(host: str, port: int) -> bool:
    try:
        with socket.create_connection((host, port), timeout=1):
            return True
    except OSError:
        return False


def pid_alive(pid_file: Path) -> bool:
    try:
        pid = int(pid_file.read_text(encoding="utf-8").strip())
    except (OSError, ValueError):
        return False
    if os.name != "nt":
        try:
            os.kill(pid, 0)
            return True
        except OSError:
            return False
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.OpenProcess.argtypes = (wintypes.DWORD, wintypes.BOOL, wintypes.DWORD)
    kernel.OpenProcess.restype = wintypes.HANDLE
    kernel.GetExitCodeProcess.argtypes = (wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD))
    kernel.CloseHandle.argtypes = (wintypes.HANDLE,)
    handle = kernel.OpenProcess(0x1000, False, pid)
    if not handle:
        return False
    try:
        exit_code = wintypes.DWORD()
        return bool(kernel.GetExitCodeProcess(handle, ctypes.byref(exit_code))) and exit_code.value == 259
    finally:
        kernel.CloseHandle(handle)


def api_ready() -> bool:
    try:
        with urlopen(READY_URL, timeout=2) as response:
            return response.status == 200 and json.load(response).get("status") == "ready"
    except (OSError, ValueError):
        return False


def launch(args: list[str], name: str, settings: dict[str, str]) -> None:
    DATA.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S-%f")
    stdout_path = DATA / f"{name}-mysql-{stamp}.stdout.log"
    stderr_path = DATA / f"{name}-mysql-{stamp}.stderr.log"
    flags = subprocess.CREATE_NO_WINDOW | subprocess.CREATE_NEW_PROCESS_GROUP if os.name == "nt" else 0
    with stdout_path.open("wb") as output, stderr_path.open("wb") as errors:
        process = subprocess.Popen([str(PYTHON), *args], cwd=BACKEND, env=settings,
                                   stdin=subprocess.DEVNULL, stdout=output, stderr=errors,
                                   creationflags=flags)
    (DATA / f"{name}.pid").write_text(str(process.pid), encoding="utf-8")


def start_backend() -> str:
    settings = load_settings()
    database = urlparse(settings["CODESENTINEL_DATABASE_URL"])
    redis = urlparse(settings.get("CODESENTINEL_REDIS_URL", "redis://127.0.0.1:6379/0"))
    if not port_open(database.hostname or "127.0.0.1", database.port or 3306):
        raise RuntimeError("MySQL 未连接，请先检查本机 3309 端口。")
    if not port_open(redis.hostname or "127.0.0.1", redis.port or 6379):
        raise RuntimeError("Redis 未连接，请先启动 Redis 服务。")

    running = api_ready()
    if not running and port_open("127.0.0.1", 8000):
        raise RuntimeError("8000 端口已被占用，但 API 尚未就绪；请先检查原有后端进程。")
    if not running:
        launch(["-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", "8000"], "api", settings)

    worker_running = pid_alive(DATA / "worker.pid")
    if not worker_running:
        launch(["-m", "app.worker"], "worker", settings)

    for _ in range(30):
        if api_ready() and pid_alive(DATA / "worker.pid"):
            return "后端已运行：API 与审查 Worker 均已就绪。\n网站：http://127.0.0.1:5173/\n接口：http://127.0.0.1:8000/docs"
        time.sleep(0.5)
    raise RuntimeError("启动超时。请查看 backend/data 中最新的 api-mysql 和 worker-mysql 错误日志。")


def show_message(message: str, error: bool) -> None:
    print(message, file=sys.stderr if error else sys.stdout)
    if os.name == "nt":
        ctypes.windll.user32.MessageBoxW(None, message, "CodeSentinel 后端", 0x10 if error else 0x40)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="启动 CodeSentinel 本地后端")
    parser.add_argument("--no-dialog", action="store_true", help="命令行使用时不显示提示窗口")
    options = parser.parse_args()
    try:
        result = start_backend()
        if options.no_dialog:
            print(result)
        else:
            show_message(result, False)
    except Exception as exc:
        message = f"启动失败：{exc}"
        if options.no_dialog:
            print(message, file=sys.stderr)
        else:
            show_message(message, True)
        raise SystemExit(1) from None
