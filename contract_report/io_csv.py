"""Чтение CSV из data/ с валидацией.

Ожидаем ошибки в данных не молча: битую строку лучше показать пользователю
с номером строки и причиной, чем получить тихо неверный отчёт.
"""

from __future__ import annotations

import csv
import datetime as dt
import pathlib
from decimal import Decimal, InvalidOperation
from typing import Iterable, Iterator, Sequence

from .models import Contract, Payment, Work

DataError = ValueError  # читаемое имя для вызывающего кода


def _fail(path: pathlib.Path, line_no: int, message: str) -> DataError:
    return DataError(f"{path.name}, строка {line_no}: {message}")


def _parse_date(path: pathlib.Path, line_no: int, raw: str, field_name: str) -> dt.date | None:
    raw = raw.strip()
    if not raw:
        return None
    try:
        return dt.date.fromisoformat(raw)
    except ValueError:
        raise _fail(path, line_no, f"поле {field_name}: неверная дата '{raw}'") from None


def _parse_money(path: pathlib.Path, line_no: int, raw: str, field_name: str) -> Decimal:
    try:
        return Decimal(raw.strip())
    except InvalidOperation:
        raise _fail(path, line_no, f"поле {field_name}: неверная сумма '{raw}'") from None


def _parse_status(
    path: pathlib.Path, line_no: int, raw: str, allowed: Sequence[str], field_name: str
) -> str:
    value = raw.strip()
    if value not in allowed:
        raise _fail(
            path, line_no, f"поле {field_name}: неизвестный статус '{value}' (ожидались {allowed})"
        )
    return value


def _check_invariants(path: pathlib.Path, line_no: int, message: str) -> None:
    # отдельная функция, чтобы вызовы читались одинаково
    raise _fail(path, line_no, message)


def _rows(path: pathlib.Path, expected_header: list[str]) -> Iterator[tuple[int, dict[str, str]]]:
    """Читает CSV и отдаёт (номер строки данных, словарь колонок)."""
    if not path.exists():
        raise DataError(f"файл не найден: {path}")
    with path.open(encoding="utf-8-sig", newline="") as fh:
        reader = csv.DictReader(fh)
        if reader.fieldnames is None:
            raise DataError(f"{path.name}: файл пуст")
        if reader.fieldnames != expected_header:
            raise DataError(
                f"{path.name}: заголовок {reader.fieldnames} не совпал с ожидаемым {expected_header}"
            )
        for line_no, row in enumerate(reader, start=2):  # 1 - заголовок
            yield line_no, row


def load_contracts(path: pathlib.Path) -> list[Contract]:
    contracts: list[Contract] = []
    for line_no, row in _rows(
        path, ["contract_id", "contractor", "amount", "signed_at"]
    ):
        signed_at = _parse_date(path, line_no, row["signed_at"], "signed_at")
        if signed_at is None:
            raise _fail(path, line_no, "поле signed_at: значение обязательно, но пусто")
        contracts.append(
            Contract(
                contract_id=row["contract_id"].strip(),
                contractor=row["contractor"].strip(),
                amount=_parse_money(path, line_no, row["amount"], "amount"),
                signed_at=signed_at,
            )
        )
    return contracts


def load_works(path: pathlib.Path) -> list[Work]:
    works: list[Work] = []
    for line_no, row in _rows(
        path, ["work_id", "contract_id", "title", "price", "status", "completed_at", "cancelled_at"]
    ):
        status = _parse_status(path, line_no, row["status"], ["planned", "done", "cancelled"], "status")
        completed = _parse_date(path, line_no, row["completed_at"], "completed_at")
        cancelled = _parse_date(path, line_no, row["cancelled_at"], "cancelled_at")
        if status == "done" and completed is None:
            _check_invariants(path, line_no, "работа done, но completed_at пуст")
        if status == "cancelled" and cancelled is None:
            _check_invariants(path, line_no, "работа cancelled, но cancelled_at пуст")
        works.append(
            Work(
                work_id=row["work_id"].strip(),
                contract_id=row["contract_id"].strip(),
                title=row["title"].strip(),
                price=_parse_money(path, line_no, row["price"], "price"),
                status=status,
                completed_at=completed,
                cancelled_at=cancelled,
            )
        )
    return works


def load_payments(path: pathlib.Path) -> list[Payment]:
    payments: list[Payment] = []
    for line_no, row in _rows(
        path,
        [
            "payment_id",
            "contract_id",
            "work_id",
            "purpose",
            "amount",
            "status",
            "created_at",
            "paid_at",
            "refunded_at",
        ],
    ):
        status = _parse_status(path, line_no, row["status"], ["paid", "queued", "refunded"], "status")
        work_id = row["work_id"].strip() or None
        paid_at = _parse_date(path, line_no, row["paid_at"], "paid_at")
        refunded_at = _parse_date(path, line_no, row["refunded_at"], "refunded_at")
        if status == "paid" and paid_at is None:
            _check_invariants(path, line_no, "платёж paid, но paid_at пуст")
        if status == "refunded" and refunded_at is None:
            _check_invariants(path, line_no, "платёж refunded, но refunded_at пуст")
        created_at = _parse_date(path, line_no, row["created_at"], "created_at")
        if created_at is None:
            raise _fail(path, line_no, "поле created_at: значение обязательно, но пусто")
        payments.append(
            Payment(
                payment_id=row["payment_id"].strip(),
                contract_id=row["contract_id"].strip(),
                work_id=work_id,
                purpose=row["purpose"].strip(),
                amount=_parse_money(path, line_no, row["amount"], "amount"),
                status=status,
                created_at=created_at,
                paid_at=paid_at,
                refunded_at=refunded_at,
            )
        )
    return payments


def check_references(
    contracts: Iterable[Contract], works: Iterable[Work], payments: Iterable[Payment]
) -> None:
    """Проверяет связи между файлами: work.contract_id и payment.contract_id/work_id."""
    contract_ids = {c.contract_id for c in contracts}
    seen_contracts: set[str] = set()
    for c in contracts:
        if c.contract_id in seen_contracts:
            raise DataError(f"contracts.csv: дубликат contract_id {c.contract_id}")
        seen_contracts.add(c.contract_id)
    work_ids: set[str] = set()
    work_ids_by_contract: dict[str, set[str]] = {}
    for w in works:
        if w.contract_id not in contract_ids:
            raise DataError(f"works.csv: работа {w.work_id} ссылается на неизвестный договор {w.contract_id}")
        work_ids_by_contract.setdefault(w.contract_id, set()).add(w.work_id)
        if w.work_id in work_ids:
            raise DataError(f"works.csv: дубликат work_id {w.work_id}")
        work_ids.add(w.work_id)
    for p in payments:
        if p.contract_id not in contract_ids:
            raise DataError(
                f"payments.csv: платёж {p.payment_id} ссылается на неизвестный договор {p.contract_id}"
            )
        if p.work_id is not None:
            if p.work_id not in work_ids:
                raise DataError(
                    f"payments.csv: платёж {p.payment_id} ссылается на неизвестную работу {p.work_id}"
                )
            if p.work_id not in work_ids_by_contract.get(p.contract_id, set()):
                raise DataError(
                    f"payments.csv: платёж {p.payment_id} (договор {p.contract_id}) "
                    f"ссылается на работу {p.work_id} другого договора"
                )
    seen_payments: set[str] = set()
    for p in payments:
        if p.payment_id in seen_payments:
            raise DataError(f"payments.csv: дубликат payment_id {p.payment_id}")
        seen_payments.add(p.payment_id)
