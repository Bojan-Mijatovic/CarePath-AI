"""Every acceptance criterion of SPEC §11 has its test file in testing/ (delivery plan step 1.7)."""

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SPEC = (ROOT / "spec" / "SPEC.md").read_text(encoding="utf-8")
ROWS = re.findall(r"^\| AC(\d+) \|.*?`(test_ac\d+_\w+\.py)`", SPEC, re.M)


def test_spec_lists_ac1_to_ac19_once():
    assert sorted(int(n) for n, _ in ROWS) == list(range(1, 20))


def test_each_ac_has_its_test_file_with_the_acceptance_marker():
    for n, name in ROWS:
        path = ROOT / "testing" / name
        assert path.exists(), f"AC{n}: {name} missing"
        source = path.read_text(encoding="utf-8")
        assert "@pytest.mark.acceptance" in source, name
        assert f"AC{n}" in source, name
