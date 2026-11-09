"""Every Python example in the documentation has to run."""

import re
from pathlib import Path

import pytest

ROOT = Path(__file__).parent.parent
PAGES = [ROOT / "README.md", *sorted((ROOT / "docs").glob("*.md"))]
EXAMPLE = re.compile(r"^```python\n(.*?)^```$", re.DOTALL | re.MULTILINE)


@pytest.mark.parametrize("page", PAGES, ids=lambda page: page.name)
def test_examples_run(page: Path) -> None:
    examples = EXAMPLE.findall(page.read_text(encoding="utf-8"))
    for example in examples:
        exec(example, {})  # noqa: S102
