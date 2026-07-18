from __future__ import annotations

import ast
from dataclasses import dataclass
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[2]
AGENT_ROOT = BACKEND_ROOT / "app" / "agents"
EXCLUDED_TREE_PARTS = {"archive", "examples", "__pycache__"}

ORM_MAPPING_NAMES = {
    "BaseModel",
    "ProjectWorkspace",
    "Resource",
    "Scene",
    "Task",
    "WorkflowGate",
    "WorkflowGateDecision",
    "WorkflowNodeAttempt",
    "WorkflowNodeState",
    "WorkflowPublishedDeliverable",
    "WorkflowSession",
}

DOMAIN_NAMES_IN_ORM_PACKAGE = {
    "AgentStatus",
    "AgentType",
    "ResourceType",
    "SceneType",
    "TaskStatus",
    "TaskType",
    "WorkflowAttemptStatus",
    "WorkflowGateStatus",
    "WorkflowNodeStatus",
    "WorkflowSessionStatus",
}


@dataclass(frozen=True, order=True)
class BoundaryViolation:
    relative_path: str
    category: str
    module: str
    symbol: str

    def render(self) -> str:
        return f"{self.relative_path}: {self.category} {self.module}:{self.symbol}"


def _is_module_or_child(module: str, parent: str) -> bool:
    return module == parent or module.startswith(f"{parent}.")


def _classify_import(module: str, symbol: str) -> str | None:
    if _is_module_or_child(module, "sqlalchemy"):
        return "persistence_framework"
    if _is_module_or_child(module, "app.core.database"):
        return "database_composition"
    if _is_module_or_child(module, "app.models"):
        if symbol in DOMAIN_NAMES_IN_ORM_PACKAGE:
            return "domain_contract_in_orm_package"
        if symbol in ORM_MAPPING_NAMES:
            return "orm_mapping"
        return "orm_package_unknown"
    return None


def _module_name(path: Path, *, backend_root: Path) -> str:
    relative = path.relative_to(backend_root).with_suffix("")
    parts = list(relative.parts)
    if parts[-1] == "__init__":
        parts.pop()
    return ".".join(parts)


def _resolve_from_module(
    node: ast.ImportFrom,
    *,
    current_module: str,
    is_package: bool,
) -> str:
    if node.level == 0:
        return node.module or ""

    package_parts = current_module.split(".")
    if not is_package:
        package_parts.pop()
    ascend = node.level - 1
    if ascend > len(package_parts):
        return node.module or ""
    base_parts = package_parts[: len(package_parts) - ascend]
    if node.module:
        base_parts.extend(node.module.split("."))
    return ".".join(base_parts)


class _ImportBoundaryVisitor(ast.NodeVisitor):
    def __init__(
        self,
        *,
        relative_path: str,
        current_module: str,
        is_package: bool,
    ) -> None:
        self.relative_path = relative_path
        self.current_module = current_module
        self.is_package = is_package
        self.violations: list[BoundaryViolation] = []

    def _record(self, *, module: str, symbol: str) -> None:
        category = _classify_import(module, symbol)
        if category is None:
            return
        self.violations.append(
            BoundaryViolation(
                relative_path=self.relative_path,
                category=category,
                module=module,
                symbol=symbol,
            )
        )

    def visit_Import(self, node: ast.Import) -> None:
        for alias in node.names:
            self._record(module=alias.name, symbol="*")

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        module = _resolve_from_module(
            node,
            current_module=self.current_module,
            is_package=self.is_package,
        )
        for alias in node.names:
            self._record(module=module, symbol=alias.name)

    def visit_Call(self, node: ast.Call) -> None:
        dynamic_module: str | None = None
        if (
            isinstance(node.func, ast.Attribute)
            and isinstance(node.func.value, ast.Name)
            and node.func.value.id == "importlib"
            and node.func.attr == "import_module"
        ):
            dynamic_module = self._constant_first_argument(node)
        elif isinstance(node.func, ast.Name) and node.func.id == "__import__":
            dynamic_module = self._constant_first_argument(node)
        if dynamic_module:
            self._record(module=dynamic_module, symbol="<dynamic_import>")
        self.generic_visit(node)

    @staticmethod
    def _constant_first_argument(node: ast.Call) -> str | None:
        if not node.args:
            return None
        first = node.args[0]
        if isinstance(first, ast.Constant) and isinstance(first.value, str):
            return first.value
        return None


