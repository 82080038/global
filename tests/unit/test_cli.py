"""Regression tests for CLI dispatch (cli.py).

Guards against regressions like duplicate `elif args.cmd == "backtest"` blocks
where the first (incomplete) block silently shadowed the full-featured one,
causing --monte-carlo/--walk-forward to never execute.
"""

import ast
from pathlib import Path

CLI_PATH = Path(__file__).resolve().parents[2] / "src" / "trading_system" / "cli.py"


def _main_if_chain_cmd_values():
    """Parse cli.py's main() if/elif chain and return the list of args.cmd values compared."""
    tree = ast.parse(CLI_PATH.read_text(encoding="utf-8"))
    main_func = next(n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef) and n.name == "main")

    cmd_values = []

    def walk_if_chain(node):
        # node.test is expected to be `args.cmd == "<value>"`
        test = node.test
        if isinstance(test, ast.Compare) and isinstance(test.ops[0], ast.Eq):
            comparator = test.comparators[0]
            if isinstance(comparator, ast.Constant):
                cmd_values.append(comparator.value)
        for stmt in node.orelse:
            if isinstance(stmt, ast.If):
                walk_if_chain(stmt)

    for stmt in main_func.body:
        if isinstance(stmt, ast.If):
            walk_if_chain(stmt)
            break

    return cmd_values


def test_no_duplicate_cmd_branches_in_main():
    """Each args.cmd value must appear at most once in the if/elif chain."""
    cmd_values = _main_if_chain_cmd_values()
    assert len(cmd_values) == len(set(cmd_values)), (
        f"Duplicate args.cmd branches detected in cli.main(): {cmd_values}"
    )


def test_backtest_branch_supports_monte_carlo_and_walk_forward():
    """The single backtest branch must reference monte_carlo/walk_forward args."""
    source = CLI_PATH.read_text(encoding="utf-8")
    assert "args.monte_carlo" in source
    assert "args.walk_forward" in source
