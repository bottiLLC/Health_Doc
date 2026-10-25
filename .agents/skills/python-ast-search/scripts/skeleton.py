"""AST skeleton extractor for Python codebases.

Extracts classes, methods, top-level functions, type signatures, and first-line
docstrings to enable skeleton-first exploration without ingesting implementation bodies.
"""

from __future__ import annotations

import argparse
import ast
import os
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

DocstringNode = ast.AsyncFunctionDef | ast.FunctionDef | ast.ClassDef | ast.Module

EXCLUDED_DIRS: frozenset[str] = frozenset(
    {
        ".git",
        ".hg",
        ".svn",
        ".venv",
        "venv",
        "env",
        "__pycache__",
        ".mypy_cache",
        ".ruff_cache",
        ".pytest_cache",
        ".context",
        ".agents",
        "node_modules",
        "build",
        "dist",
        ".tox",
        ".idea",
        ".vscode",
    }
)


def format_docstring(node: DocstringNode, indent: str = "    ") -> list[str]:
    doc = ast.get_docstring(node, clean=True)
    if not doc:
        return []
    first_line = doc.strip().splitlines()[0]
    return [f'{indent}"""{first_line}"""']


def format_function(
    node: ast.FunctionDef | ast.AsyncFunctionDef,
    indent: str = "",
) -> list[str]:
    lines: list[str] = []
    for dec in node.decorator_list:
        lines.append(f"{indent}@{ast.unparse(dec)}")
    prefix = "async def " if isinstance(node, ast.AsyncFunctionDef) else "def "
    args_str = ast.unparse(node.args)
    ret_str = f" -> {ast.unparse(node.returns)}" if node.returns else ""
    lines.append(f"{indent}{prefix}{node.name}({args_str}){ret_str}:")
    doc_lines = format_docstring(node, indent + "    ")
    if doc_lines:
        lines.extend(doc_lines)
    else:
        lines.append(f"{indent}    ...")
    return lines


def format_class(node: ast.ClassDef, indent: str = "") -> list[str]:
    lines: list[str] = []
    for dec in node.decorator_list:
        lines.append(f"{indent}@{ast.unparse(dec)}")
    bases_str = f"({', '.join(ast.unparse(b) for b in node.bases)})" if node.bases else ""
    lines.append(f"{indent}class {node.name}{bases_str}:")
    doc_lines = format_docstring(node, indent + "    ")
    if doc_lines:
        lines.extend(doc_lines)

    body_has_items = False
    for item in node.body:
        if isinstance(item, ast.AnnAssign) and isinstance(item.target, ast.Name):
            val_str = f" = {ast.unparse(item.value)}" if item.value is not None else ""
            lines.append(f"{indent}    {item.target.id}: {ast.unparse(item.annotation)}{val_str}")
            body_has_items = True
        elif isinstance(item, ast.Assign):
            for t in item.targets:
                if isinstance(t, ast.Name) and (t.id.isupper() or t.id.startswith("__")):
                    lines.append(f"{indent}    {t.id} = {ast.unparse(item.value)}")
                    body_has_items = True
        elif isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
            lines.extend(format_function(item, indent=indent + "    "))
            body_has_items = True

    if not doc_lines and not body_has_items:
        lines.append(f"{indent}    ...")

    return lines


def extract_file_skeleton(file_path: Path) -> str:
    try:
        content = file_path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        try:
            content = file_path.read_text(encoding="cp932")
        except Exception as exc:
            return f"# [Error reading file {file_path}: {exc}]\n"
    except Exception as exc:
        return f"# [Error reading file {file_path}: {exc}]\n"

    try:
        tree = ast.parse(content, filename=str(file_path))
    except SyntaxError as exc:
        return f"# [SyntaxError in {file_path}: {exc}]\n"

    output: list[str] = [f"=== {file_path.as_posix()} ==="]

    mod_doc = format_docstring(tree, indent="")
    if mod_doc:
        output.extend(mod_doc)

    for item in tree.body:
        if isinstance(item, (ast.Import, ast.ImportFrom)):
            output.append(ast.unparse(item))
        elif isinstance(item, ast.AnnAssign) and isinstance(item.target, ast.Name):
            val_str = f" = {ast.unparse(item.value)}" if item.value is not None else ""
            output.append(f"{item.target.id}: {ast.unparse(item.annotation)}{val_str}")
        elif isinstance(item, ast.Assign):
            for t in item.targets:
                if isinstance(t, ast.Name) and (t.id.isupper() or t.id.startswith("__")):
                    output.append(f"{t.id} = {ast.unparse(item.value)}")
        elif hasattr(ast, "TypeAlias") and isinstance(item, ast.TypeAlias):
            output.append(f"type {ast.unparse(item.name)} = {ast.unparse(item.value)}")
        elif isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
            output.extend(format_function(item, indent=""))
        elif isinstance(item, ast.ClassDef):
            output.extend(format_class(item, indent=""))

    output.append("")  # blank trailing line
    return "\n".join(output)


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description="Extract AST skeleton from Python files.")
    parser.add_argument("paths", nargs="*", default=["."], help="Directories or files to process.")
    args = parser.parse_args()

    files_to_process: list[Path] = []
    for raw_path in args.paths:
        p = Path(raw_path)
        if p.is_file() and p.suffix == ".py":
            files_to_process.append(p)
        elif p.is_dir():
            for root, dirs, files in os.walk(p):
                dirs[:] = [d for d in dirs if d not in EXCLUDED_DIRS and not d.startswith(".")]
                for f in files:
                    if f.endswith(".py"):
                        files_to_process.append(Path(root) / f)

    for py_file in sorted(files_to_process):
        skeleton = extract_file_skeleton(py_file)
        sys.stdout.write(skeleton + "\n")


if __name__ == "__main__":
    main()
