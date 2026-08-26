#!/usr/bin/env python3
"""Cross-platform first-run wizard for the Molt Drop demo."""
from __future__ import annotations
import argparse, os, shutil, subprocess, sys
from pathlib import Path

HERE = Path(__file__).resolve().parent

def ask(prompt: str, default: str = "") -> str:
    suffix = f" [{default}]" if default else ""
    value = input(f"{prompt}{suffix}: ").strip()
    return value or default

def header(text: str) -> None:
    print("\n" + "=" * 64 + f"\n  {text}\n" + "=" * 64)

def run_host(args: argparse.Namespace) -> int:
    header("Host 设置")
    root = args.root or ask("专用共享目录（不要填桌面、用户目录或真实业务目录）", str(Path.home() / "MoltDemoShare"))
    state = args.state_dir or ask("私有状态目录（审计日志放这里）", str(Path.home() / ".molt-drop"))
    print(f"共享目录: {root}\n状态目录: {state}")
    if ask("确认创建/使用这个专用共享目录并启动 Host？输入 yes", "no") != "yes":
        print("已取消。")
        return 0
    header("Host 启动")
    python = shutil.which("python3") or shutil.which("python")
    if not python:
        print("未找到 Python 3。请安装 Python 3 后重新运行。", file=sys.stderr)
        return 1
    command = [python, str(HERE / "drop_host.py"), "--root", root,
                            "--create-root", "--state-dir", state,
                            "--port", str(args.port)]
    if args.enable_diagnostics:
        command.append("--enable-diagnostics")
    return subprocess.call(command)

def run_agent(args: argparse.Namespace) -> int:
    header("Agent 设置")
    print("请先确认 Host 管理员提供的 SSH host-key 指纹。不要跳过校验。")
    url = args.url or ask("Tunnel 建立后，Agent 访问地址", "http://127.0.0.1:18765")
    invitation_id = args.invitation_id or ask("Host 屏幕上的 MOLT_INVITATION_ID")
    secret = args.invitation_secret or ask("Host 屏幕上的 MOLT_INVITATION_SECRET")
    label = args.label or ask("给这次 Agent 取个名字", "my-agent")
    if not invitation_id or not secret:
        print("Invitation ID/SECRET 不能为空。", file=sys.stderr)
        return 1
    python = shutil.which("python3") or shutil.which("python")
    if not python:
        print("Agent 端需要 Python 3。", file=sys.stderr)
        return 1
    header("开始配对")
    print("Host 屏幕会显示 request id；必须由 Host Owner 明确批准。")
    return subprocess.call([python, str(HERE / "drop_client.py"), "--url", url, "pair",
                            "--invitation-id", invitation_id,
                            "--invitation-secret", secret, "--label", label])

def main() -> int:
    p = argparse.ArgumentParser(description="Molt Drop first-run wizard")
    p.add_argument("--role", choices=("host", "agent"))
    p.add_argument("--root", default="")
    p.add_argument("--state-dir", default="")
    p.add_argument("--port", type=int, default=8765)
    p.add_argument("--enable-diagnostics", action="store_true")
    p.add_argument("--url", default="")
    p.add_argument("--invitation-id", default="")
    p.add_argument("--invitation-secret", default="")
    p.add_argument("--label", default="")
    args = p.parse_args()
    print("Molt Drop · 临时授权、可审计、用完即走")
    print("安全 Demo：不会开放公网端口、关闭防火墙或跳过 SSH host-key 校验。")
    role = args.role or ask("你现在是哪一端？输入 host（文件所在电脑）或 agent（运行 Agent 的电脑）")
    if role not in ("host", "agent"):
        print("请输入 host 或 agent。", file=sys.stderr)
        return 2
    return run_host(args) if role == "host" else run_agent(args)

if __name__ == "__main__":
    raise SystemExit(main())
