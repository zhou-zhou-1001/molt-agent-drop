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
            "exit 1",
        ):
            self.assertIn(required, script)

    def test_documented_windows_launcher_is_one_line_without_placeholders(self):
        launchers = []
        for name in ("README.md", "docs/demo-cross-machine.md"):
            text = (ROOT / name).read_text(encoding="utf-8")
            launchers.extend(re.findall(r"```powershell\n(powershell\.exe[^\n]+)\n```", text))
        self.assertGreaterEqual(len(launchers), 2)
        for launcher in launchers:
            self.assertIn("raw.githubusercontent.com", launcher)
            self.assertIn("-Command '$ErrorActionPreference=", launcher)
            self.assertNotRegex(launcher, r"<[^>]+>")
            self.assertNotIn("`", launcher)

    def test_agent_uses_bootstrapped_python(self):
        script = (ROOT / "molt.ps1").read_text(encoding="ascii")
        self.assertIn("& $python $client", script)
        self.assertNotIn("Agent requires Python 3", script)


if __name__ == "__main__":
    unittest.main(verbosity=2)
