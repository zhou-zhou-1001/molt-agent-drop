import re
import unittest
from pathlib import Path

from check_powershell import FILES, check


ROOT = Path(__file__).resolve().parent


class WindowsOnboardingTests(unittest.TestCase):
    def test_powershell_entry_files_are_ascii_and_lexically_balanced(self):
        for name in FILES:
            self.assertEqual([], check(ROOT / name), name)

    def test_bootstrap_has_fail_closed_source_guards(self):
        script = (ROOT / "bootstrap.ps1").read_text(encoding="ascii")
        for required in (
            "Tls12",
            "StatusCode -ne 200",
            "ContentLength",
            "minimumZipBytes",
            "Validate-Zip",
            ".staging-",
            ".molt-source.json",
            "^[0-9a-f]{40}$",
            "commit API unavailable",
            "return $repoRef",
            "Join-Path $installDir 'molt.ps1'",
            "throw",
        ):
            self.assertIn(required, script)
        self.assertNotIn("$PSScriptRoot", script)
        self.assertNotRegex(script, r"(?m)^\s*exit\b")

    def test_documented_windows_launcher_is_one_line_without_placeholders(self):
        launchers = []
        for name in ("README.md", "docs/demo-cross-machine.md"):
            text = (ROOT / name).read_text(encoding="utf-8")
            launchers.extend(
                line
                for line in re.findall(r"```powershell\n([^\n]+)\n```", text)
                if "cdn.jsdelivr.net/gh/zhou-zhou-1001/molt-agent-drop@main/bootstrap.ps1" in line
            )
        self.assertGreaterEqual(len(launchers), 2)
        for launcher in launchers:
            self.assertLess(launcher.index("cdn.jsdelivr.net"), launcher.index("raw.githubusercontent.com"))
            self.assertNotIn("powershell.exe", launcher.lower())
            self.assertIn('$ErrorActionPreference="Stop"', launcher)
            self.assertIn("Tls12", launcher)
            self.assertIn("HttpWebRequest", launcher)
            self.assertIn("Timeout=30000", launcher)
            self.assertIn("raw.githubusercontent.com", launcher)
            self.assertIn("github.com/zhou-zhou-1001/molt-agent-drop/raw", launcher)
            self.assertIn("codeload.github.com/zhou-zhou-1001/molt-agent-drop/zip/main", launcher)
            self.assertIn("System.IO.Compression.FileSystem", launcher)
            self.assertIn("ZipFile", launcher)
            self.assertIn("$s.Length -lt 1000", launcher)
            self.assertIn(r'[^\x00-\x7F]', launcher)
            self.assertIn("[ScriptBlock]::Create($s)", launcher)
            self.assertNotRegex(launcher, r"(?i)\biex\b|Invoke-Expression")
            self.assertNotIn("ExecutionPolicy", launcher)
            self.assertNotRegex(launcher, r"<[^>]+>")
            self.assertNotIn("`", launcher)

    def test_agent_uses_bootstrapped_python(self):
        script = (ROOT / "molt.ps1").read_text(encoding="ascii")
        self.assertIn("& $python $client", script)
        self.assertNotIn("Agent requires Python 3", script)

    def test_diagnostics_are_explicitly_opt_in_at_all_host_entries(self):
        ps = (ROOT / "molt.ps1").read_text(encoding="ascii")
        runner = (ROOT / "run_drop_host.ps1").read_text(encoding="ascii")
        wizard = (ROOT / "molt_wizard.py").read_text(encoding="utf-8")
        self.assertIn("[switch]$EnableDiagnostics", ps)
        self.assertIn("EnableDiagnostics", ps)
        self.assertIn("[switch]$EnableDiagnostics", runner)
        self.assertIn("--enable-diagnostics", runner)
        self.assertIn('p.add_argument("--enable-diagnostics", action="store_true")', wizard)
        self.assertIn('command.append("--enable-diagnostics")', wizard)


if __name__ == "__main__":
    unittest.main(verbosity=2)
