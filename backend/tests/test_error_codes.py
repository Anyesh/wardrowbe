import ast
import json
import re
import textwrap
from dataclasses import dataclass, field
from pathlib import Path

import pytest

BACKEND = Path(__file__).resolve().parents[1]
APP = BACKEND / "app"
ERRORS_EN = BACKEND.parent / "frontend" / "messages" / "en" / "errors.json"
ERRORS_MODULE = APP / "utils" / "errors.py"
CODED_ROOTS = {"Coded"}
UPPER_SNAKE = re.compile(r"^[A-Z][A-Z0-9_]*$")


@dataclass
class CodeUse:
    where: str
    code: str | None
    params: set[str] | None = None


@dataclass
class Scan:
    raw_http_exceptions: list[str] = field(default_factory=list)
    uses: list[CodeUse] = field(default_factory=list)
    classes_without_code: list[str] = field(default_factory=list)


def _modules() -> dict[Path, ast.Module]:
    return {path: ast.parse(path.read_text(), str(path)) for path in sorted(APP.rglob("*.py"))}


def _name(node: ast.AST) -> str | None:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return node.attr
    return None


def _literal(node: ast.AST | None) -> str | None:
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    return None


def _class_code(node: ast.ClassDef) -> ast.AST | None:
    for statement in node.body:
        targets = []
        if isinstance(statement, ast.Assign):
            targets = statement.targets
        elif isinstance(statement, ast.AnnAssign) and statement.value is not None:
            targets = [statement.target]
        for target in targets:
            if isinstance(target, ast.Name) and target.id == "code":
                return statement.value
    return None


def _coded_classes(modules: dict[Path, ast.Module]) -> dict[str, tuple[list[str], ast.AST | None]]:
    classes = {
        node.name: ([b for b in map(_name, node.bases) if b], _class_code(node))
        for tree in modules.values()
        for node in ast.walk(tree)
        if isinstance(node, ast.ClassDef)
    }
    coded = set(CODED_ROOTS)
    changed = True
    while changed:
        changed = False
        for name, (bases, _) in classes.items():
            if name not in coded and coded & set(bases):
                coded.add(name)
                changed = True
    return {name: classes[name] for name in coded if name in classes}


def _default_code(name: str, coded: dict[str, tuple[list[str], ast.AST | None]]) -> str | None:
    bases, code = coded.get(name, ([], None))
    if code is not None:
        return _literal(code)
    for base in bases:
        if base in coded and base not in CODED_ROOTS:
            found = _default_code(base, coded)
            if found:
                return found
    return None


def _kwarg(call: ast.Call, name: str) -> ast.AST | None:
    return next((k.value for k in call.keywords if k.arg == name), None)


def _arg(call: ast.Call, index: int, name: str) -> ast.AST | None:
    return call.args[index] if len(call.args) > index else _kwarg(call, name)


def _dict_keys(node: ast.AST | None) -> set[str] | None:
    if isinstance(node, ast.Dict) and all(_literal(k) is not None for k in node.keys):
        return {_literal(k) for k in node.keys}
    return None


def _enclosing_classes(tree: ast.Module) -> dict[ast.AST, str]:
    owner: dict[ast.AST, str] = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef):
            for child in ast.walk(node):
                owner.setdefault(child, node.name)
    return owner


def _is_super_init(call: ast.Call) -> bool:
    func = call.func
    return (
        isinstance(func, ast.Attribute)
        and func.attr == "__init__"
        and isinstance(func.value, ast.Call)
        and _name(func.value.func) == "super"
    )


def _body_code(node: ast.AST) -> str | None:
    if isinstance(node, ast.Dict):
        for key, value in zip(node.keys, node.values, strict=True):
            if key is not None and _literal(key) == "error_code":
                return _literal(value)
    if isinstance(node, ast.Call):
        return _literal(_kwarg(node, "error_code"))
    return None


