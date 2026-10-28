"""Bounded static tracing from builtin input() to eval()/exec() in one file.

This is a possible data-flow path, not proof that a branch executes or that
an external caller can reach the function. It never runs reviewed code.
"""

import ast
from dataclasses import dataclass


@dataclass(frozen=True)
class Trace:
    source_line: int
    steps: tuple[str, ...]


@dataclass(frozen=True)
class DynamicSink:
    line: int
    name: str
    trigger: Trace | None


def _bound_names(statements: list[ast.stmt]) -> set[str]:
    names: set[str] = set()

    class Bindings(ast.NodeVisitor):
        def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
            names.add(node.name)

        def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
            names.add(node.name)

        def visit_ClassDef(self, node: ast.ClassDef) -> None:
            names.add(node.name)

        def visit_Name(self, node: ast.Name) -> None:
            if isinstance(node.ctx, ast.Store):
                names.add(node.id)

        def visit_alias(self, node: ast.alias) -> None:
            names.add(node.asname or node.name.split(".")[0])

    visitor = Bindings()
    for statement in statements:
        visitor.visit(statement)
    return names


class _Tracer:
    def __init__(self, tree: ast.Module):
        self.tree = tree
        self.functions = {
            node.name: node for node in tree.body
            if isinstance(node, ast.FunctionDef)
        }
        self.global_shadowed = _bound_names(tree.body)
        self.local_shadowed = {
            name: (
                {arg.arg for arg in (*node.args.posonlyargs, *node.args.args, *node.args.kwonlyargs)}
                | _bound_names(node.body)
            )
            for name, node in self.functions.items()
        }
        self.triggers: dict[int, Trace] = {}
        self.module_values: dict[str, Trace] = {}

    def _builtin(self, name: str, scope: str | None) -> bool:
        return (
            name not in self.global_shadowed
            and (scope is None or name not in self.local_shadowed[scope])
        )

    def _expression(
        self, node: ast.expr, values: dict[str, Trace], scope: str | None,
        stack: tuple[str, ...],
    ) -> Trace | None:
        if isinstance(node, ast.Name):
            return values.get(node.id)
        if isinstance(node, ast.Call):
            name = node.func.id if isinstance(node.func, ast.Name) else None
            arguments = [self._expression(arg, values, scope, stack) for arg in node.args]
            keywords = {
                keyword.arg: self._expression(keyword.value, values, scope, stack)
                for keyword in node.keywords if keyword.arg
            }
            if name == "input" and self._builtin(name, scope):
                return Trace(node.lineno, (f"input() 第 {node.lineno} 行",))
            if name in {"eval", "exec"} and self._builtin(name, scope):
                if arguments and arguments[0] and node.lineno not in self.triggers:
                    self.triggers[node.lineno] = Trace(
                        arguments[0].source_line,
                        (*arguments[0].steps, f"{name}() 第 {node.lineno} 行"),
                    )
                return None
            if name in self.functions and name not in stack and len(stack) < 5:
                return self._invoke(name, node, arguments, keywords, stack)
            return None
        if isinstance(node, (ast.BinOp, ast.BoolOp, ast.IfExp, ast.JoinedStr, ast.FormattedValue)):
            first: Trace | None = None
            for child in ast.iter_child_nodes(node):
                if isinstance(child, ast.expr):
                    trace = self._expression(child, values, scope, stack)
                    if trace and first is None:
                        first = trace
            return first
        if isinstance(node, ast.Subscript):
            self._expression(node.slice, values, scope, stack)
            return self._expression(node.value, values, scope, stack)
        for child in ast.iter_child_nodes(node):
            if isinstance(child, ast.expr):
                self._expression(child, values, scope, stack)
        return None

    def _invoke(
        self, name: str, call: ast.Call, arguments: list[Trace | None],
        keywords: dict[str, Trace | None],
        stack: tuple[str, ...],
    ) -> Trace | None:
        function = self.functions[name]
        values = dict(self.module_values)
        parameters = (*function.args.posonlyargs, *function.args.args)
        for parameter, trace in zip(parameters, arguments):
            if trace:
                values[parameter.arg] = Trace(
                    trace.source_line,
                    (*trace.steps, f"传入 {name}.{parameter.arg}（第 {call.lineno} 行）"),
                )
        for keyword, trace in keywords.items():
            if trace:
                values[keyword] = Trace(
                    trace.source_line,
                    (*trace.steps, f"传入 {name}.{keyword}（第 {call.lineno} 行）"),
                )
        result = self._block(function.body, values, name, (*stack, name))
        if result:
            return Trace(result.source_line, (*result.steps, f"由 {name}() 返回"))
        return None

    def _block(
        self, statements: list[ast.stmt], values: dict[str, Trace],
        scope: str | None, stack: tuple[str, ...],
    ) -> Trace | None:
        for statement in statements:
            if isinstance(statement, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                continue
            if isinstance(statement, (ast.Assign, ast.AnnAssign, ast.NamedExpr)):
                value = self._expression(statement.value, values, scope, stack) if statement.value else None
                targets = statement.targets if isinstance(statement, ast.Assign) else [statement.target]
                for target in targets:
                    if isinstance(target, ast.Name):
                        if value:
                            values[target.id] = value
                        else:
                            values.pop(target.id, None)
                continue
            if isinstance(statement, ast.Expr):
                self._expression(statement.value, values, scope, stack)
            elif isinstance(statement, ast.Return):
                return self._expression(statement.value, values, scope, stack) if statement.value else None
            elif isinstance(statement, ast.If):
                if isinstance(statement.test, ast.Constant) and isinstance(statement.test.value, bool):
                    branch = statement.body if statement.test.value else statement.orelse
                    result = self._block(branch, values.copy(), scope, stack)
                else:
                    self._expression(statement.test, values, scope, stack)
                    result = self._block(statement.body, values.copy(), scope, stack)
                    self._block(statement.orelse, values.copy(), scope, stack)
                if result:
                    return result
            elif isinstance(statement, (ast.For, ast.While, ast.With, ast.Try)):
                self._block(statement.body, values.copy(), scope, stack)
                if hasattr(statement, "orelse"):
                    self._block(statement.orelse, values.copy(), scope, stack)
        return None

    def scan(self) -> list[DynamicSink]:
        self._block(self.tree.body, self.module_values, None, ())
        unreachable: set[int] = set()
        for branch in ast.walk(self.tree):
            skipped: list[ast.stmt] = []
            if isinstance(branch, ast.If) and isinstance(branch.test, ast.Constant):
                if branch.test.value is True:
                    skipped = branch.orelse
                elif branch.test.value is False:
                    skipped = branch.body
            elif isinstance(branch, ast.While) and isinstance(branch.test, ast.Constant):
                if branch.test.value is False:
                    skipped = branch.body
            elif isinstance(branch, ast.For) and isinstance(branch.iter, (ast.List, ast.Tuple)):
                if not branch.iter.elts:
                    skipped = branch.body
            for statement in skipped:
                unreachable.update(id(node) for node in ast.walk(statement))
        sinks: list[DynamicSink] = []
        for node in ast.walk(self.tree):
            if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Name):
                continue
            if id(node) in unreachable:
                continue
            name = node.func.id
            if name not in {"eval", "exec"} or not node.args:
                continue
            scope = self._enclosing_function(node)
            if not self._builtin(name, scope):
                continue
            if isinstance(node.args[0], ast.Constant):
                continue
            sinks.append(DynamicSink(node.lineno, name, self.triggers.get(node.lineno)))
        return sorted(sinks, key=lambda sink: sink.line)

    def _enclosing_function(self, target: ast.AST) -> str | None:
        for name, function in self.functions.items():
            if any(node is target for node in ast.walk(function)):
                return name
        return None


def scan_dynamic_exec(source: str) -> list[DynamicSink]:
    tree = ast.parse(source)
    return _Tracer(tree).scan()
