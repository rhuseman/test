import os
import shutil
import subprocess
import unittest

WEB = os.path.join(os.path.dirname(os.path.abspath(__file__)), "web")


@unittest.skipIf(shutil.which("node") is None, "node not installed")
class WebPortMatchesPython(unittest.TestCase):
    def test_golden_cases(self):
        # Regenerate from the current Python code, then check the JS port.
        subprocess.run(["python3", os.path.join(WEB, "make_golden.py")],
                       check=True, capture_output=True)
        r = subprocess.run(["node", "check_golden.js"], cwd=WEB,
                           capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stdout[-2000:] + r.stderr)


if __name__ == "__main__":
    unittest.main()
