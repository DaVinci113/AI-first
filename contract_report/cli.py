"""CLI: python -m contract_report --data data --date 2026-11-10 [--out out].

Ничего не импортирует лишнего, работает на голом Python 3.11+.
"""

from __future__ import annotations

import argparse
import datetime as dt
import pathlib
import sys

from . import __version__
from .io_csv import DataError, check_references, load_contracts, load_payments, load_works
from .render import render_console, write_report_files
from .report import build_report


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="contract_report",
        description="Отчёт по выплатам: по каждой работе и договору, на дату.",
    )
    parser.add_argument("--data", type=pathlib.Path, default=pathlib.Path("data"),
                        help="папка с contracts.csv, works.csv, payments.csv (по умолчанию ./data)")
    parser.add_argument("--date", type=dt.date.fromisoformat, required=True,
                        help="дата отчёта в формате YYYY-MM-DD, например 2026-11-10")
    parser.add_argument("--out", type=pathlib.Path, default=pathlib.Path("out"),
                        help="куда сохранить CSV и TXT отчёт (по умолчанию ./out)")
    parser.add_argument("--no-console", action="store_true",
                        help="не печатать отчёт в консоль")
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)

    try:
        contracts = load_contracts(args.data / "contracts.csv")
        works = load_works(args.data / "works.csv")
        payments = load_payments(args.data / "payments.csv")
        check_references(contracts, works, payments)
        report = build_report(contracts, works, payments, args.date)
    except DataError as exc:
        print(f"Ошибка данных: {exc}", file=sys.stderr)
        return 2

    if not args.no_console:
        print(render_console(report, args.date))

    paths = write_report_files(report, args.out, args.date)
    print(f"CSV: {paths['csv']}")
    print(f"TXT: {paths['txt']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