def scan_python_tree(root: Path, *, backend_root: Path) -> set[BoundaryViolation]:
    violations: set[BoundaryViolation] = set()
    for path in sorted(root.rglob("*.py")):
        relative_to_root = path.relative_to(root)
        if EXCLUDED_TREE_PARTS.intersection(relative_to_root.parts):
            continue
        relative_path = path.relative_to(backend_root).as_posix()
        visitor = _ImportBoundaryVisitor(
            relative_path=relative_path,
            current_module=_module_name(path, backend_root=backend_root),
            is_package=path.name == "__init__.py",
        )
        visitor.visit(ast.parse(path.read_text(encoding="utf-8"), filename=str(path)))
        violations.update(visitor.violations)
    return violations


EXPECTED_TRANSITIONAL_DEBT: set[BoundaryViolation] = set()


def _format_diff(
    observed: set[BoundaryViolation],
    expected: set[BoundaryViolation],
) -> str:
    added = sorted(observed - expected)
    removed = sorted(expected - observed)
    sections = []
    if added:
        sections.append("new boundary violations:\n" + "\n".join(item.render() for item in added))
    if removed:
        sections.append(
            "resolved debt still listed; reduce the explicit baseline:\n"
            + "\n".join(item.render() for item in removed)
        )
    return "\n\n".join(sections)


def test_production_agent_persistence_debt_is_explicit_and_cannot_expand():
    observed = scan_python_tree(AGENT_ROOT, backend_root=BACKEND_ROOT)

    assert observed == EXPECTED_TRANSITIONAL_DEBT, _format_diff(
        observed,
        EXPECTED_TRANSITIONAL_DEBT,
    )


def test_production_agent_callables_do_not_accept_persistence_shaped_parameters():
    violations: list[str] = []
    for path in sorted(AGENT_ROOT.rglob("*.py")):
        relative = path.relative_to(AGENT_ROOT)
        if EXCLUDED_TREE_PARTS.intersection(relative.parts):
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            parameter_names = {
                argument.arg
                for argument in [*node.args.posonlyargs, *node.args.args, *node.args.kwonlyargs]
            }
            forbidden = sorted(parameter_names.intersection({"db", "database_session"}))
            if forbidden:
                violations.append(
                    f"{path.relative_to(BACKEND_ROOT).as_posix()}:{node.lineno} "
                    f"{node.name} accepts {', '.join(forbidden)}"
                )

    assert violations == []


def test_boundary_guard_scans_agent_helpers_not_only_agent_classes(tmp_path):
    backend_root = tmp_path / "backend"
    helper = backend_root / "app" / "agents" / "utils" / "persistence_helper.py"
    helper.parent.mkdir(parents=True)
    helper.write_text(
        "from sqlalchemy.orm import Session\nfrom app.models import Task\n",
        encoding="utf-8",
    )

    observed = scan_python_tree(backend_root / "app" / "agents", backend_root=backend_root)

    assert observed == {
        BoundaryViolation(
            "app/agents/utils/persistence_helper.py",
            "persistence_framework",
            "sqlalchemy.orm",
            "Session",
        ),
        BoundaryViolation(
            "app/agents/utils/persistence_helper.py",
            "orm_mapping",
            "app.models",
            "Task",
        ),
    }


def test_boundary_guard_distinguishes_domain_names_from_orm_mappings(tmp_path):
    backend_root = tmp_path / "backend"
    module = backend_root / "app" / "agents" / "sample.py"
    module.parent.mkdir(parents=True)
    module.write_text("from app.models import AgentType, Task\n", encoding="utf-8")

    observed = scan_python_tree(backend_root / "app" / "agents", backend_root=backend_root)

    assert observed == {
        BoundaryViolation(
            "app/agents/sample.py",
            "domain_contract_in_orm_package",
            "app.models",
            "AgentType",
        ),
        BoundaryViolation(
            "app/agents/sample.py",
            "orm_mapping",
            "app.models",
            "Task",
        ),
    }


def test_domain_execution_contract_is_persistence_free():
    observed = scan_python_tree(BACKEND_ROOT / "app" / "domain", backend_root=BACKEND_ROOT)

    assert observed == set()


def test_production_code_imports_domain_enums_from_domain_package():
    observed = scan_python_tree(BACKEND_ROOT / "app", backend_root=BACKEND_ROOT)
    packaging_leaks = {
        violation
        for violation in observed
        if violation.category == "domain_contract_in_orm_package"
    }

    assert packaging_leaks == set()
