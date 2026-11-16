"""Вывод отчёта: CSV-файл и таблица в консоль.

Один и тот же список строк, два формата: цифры гарантированно совпадают.
"""

from __future__ import annotations

import csv
import datetime as dt
import io
import pathlib
from decimal import Decimal
from typing import Sequence

from .models import ContractRow

WORK_COLUMNS = [
    "Договор",
    "Подрядчик",
    "Работа",
    "Название",
    "Статус",
    "Цена",
    "Выплачено",
    "Осталось оплатить",
]
CONTRACT_COLUMNS = [
    "Договор",
    "Подрядчик",
    "Сумма договора",
    "Выплачено",
    "Осталось оплатить",
    "Выплачено сверх работ",
]


def _money(value: Decimal) -> str:
    """Копейки всегда с двумя знаками, без экспоненты."""
    return str(value.quantize(Decimal("0.01")))


def work_rows(report: Sequence[ContractRow]) -> list[list[str]]:
    """Плоская таблица по работам."""
    rows: list[list[str]] = []
    for c in report:
        for w in c.works:
            rows.append(
                [
                    c.contract_id,
                    c.contractor,
                    w.work_id,
                    w.title,
                    w.status,
                    _money(w.price),
                    _money(w.paid),
                    _money(w.remaining),
                ]
            )
    return rows


def contract_rows(report: Sequence[ContractRow]) -> list[list[str]]:
    """Итоговая таблица по договорам."""
    return [
        [
            c.contract_id,
            c.contractor,
            _money(c.contract_amount),
            _money(c.paid),
            _money(c.remaining),
            _money(c.unallocated_paid),
        ]
        for c in report
    ]


def write_csv(report: Sequence[ContractRow], path: pathlib.Path) -> None:
    """Пишет отчёт в CSV: секция работ, пустая строка, секция договоров."""
    with path.open("w", encoding="utf-8-sig", newline="") as fh:
        writer = csv.writer(fh)
        _write_sections(writer, report)


def render_csv(report: Sequence[ContractRow]) -> str:
    """Тот же CSV, но в строку (для тестов)."""
    buf = io.StringIO()
    writer = csv.writer(buf)
    _write_sections(writer, report)
    return buf.getvalue()


def _write_sections(writer: csv.writer, report: Sequence[ContractRow]) -> None:
    writer.writerow(["По работам"])
    writer.writerow(WORK_COLUMNS)
    writer.writerows(work_rows(report))
    writer.writerow([])
    writer.writerow(["По договорам"])
    writer.writerow(CONTRACT_COLUMNS)
    writer.writerows(contract_rows(report))


def render_console(report: Sequence[ContractRow], on_date: dt.date) -> str:
    """Таблица в консоль: по договорам, внутри - работы, с отступами."""
    lines: list[str] = []
    lines.append(f"Отчёт на {on_date.isoformat()}")
    lines.append("")
    for c in report:
        lines.append(
            f"Договор {c.contract_id} — {c.contractor}: "
            f"сумма {_money(c.contract_amount)}, выплачено {_money(c.paid)}, "
            f"осталось {_money(c.remaining)}"
        )
        for w in c.works:
            lines.append(
                f"  {w.work_id} {w.title} ({w.status}): "
                f"цена {_money(w.price)}, выплачено {_money(w.paid)}, "
                f"осталось {_money(w.remaining)}"
            )
        if c.unallocated_paid > 0:
            lines.append(
                f"  сверх цен работ выплачено: {_money(c.unallocated_paid)} "
                f"(деньги по договору без привязки к работе)"
            )
        lines.append("")
    return "\n".join(lines)


def write_report_files(
    report: Sequence[ContractRow], out_dir: pathlib.Path, on_date: dt.date
) -> dict[str, pathlib.Path]:
    """Сохраняет CSV-отчёт и текстовый отчёт, возвращает пути к файлам."""
    out_dir.mkdir(parents=True, exist_ok=True)
    csv_path = out_dir / f"report_{on_date.isoformat()}.csv"
    txt_path = out_dir / f"report_{on_date.isoformat()}.txt"
    write_csv(report, csv_path)
    txt_path.write_text(render_console(report, on_date), encoding="utf-8")
    return {"csv": csv_path, "txt": txt_path}
