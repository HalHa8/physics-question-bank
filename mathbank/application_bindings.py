"""Composition-time binding and a narrowly scoped legacy module adapter.

Domain code accepts frozen dependency contracts. Only the compatibility adapter
consults a caller-owned namespace; domain modules never import or discover main.
"""

from dataclasses import fields
import functools
import inspect
from types import ModuleType

from mathbank.application_state import RuntimeState

_MISSING = object()


class ApplicationBindings:
    def __init__(self, state: RuntimeState, defaults):
        self.state = state
        self.defaults = defaults
        self.services = {}
        self.legacy_namespace = {}
        self.state_names = frozenset(field.name for field in fields(RuntimeState))
        self.app = None

    def resolve(self, name):
        if name in self.state_names:
            value = getattr(self.state, name)
            if value is _MISSING:
                raise AttributeError(name)
            return value
        if name in self.legacy_namespace:
            return self.legacy_namespace[name]
        if name in self.services:
            return self.services[name]
        try:
            return getattr(self.defaults, name)
        except AttributeError:
            raise AttributeError(name) from None

    def dependencies(self, contract):
        return contract(**{
            field.name: self.state if field.name == "state" else self.resolve(field.name)
            for field in fields(contract)
        })

    def bind(self, function, contract):
        if inspect.iscoroutinefunction(function):
            @functools.wraps(function)
            async def bound(*args, **kwargs):
                return await function(*args, dependencies=self.dependencies(contract), **kwargs)
        else:
            @functools.wraps(function)
            def bound(*args, **kwargs):
                return function(*args, dependencies=self.dependencies(contract), **kwargs)
        signature = inspect.signature(function)
        bound.__signature__ = signature.replace(parameters=[
            parameter for parameter in signature.parameters.values()
            if parameter.name != "dependencies"
        ])
        return bound


def install_legacy_facade(module, bindings):
    """Preserve old imports and override points without copying runtime state."""
    bindings.legacy_namespace = module.__dict__

    class LegacyEntry(ModuleType):
        def __getattr__(self, name):
            return bindings.resolve(name)

        def __setattr__(self, name, value):
            if name in bindings.state_names:
                setattr(bindings.state, name, value)
            else:
                super().__setattr__(name, value)

        def __delattr__(self, name):
            # unittest.mock deletes non-local exports before restoring them.
            # A missing marker gives it normal module semantics without ever
            # duplicating the actual runtime value in this module's dictionary.
            if name in bindings.state_names:
                if getattr(bindings.state, name) is _MISSING:
                    raise AttributeError(name)
                setattr(bindings.state, name, _MISSING)
            else:
                super().__delattr__(name)

        def __dir__(self):
            return sorted(set(super().__dir__()) | bindings.state_names
                          | set(bindings.services) | set(vars(bindings.defaults)))

    module.__class__ = LegacyEntry
