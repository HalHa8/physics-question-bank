"""Read the released PDF feature boundary without initializing the application.

Local PDF projects/checkpoint adapters are retained experimental components.
Their HTTP integration is not claimed while RuntimeState disables the feature.
Pure component and released PDF processing tests remain active.
"""
import ast
from pathlib import Path
import pytest


def pdf_cloud_only_enabled():
    source = Path(__file__).resolve().parents[1] / 'mathbank' / 'application_state.py'
    state = next(node for node in ast.parse(source.read_text(encoding='utf-8')).body
                 if isinstance(node, ast.ClassDef) and node.name == 'RuntimeState')
    nodes = [node for node in state.body if isinstance(node, ast.AnnAssign)
             and isinstance(node.target, ast.Name) and node.target.id == 'PDF_CLOUD_ONLY']
    assert len(nodes) == 1 and isinstance(nodes[0].value, ast.Constant)
    assert type(nodes[0].value.value) is bool
    return nodes[0].value.value


PDF_CLOUD_ONLY = pdf_cloud_only_enabled()
experimental_pdf_only = pytest.mark.skipif(PDF_CLOUD_ONLY,
    reason='Released PDF boundary disables retained local-project/checkpoint experiments')
