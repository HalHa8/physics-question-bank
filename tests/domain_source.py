"""Inspect the real modular function, adapting upstream's isolated AST harness.

Only explicit dependency accesses are unbound into that harness's fake namespace.
This does not synthesize a monolithic main.py or alter production behavior.
"""
import ast
from copy import deepcopy
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class _Unbind(ast.NodeTransformer):
    def visit_Attribute(self, node):
        if isinstance(node.value, ast.Name) and node.value.id == 'dependencies':
            return ast.copy_location(ast.Name(id=node.attr, ctx=node.ctx), node)
        if (isinstance(node.value, ast.Attribute) and node.value.attr == 'state'
                and isinstance(node.value.value, ast.Name) and node.value.value.id == 'dependencies'):
            return ast.copy_location(ast.Name(id=node.attr, ctx=node.ctx), node)
        return self.generic_visit(node)


def domain_function(name, module):
    tree = ast.parse((ROOT / 'mathbank' / (module + '.py')).read_text(encoding='utf-8'))
    node = deepcopy(next(node for node in tree.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == name))
    node.decorator_list = []
    node = _Unbind().visit(node)
    pairs = [(arg, default) for arg, default in zip(node.args.kwonlyargs, node.args.kw_defaults)
             if arg.arg != 'dependencies']
    node.args.kwonlyargs = [arg for arg, _ in pairs]
    node.args.kw_defaults = [default for _, default in pairs]
    return ast.fix_missing_locations(node)
