"""The documentation: its Python examples run, and the docstrings agree."""

import inspect
import re
from pathlib import Path

import pytest

import stellar_xdr as xdr

ROOT = Path(__file__).parent.parent
PAGES = [ROOT / "README.md", *sorted((ROOT / "docs").glob("*.md"))]
EXAMPLE = re.compile(r"^```python\n(.*?)^```$", re.DOTALL | re.MULTILINE)


@pytest.mark.parametrize("page", PAGES, ids=lambda page: page.name)
def test_examples_run(page: Path) -> None:
    examples = EXAMPLE.findall(page.read_text(encoding="utf-8"))
    for example in examples:
        exec(example, {})  # noqa: S102


@pytest.mark.parametrize(
    "method", ["from_xdr_bytes", "from_xdr_base64", "from_json_value"]
)
def test_unions_document_decoding_as_structs_do(method: str) -> None:
    # A struct inherits these methods and a union has generated ones, so their
    # docstrings are written in two places.
    documented = inspect.getdoc(getattr(xdr.UInt128Parts, method))
    assert documented
    assert inspect.getdoc(getattr(xdr.SCVal, method)) == documented