def scan(modules: dict[Path, ast.Module] | None = None) -> Scan:
    modules = _modules() if modules is None else modules
    coded = _coded_classes(modules)
    own_init = {
        node.name
        for tree in modules.values()
        for node in ast.walk(tree)
        if isinstance(node, ast.ClassDef)
        and node.name in coded
        and any(isinstance(b, ast.FunctionDef) and b.name == "__init__" for b in node.body)
    }
    result = Scan()
    for name, (_, code) in coded.items():
        if name in CODED_ROOTS:
            continue
        if code is not None and _literal(code) is None:
            result.uses.append(CodeUse(f"class {name}", None))
        elif _default_code(name, coded) is None:
            result.classes_without_code.append(name)
        elif code is not None:
            result.uses.append(CodeUse(f"class {name}", _literal(code)))

    for path, tree in modules.items():
        rel = path.relative_to(BACKEND)
        owners = _enclosing_classes(tree)
        for node in ast.walk(tree):
            body_code = _body_code(node)
            if body_code and UPPER_SNAKE.match(body_code):
                result.uses.append(CodeUse(f"{rel}:{node.lineno}", body_code))
            if not isinstance(node, ast.Call):
                continue
            where = f"{rel}:{node.lineno}"
            callee = _name(node.func)
            if callee == "HTTPException" and path != ERRORS_MODULE:
                result.raw_http_exceptions.append(where)
            elif callee == "CodedHTTPException" and path != ERRORS_MODULE:
                code_node = _arg(node, 1, "error_code")
                result.uses.append(
                    CodeUse(where, _literal(code_node), _dict_keys(_arg(node, 3, "params")))
                )
            elif callee == "http_error" and path != ERRORS_MODULE:
                result.uses.append(CodeUse(where, _literal(_arg(node, 2, "fallback_code"))))
            elif (callee in coded and callee not in CODED_ROOTS) or (
                _is_super_init(node)
                and owners.get(node) in coded
                and owners.get(node) not in CODED_ROOTS
            ):
                code_node = _kwarg(node, "code")
                params = {k.arg for k in node.keywords if k.arg not in (None, "code")}
                if any(k.arg is None for k in node.keywords) or callee in own_init:
                    params = None
                if code_node is not None:
                    result.uses.append(CodeUse(where, _literal(code_node), params))
                elif callee in coded:
                    result.uses.append(CodeUse(where, _default_code(callee, coded), params))
                else:
                    owner = owners[node]
                    result.uses.append(CodeUse(where, _default_code(owner, coded), params))
    return result


def icu_arguments(message: str) -> set[str]:
    names: set[str] = set()
    depth = 0
    i = 0
    while i < len(message):
        char = message[i]
        if char == "'" and i + 1 < len(message) and message[i + 1] in "{}'":
            end = message.find("'", i + 1)
            i = len(message) if end == -1 else end + 1
            continue
        if char == "{":
            depth += 1
            if depth % 2 == 1:
                j = i + 1
                while j < len(message) and message[j] not in ",}":
                    j += 1
                names.add(message[i + 1 : j].strip())
        elif char == "}":
            depth -= 1
        i += 1
    return names


@pytest.fixture(scope="module")
def catalog() -> dict[str, object]:
    assert ERRORS_EN.exists(), f"{ERRORS_EN} is missing; run this test from the repo checkout"
    return json.loads(ERRORS_EN.read_text())


@pytest.fixture(scope="module")
def scanned() -> Scan:
    return scan()


def test_icu_arguments_skip_plural_branch_text():
    message = "{count, plural, one {# item over {limit}} other {# items}} in {place}"

    assert icu_arguments(message) == {"count", "limit", "place"}


def _scan_source(source: str) -> Scan:
    path = APP / "sample.py"
    return scan({path: ast.parse(textwrap.dedent(source))})


def test_params_passed_through_super_init_take_the_class_default():
    found = _scan_source(
        """
        class TooBig(Coded, Exception):
            code = "IMAGE_TOO_LARGE"

            def __init__(self, size):
                super().__init__("too big", size=size)
        """
    )

    assert [(u.code, u.params) for u in found.uses if u.params is not None] == [
        ("IMAGE_TOO_LARGE", {"size"})
    ]


def test_codes_in_200_bodies_are_collected_but_lowercase_ones_are_not():
    found = _scan_source(
        """
        ok = {"status": "error", "error_code": "AI_ENDPOINT_FAILED"}
        status = AuthStatus(error_code="AUTH_NOT_CONFIGURED")
        row = BulkUploadResult(error_code="duplicate")
        """
    )

    assert sorted(u.code for u in found.uses) == ["AI_ENDPOINT_FAILED", "AUTH_NOT_CONFIGURED"]


def test_no_uncoded_http_exception(scanned: Scan):
    assert scanned.raw_http_exceptions == []


def test_every_coded_class_has_a_literal_default(scanned: Scan):
    assert scanned.classes_without_code == []


def test_every_code_is_a_literal(scanned: Scan):
    assert [use.where for use in scanned.uses if use.code is None] == []


def test_every_code_has_an_english_message(scanned: Scan, catalog: dict[str, object]):
    missing = sorted(
        f"{use.where} {use.code}"
        for use in scanned.uses
        if use.code and not isinstance(catalog.get(use.code), str)
    )

    assert missing == []


def test_params_match_the_message_arguments(scanned: Scan, catalog: dict[str, object]):
    mismatched = []
    for use in scanned.uses:
        message = catalog.get(use.code or "")
        if use.params is None or not isinstance(message, str):
            continue
        expected = icu_arguments(message)
        if use.params != expected:
            mismatched.append(f"{use.where} {use.code}: sends {use.params}, message {expected}")

    assert mismatched == []
