"""P4 asks for authorisation for every third-party component.

A hand-written table answers it once and then goes stale. These compare the
document to what is installed, so it is wrong loudly instead of quietly.
"""

from __future__ import annotations

import pathlib
import re

from archon.evidence import licences

DOC = (pathlib.Path(__file__).resolve().parents[1] / "docs" / "THIRD-PARTY.md").read_text(
    encoding="utf-8"
)


def test_every_declared_dependency_is_installed_and_readable():
    for package in licences.read(licences.RUNTIME + licences.DEVELOPMENT):
        assert package.version != "not installed", package.name
        assert package.licence != "unknown", package.name


def test_nothing_ships_under_a_licence_that_would_need_thinking_about():
    for package in licences.read(licences.RUNTIME):
        assert package.permissive, f"{package.name} declares {package.licence}"


def test_the_document_names_every_dependency_the_code_declares():
    for name in licences.RUNTIME + licences.DEVELOPMENT:
        assert f"`{name}`" in DOC, name


def test_the_document_quotes_the_licence_each_package_actually_declares():
    for package in licences.read(licences.RUNTIME + licences.DEVELOPMENT):
        row = next((line for line in DOC.splitlines() if f"`{package.name}`" in line), None)
        assert row, package.name
        stated = package.licence.replace(" License", "")
        assert stated in row, f"{package.name} declares {package.licence}; the table says {row}"


def test_every_runtime_dependency_in_pyproject_is_in_the_list():
    """A dependency added without listing it is the way this goes stale."""
    pyproject = (
        pathlib.Path(__file__).resolve().parents[1] / "pyproject.toml"
    ).read_text(encoding="utf-8")
    block = pyproject[pyproject.index("dependencies = [") : pyproject.index("[project.optional")]
    declared = {m.group(1) for m in re.finditer(r'"([a-z0-9\-]+)[><=]', block)}
    assert declared <= set(licences.RUNTIME), declared - set(licences.RUNTIME)


def test_the_services_and_their_terms_are_named():
    for service in ("Amazon Bedrock", "Amazon SES", "GitHub Actions"):
        assert service in DOC, service
    assert "AWS Customer Agreement" in DOC


def test_what_it_adds_to_the_sdk_is_stated_rather_than_claimed():
    """S12 asks an entrant to build on open source, not wrap it."""
    for addition in (
        "edge condition that makes six readers a requirement",
        "composer that holds no tools",
        "claim layer between the model and the reader",
        "release gate in plain code",
        "redaction boundary before the model",
    ):
        assert addition in DOC, addition
    assert "None of the above is orchestration" in DOC
