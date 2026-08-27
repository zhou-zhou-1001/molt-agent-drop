import json
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import molt_tunnel


FINGERPRINT = "SHA256:" + "A" * 43


class TunnelTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.base = Path(self.tmp.name)
        self.known = self.base / "known_hosts"
        self.known.write_text("relay ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAITest\n", encoding="ascii")

    def tearDown(self):
        self.tmp.cleanup()

    def config(self, mode="host-reverse", **extra):
        value = {"mode": mode, "relay_host": "relay.example", "relay_user": "molt",
                 "known_hosts": "known_hosts", "host_key_fingerprint": FINGERPRINT}
        value.update(extra)
        path = self.base / "tunnel.json"
        path.write_text(json.dumps(value), encoding="utf-8")
        return molt_tunnel.load_config(path)

    def test_reverse_command_has_loopback_and_required_security_options(self):
        command = molt_tunnel.build_ssh_command(self.config())
        joined = " ".join(command)
        self.assertIn("127.0.0.1:18765:127.0.0.1:8765", command)
        for option in ("StrictHostKeyChecking=yes", "ExitOnForwardFailure=yes",
                       "ServerAliveInterval=15", "ServerAliveCountMax=3", "BatchMode=yes",
                       "GatewayPorts=no"):
            self.assertIn(option, command)
        self.assertNotIn("StrictHostKeyChecking=no", joined)
        self.assertNotIn("0.0.0.0", joined)

    def test_local_command_forwards_only_loopback(self):
        command = molt_tunnel.build_ssh_command(self.config("agent-local", agent_port=28765))
        self.assertIn("-L", command)
        self.assertIn("127.0.0.1:28765:127.0.0.1:18765", command)

    def test_config_rejects_unknown_fields_bad_ports_and_destination_injection(self):
        for change in ({"surprise": True}, {"relay_port": 0}, {"relay_host": "-oProxyCommand=x"},
                       {"relay_user": "user@other"}, {"host_key_fingerprint": "SHA256:short"}):
            with self.subTest(change=change):
                value = {"mode": "host-reverse", "relay_host": "relay.example", "relay_user": "molt",
                         "known_hosts": "known_hosts", "host_key_fingerprint": FINGERPRINT}
                value.update(change)
                path = self.base / "bad.json"
                path.write_text(json.dumps(value), encoding="utf-8")
                with self.assertRaises(ValueError):
                    molt_tunnel.load_config(path)

    def test_fingerprint_must_be_present_in_known_hosts(self):
        calls = iter((
            subprocess.CompletedProcess([], 0, stdout="relay ssh-ed25519 AAAATest\n", stderr=""),
            subprocess.CompletedProcess([], 0, stdout="256 SHA256:" + "B" * 43 + " relay (ED25519)\n", stderr=""),
        ))
        with self.assertRaises(RuntimeError):
            molt_tunnel.verify_host_fingerprint(self.config(), runner=lambda *a, **k: next(calls))

    def test_auth_and_host_key_errors_are_fatal(self):
        for message in ("Permission denied (publickey).", "Host key verification failed.",
                        "REMOTE HOST IDENTIFICATION HAS CHANGED!"):
            self.assertTrue(molt_tunnel.is_fatal_ssh_error(message))
        self.assertFalse(molt_tunnel.is_fatal_ssh_error("Connection timed out"))

    def test_transient_exit_reaches_reconnect_delay(self):
        class Process:
            returncode = 255
            stderr = mock.Mock(read=mock.Mock(return_value="Connection timed out"))
            def poll(self): return self.returncode
        delays = []
        def stop_after_delay(seconds):
            delays.append(seconds)
            raise KeyboardInterrupt
        with mock.patch("molt_tunnel.shutil.which", return_value="ssh"):
            with self.assertRaises(KeyboardInterrupt):
                molt_tunnel.supervise(self.config("agent-local", reconnect_delay=3),
                                      popen=lambda *a, **k: Process(), sleep=stop_after_delay)
        self.assertEqual([3.0], delays)

    def test_host_tunnel_requires_local_health(self):
        with mock.patch("molt_tunnel.shutil.which", return_value="ssh"), \
             mock.patch("molt_tunnel.health_ok", return_value=False):
            with self.assertRaisesRegex(RuntimeError, "health check failed"):
                molt_tunnel.supervise(self.config(), popen=mock.Mock())


if __name__ == "__main__":
    unittest.main(verbosity=2)
