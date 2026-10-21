"""Composition-time binding and a narrowly scoped legacy module adapter.

Domain code accepts frozen dependency contracts. Only the compatibility adapter
consults a caller-owned namespace; domain modules never import or discover main.
"""

from dataclasses import fields
import functools
import inspect
from contextlib import ExitStack
from types import ModuleType

from mathbank.application_state import RuntimeState

_MISSING = object()


def _service_guards(function):
    """Immutable composition metadata; no locks or runtime in domain modules."""
    return {
        ("mathbank.document_project_runtime", "_release_document_project_assets"): ('serialize_asset_lifecycle',),
        ("mathbank.library_transfer_service", "export_library_transfer"): ('serialize_asset_lifecycle',),
        ("mathbank.library_transfer_service", "import_library_transfer"): ('serialize_asset_lifecycle',),
        ("mathbank.maintenance_service", "clean_orphaned_images"): ('serialize_asset_lifecycle',),
        ("mathbank.question_commands", "create_question"): ('serialize_asset_lifecycle', 'serialize_curriculum_write', 'project_import_guard'),
        ("mathbank.question_commands", "update_question"): ('serialize_asset_lifecycle', 'serialize_curriculum_write'),
        ("mathbank.question_commands", "delete_question"): ('serialize_asset_lifecycle',),
        ("mathbank.question_asset_service", "rollback_question_asset_promotions"): ('serialize_asset_lifecycle',),
        ("mathbank.question_asset_service", "delete_unreferenced_question_assets"): ('serialize_asset_lifecycle',),
        ("mathbank.question_asset_service", "promote_question_temp_assets"): ('serialize_asset_lifecycle',),
        ("mathbank.question_asset_service", "_delete_task_temp_assets"): ('serialize_asset_lifecycle',),
    }.get((function.__module__, function.__name__), ())



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
                # Writers share the same application-owned curriculum lock and
                # asset lifecycle lease as cleanup and retained-project import.
                # Binding keeps these guards outside pure domain imports.
                guards = _service_guards(function)
                with ExitStack() as stack:
                    if "serialize_asset_lifecycle" in guards:
                        from mathbank.asset_lifecycle import ASSET_LIFECYCLE_LOCK
                        stack.enter_context(ASSET_LIFECYCLE_LOCK)
                    if "serialize_curriculum_write" in guards:
                        stack.enter_context(self.state._METADATA_SAVE_LOCK)
                    project_id = kwargs.get("import_project_id")
                    if "project_import_guard" in guards and isinstance(project_id, str) and project_id:
                        from fastapi import HTTPException
                        if self.state.DOCUMENT_PROJECTS is None:
                            raise HTTPException(409, "本地工程服务不可用，请保留校对稿。")
                        stack.enter_context(self.state.DOCUMENT_PROJECTS.operation(project_id))
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
