"""Step 4.3: the hash list of what the demo reads from disk, to copy to the backup laptop and check there.

    uv run python testing/cache_hashes.py           # write demo/SHA256SUMS on the demo machine
    uv run python testing/cache_hashes.py --check   # on the backup laptop, after copying demo/

It covers the LLM cache (demo/cache/, D14) and the what-if grids (demo/whatif/, D48): the two things the demo
cannot rebuild in front of an audience. The check lists every file that is missing, different or extra, and
exits 1 if any is; then run `uv run pytest -m demo` there too (SPEC §8).
"""

import hashlib
import sys
from pathlib import Path

DEMO = Path(__file__).resolve().parents[1] / "demo"
SUMS = DEMO / "SHA256SUMS"
COVERED = ("cache", "whatif")


def hashes() -> dict[str, str]:
    """{path under demo/, posix: sha256} of every covered file, over its text with LF line ends: git on the team
    laptops checks text files out with CRLF (core.autocrlf), so the same commit gives other bytes on another
    clone, and the JSON reads the same."""
    files = sorted(p for d in COVERED for p in (DEMO / d).rglob("*") if p.is_file())
    return {p.relative_to(DEMO).as_posix(): hashlib.sha256(p.read_bytes().replace(b"\r\n", b"\n")).hexdigest()
            for p in files}


def main(argv: list[str]) -> int:
    now = hashes()
    if "--check" not in argv:
        SUMS.write_text("".join(f"{h}  {p}\n" for p, h in now.items()), encoding="utf-8", newline="\n")
        print(f"{len(now)} files -> {SUMS}")
        return 0
    expected = dict(reversed(line.split("  ", 1)) for line in SUMS.read_text(encoding="utf-8").splitlines())
    missing = sorted(set(expected) - set(now))
    extra = sorted(set(now) - set(expected))
    changed = sorted(p for p in set(expected) & set(now) if expected[p] != now[p])
    for label, paths in (("missing", missing), ("different", changed), ("extra", extra)):
        for p in paths:
            print(f"{label}: {p}")
    print(f"{len(now)} files checked: {len(missing)} missing, {len(changed)} different, {len(extra)} extra")
    return 1 if missing or changed or extra else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
