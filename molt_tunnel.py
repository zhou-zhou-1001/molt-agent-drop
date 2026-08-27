#!/usr/bin/env python3
"""Supervise Molt's two-hop OpenSSH tunnel without storing credentials."""
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.request
from pathlib import Path

FATAL_SSH_ERRORS = (
    "host key verification failed", "remote host identification has changed",
    "permission denied", "too many authentication failures", "no matching host key type",
    "authentication failed", "no supported authentication methods available",
    "bad permissions", "identity file", "could not resolve hostname",
)
FINGERPRINT_RE = re.compile(r"^SHA256:[A-Za-z0-9+/]{43}$")


def _port(value: object, name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or not 1 <= value <= 65535:
        raise ValueError(f"{name} must be an integer from 1 to 65535")
    return value


def load_config(path: str | Path) -> dict:
    config_path = Path(path).expanduser().resolve()
    try:
        config = json.loads(config_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"cannot read valid JSON config: {exc}") from exc
    allowed = {"mode", "relay_host", "relay_user", "relay_ssh_port", "known_hosts",
               "host_key_fingerprint", "identity_file", "host_port", "relay_port",
               "agent_port", "reconnect_delay", "health_timeout"}
    unknown = set(config) - allowed
    if unknown:
        raise ValueError("unknown config fields: " + ", ".join(sorted(unknown)))
    required = {"mode", "relay_host", "relay_user", "known_hosts", "host_key_fingerprint"}
    missing = required - set(config)
    if missing:
        raise ValueError("missing config fields: " + ", ".join(sorted(missing)))
    if config["mode"] not in ("host-reverse", "agent-local"):
        raise ValueError("mode must be host-reverse or agent-local")
    for name in ("relay_host", "relay_user"):
        value = config[name]
        if not isinstance(value, str) or not value or any(c.isspace() for c in value) or value.startswith("-"):
            raise ValueError(f"{name} is invalid")
    if any(c in config["relay_host"] for c in "@/\\") or any(c in config["relay_user"] for c in "@/\\"):
        raise ValueError("relay_host and relay_user must be separate plain SSH destination fields")
    fingerprint = config["host_key_fingerprint"]
    if not isinstance(fingerprint, str) or not FINGERPRINT_RE.fullmatch(fingerprint):
        raise ValueError("host_key_fingerprint must be a complete SHA256 fingerprint")
    if not isinstance(config["known_hosts"], str) or not config["known_hosts"]:
        raise ValueError("known_hosts must be a non-empty path")
    known_hosts = (config_path.parent / config["known_hosts"]).resolve() if not Path(config["known_hosts"]).is_absolute() else Path(config["known_hosts"]).resolve()
    if not known_hosts.is_file() or known_hosts.is_symlink():
        raise ValueError("known_hosts must be an existing regular, non-symlink file")
    config["known_hosts"] = str(known_hosts)
    if config.get("identity_file"):
        if not isinstance(config["identity_file"], str):
            raise ValueError("identity_file must be a path")
        identity = (config_path.parent / config["identity_file"]).resolve() if not Path(config["identity_file"]).is_absolute() else Path(config["identity_file"]).resolve()
        if not identity.is_file() or identity.is_symlink():
            raise ValueError("identity_file must be an existing regular, non-symlink file")
        config["identity_file"] = str(identity)
    for name, default in (("relay_ssh_port", 22), ("host_port", 8765), ("relay_port", 18765), ("agent_port", 18765)):
        config[name] = _port(config.get(name, default), name)
    for name, default in (("reconnect_delay", 5), ("health_timeout", 15)):
        value = config.get(name, default)
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not 0 < value <= 300:
            raise ValueError(f"{name} must be greater than 0 and at most 300 seconds")
        config[name] = float(value)
    return config


def verify_host_fingerprint(config: dict, runner=subprocess.run) -> None:
    keygen = shutil.which("ssh-keygen")
    if not keygen:
        raise RuntimeError("ssh-keygen was not found; install/enable OpenSSH client")
    lookup = config["relay_host"] if config["relay_ssh_port"] == 22 else f"[{config['relay_host']}]:{config['relay_ssh_port']}"
    matches = runner([keygen, "-F", lookup, "-f", config["known_hosts"]],
                     capture_output=True, text=True, timeout=10)
    if matches.returncode or not matches.stdout.strip():
        raise RuntimeError("relay host has no matching entry in known_hosts")
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", delete=False) as selected:
        selected.write(matches.stdout)
        selected_path = selected.name
    try:
        result = runner([keygen, "-lf", selected_path, "-E", "sha256"],
                        capture_output=True, text=True, timeout=10)
    finally:
        try:
            os.unlink(selected_path)
        except OSError:
            pass
    if result.returncode:
        raise RuntimeError("ssh-keygen could not inspect known_hosts: " + result.stderr.strip())
    found = {part for line in result.stdout.splitlines() for part in line.split() if part.startswith("SHA256:")}
    if config["host_key_fingerprint"] not in found:
        raise RuntimeError("verified relay fingerprint is not present in known_hosts")


def build_ssh_command(config: dict, ssh: str = "ssh") -> list[str]:
    common = [ssh, "-N", "-T", "-p", str(config["relay_ssh_port"]),
              "-o", "BatchMode=yes", "-o", "ExitOnForwardFailure=yes",
              "-o", "StrictHostKeyChecking=yes", "-o", "ServerAliveInterval=15",
              "-o", "ServerAliveCountMax=3", "-o", "ConnectTimeout=15",
              "-o", "GatewayPorts=no",
              "-o", "UserKnownHostsFile=" + config["known_hosts"]]
    if config.get("identity_file"):
        common += ["-i", config["identity_file"], "-o", "IdentitiesOnly=yes"]
    if config["mode"] == "host-reverse":
        forwarding = f"127.0.0.1:{config['relay_port']}:127.0.0.1:{config['host_port']}"
        common += ["-R", forwarding]
    else:
        forwarding = f"127.0.0.1:{config['agent_port']}:127.0.0.1:{config['relay_port']}"
        common += ["-L", forwarding]
    return common + [config["relay_user"] + "@" + config["relay_host"]]


def health_ok(port: int, timeout: float = 2) -> bool:
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/health", timeout=timeout) as response:
            value = json.load(response)
            return response.status == 200 and value.get("ok") is True
    except Exception:
        return False


def is_fatal_ssh_error(stderr: str) -> bool:
    lowered = stderr.lower()
    return any(message in lowered for message in FATAL_SSH_ERRORS)


def supervise(config: dict, popen=subprocess.Popen, sleep=time.sleep) -> int:
    ssh = shutil.which("ssh")
    if not ssh:
        raise RuntimeError("ssh was not found; install/enable OpenSSH client")
    local_health_port = config["host_port"] if config["mode"] == "host-reverse" else config["agent_port"]
    if config["mode"] == "host-reverse" and not health_ok(local_health_port):
        raise RuntimeError("Molt Host health check failed; start Host before its tunnel")
    command = build_ssh_command(config, ssh)
    while True:
        print(f"Starting {config['mode']} tunnel; credentials are handled by OpenSSH/ssh-agent.", flush=True)
        proc = popen(command, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True)
        healthy = config["mode"] == "host-reverse"
        deadline = time.monotonic() + config["health_timeout"]
        while proc.poll() is None:
            if config["mode"] == "agent-local" and health_ok(local_health_port):
                if not healthy:
                    print(f"Tunnel healthy: http://127.0.0.1:{local_health_port}/health", flush=True)
                healthy = True
            if not healthy and time.monotonic() >= deadline:
                proc.terminate()
                proc.wait(timeout=5)
                raise RuntimeError("tunnel started but Molt health check did not succeed")
            sleep(1)
        stderr = proc.stderr.read() if proc.stderr else ""
        if is_fatal_ssh_error(stderr):
            print(stderr.strip(), file=sys.stderr)
            raise RuntimeError("SSH host-key, configuration, or authentication failure; not retrying")
        print(f"SSH tunnel exited ({proc.returncode}); reconnecting in {config['reconnect_delay']:g}s.", file=sys.stderr)
        sleep(config["reconnect_delay"])


def main() -> int:
    parser = argparse.ArgumentParser(description="Start and supervise a verified Molt SSH relay tunnel")
    parser.add_argument("config", help="JSON config path (contains no passwords)")
    parser.add_argument("--check", action="store_true", help="validate config, fingerprint, and print the SSH argv")
    args = parser.parse_args()
    try:
        config = load_config(args.config)
        verify_host_fingerprint(config)
        if args.check:
            print(json.dumps(build_ssh_command(config), ensure_ascii=False))
            return 0
        return supervise(config)
    except (ValueError, RuntimeError, OSError) as exc:
        print("Molt tunnel error: " + str(exc), file=sys.stderr)
        return 2
    except KeyboardInterrupt:
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
