"""Check that Alembic migrations have exactly one head and no duplicate revision IDs."""

import re
import sys
from pathlib import Path

VERSIONS_DIR = Path(__file__).resolve().parent.parent / "migrations" / "versions"

REV_RE = re.compile(r'^revision:\s*str\s*=\s*"(.+?)"', re.MULTILINE)
DOWN_RE = re.compile(r'^down_revision:\s*str\s*\|\s*None\s*=\s*"(.+?)"', re.MULTILINE)


def main() -> int:
    revisions: dict[str, str] = {}
    down_refs: set[str] = set()
    errors = 0

    for path in sorted(VERSIONS_DIR.glob("*.py")):
        content = path.read_text()
        rev_match = REV_RE.search(content)
        down_match = DOWN_RE.search(content)

        if not rev_match:
            continue

        rev_id = rev_match.group(1)

        if rev_id in revisions:
            print(
                f"FAIL: Duplicate revision ID '{rev_id}' "
                f"in {path.name} and {Path(revisions[rev_id]).name}"
            )
            errors += 1

        revisions[rev_id] = str(path)

        if down_match:
            down_refs.add(down_match.group(1))

    heads = set(revisions.keys()) - down_refs

    if len(heads) == 0:
        print("FAIL: No migration heads found (circular dependency?)")
        errors += 1
    elif len(heads) > 1:
        print(f"FAIL: Multiple migration heads found: {heads}")
        for h in heads:
            print(f"  {h} -> {Path(revisions[h]).name}")
        errors += 1
    else:
        print(f"OK: Single migration head: {heads.pop()}")

    if errors:
        print(f"\n{errors} error(s) found. Merge the migration heads before deploying.")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
