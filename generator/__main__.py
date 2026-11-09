"""Generate the package, or check that the committed code is up to date.

Usage:
    python -m generator          write the generated modules
    python -m generator --check  fail if regenerating would change any file
"""

import argparse
import subprocess
import sys
import tomllib
from pathlib import Path

from .emit import Generator, StrategyGenerator
from .model import load

ROOT = Path(__file__).resolve().parent.parent
PACKAGE = ROOT / "src" / "stellar_xdr"


def _ruff(path: Path, source: str, *args: str) -> str:
    result = subprocess.run(  # noqa: S603 - runs ruff from this environment
        [sys.executable, "-m", "ruff", *args, "--stdin-filename", str(path), "-"],
        input=source,
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        sys.exit(f"ruff {args[0]} failed for {path}:\n{result.stderr}")
    return result.stdout


def _format(path: Path, source: str) -> str:
    # The imports are sorted by ruff rather than by the generator, so that they follow
    # exactly the rules the lint check applies.
    sorted_imports = _ruff(path, source, "check", "--select", "I", "--fix", "--quiet")
    return _ruff(path, sorted_imports, "format")


def main() -> None:
    """Parse the command line and generate."""
    parser = argparse.ArgumentParser(description="Generate stellar_xdr from xdr.json.")
    parser.add_argument("--check", action="store_true", help="only check")
    args = parser.parse_args()
    model = load(ROOT / "xdr" / "xdr.json")
    protocol: int = tomllib.loads((ROOT / "xdr" / "source.toml").read_text())[
        "protocol"
    ]
    generator = Generator(model, protocol)
    sources = {PACKAGE / p: s for p, s in generator.sources().items()}
    sources[ROOT / "tests" / "strategies.py"] = StrategyGenerator(model).source()
    sources[ROOT / "generator" / "arm_names.txt"] = generator.arm_names()
    stale: list[str] = []
    for path, source in sources.items():
        formatted = _format(path, source) if path.suffix == ".py" else source
        if args.check:
            if not path.exists() or path.read_text() != formatted:
                stale.append(str(path.relative_to(ROOT)))
        else:
            path.write_text(formatted)
    if stale:
        sys.exit("out of date, run `make generate`:\n  " + "\n  ".join(stale))


if __name__ == "__main__":
    main()
