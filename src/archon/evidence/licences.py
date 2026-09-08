"""Read the licence of everything installed, rather than believing a list.

    python -m archon.evidence.licences

`docs/THIRD-PARTY.md` is a table a person wrote, and a table a person wrote is a
table that goes stale the first time a dependency moves. This prints what is
actually installed, and a test compares the two, so the document is wrong loudly
rather than quietly.
"""

from __future__ import annotations

import importlib.metadata as metadata
from dataclasses import dataclass

#: Everything this project declares, runtime first. Kept here rather than parsed
#: out of pyproject so that adding a dependency without listing it is a failure.
RUNTIME = ("strands-agents", "boto3", "fastapi", "uvicorn", "python-multipart", "pypdf")
DEVELOPMENT = ("pytest", "pytest-cov", "ruff")

#: Licences this project can ship under MIT without anyone having to think about
#: it. Anything outside this set should stop a build rather than surprise a judge.
PERMISSIVE = {"MIT", "MIT License", "Apache-2.0", "BSD-3-Clause", "BSD License", "Apache 2.0"}


@dataclass(frozen=True, slots=True)
class Package:
    name: str
    version: str
    licence: str

    @property
    def permissive(self) -> bool:
        return self.licence in PERMISSIVE


def _licence_of(md) -> str:
    """The licence, from whichever field the package chose to use.

    Packaging metadata offers three places for this and projects disagree about
    which to fill, so all three are read before giving up.
    """
    explicit = md.get("License-Expression") or md.get("License")
    if explicit and len(explicit) < 40:
        return explicit.strip()
    for classifier in md.get_all("Classifier") or []:
        if classifier.startswith("License ::"):
            return classifier.split("::")[-1].strip()
    return "unknown"


def read(names: tuple[str, ...]) -> list[Package]:
    found = []
    for name in names:
        try:
            md = metadata.metadata(name)
        except metadata.PackageNotFoundError:
            found.append(Package(name, "not installed", "unknown"))
            continue
        found.append(Package(name, md.get("Version", "?"), _licence_of(md)))
    return found


def report() -> str:
    lines = ["installed dependencies and the licence each declares", ""]
    for heading, names in (("runtime", RUNTIME), ("development only", DEVELOPMENT)):
        lines.append(f"  {heading}")
        for package in read(names):
            flag = "" if package.permissive else "   <-- not on the permissive list"
            lines.append(f"    {package.name:<20} {package.version:<10} {package.licence}{flag}")
        lines.append("")
    lines.append("Read from the installed packages, not from a document.")
    return "\n".join(lines)


if __name__ == "__main__":  # pragma: no cover
    print(report())
