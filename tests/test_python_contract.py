"""Verify the repository quality policy on small, synthetic Python files."""

import unittest

from tools.check_python_contract import check_source


class PythonContractTests(unittest.TestCase):
    """Exercise failure and success paths for the documentation and typing gate."""

    def test_documented_concrete_api_passes(self) -> None:
        """A public API with specific annotations and useful docstrings passes."""
        source = '''
"""Provide a small example for policy tests."""

def label(index: int) -> str:
    """Format a finding index for display.

    Args:
        index: Zero-based position of the finding.

    Returns:
        A display label for the finding.
    """
    return str(index)
'''
        self.assertEqual(check_source(source, "example.py"), [])

    def test_missing_docs_and_suppressions_are_errors(self) -> None:
        """Missing API sections, generic aliases and inline suppressions are rejected."""
        source = '''
"""Provide a small example for policy tests."""

from typing import Any as Dynamic

def inspect(values: "list[Dynamic]") -> int:
    """TODO: Document me."""
    raise ValueError("incorrect")  # noqa: TRY003
'''
        errors = "\n".join(check_source(source, "example.py"))
        self.assertIn("descriptive API summary", errors)
        self.assertIn("descriptive entry for values", errors)
        self.assertIn("descriptive entry for ValueError", errors)
        self.assertIn("concrete type", errors)
        self.assertIn("suppression is forbidden", errors)
