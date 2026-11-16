"""Расчёт отчёта: сколько выплачено по каждой работе и договору на дату.

Ключевая идея: платёж, привязанный к работе, засчитывается в работу напрямую.
Платёж без привязки - это деньги «по договору в целом»: бухгалтер платит
авансом и остатками. Такие деньги распределяем на работы в порядке,
который имеет смысл для бизнеса (см. DECISIONS.md).
"""

from __future__ import annotations

import datetime as dt
from decimal import Decimal

from .models import Contract, ContractRow, Payment, Work, WorkRow

Money = Decimal

# Порядок распределения непривязанных платежей на работы:
# 1) принятые на дату отчёта работы - за них уже есть обязанность платить;
# 2) запланированные - аванс уходит в счёт будущих работ;
# внутри группы - в порядке появления работ в works.csv.
_STATUS_ORDER = {"done": 0, "planned": 1}


def build_report(
    contracts: list[Contract],
    works: list[Work],
    payments: list[Payment],
    on_date: dt.date,
) -> list[ContractRow]:
    """Строит отчёт на дату.

    Алгоритм:
    1. Для каждого платёжа считаем «фактически уплаченные деньги» на дату
       (paid, у которого paid_at <= on_date; refunded до on_date - ноль;
       queued - ноль).
    2. Платёж с work_id идёт в свою работу напрямую.
    3. Платёж без work_id распределяется на работы договора в порядке:
       сначала done, потом planned (внутри - как в works.csv), не больше
       цены каждой работы.
    4. Остаток сверх сумм работ показываем отдельной строкой «без привязки».
    """
    works_by_contract: dict[str, list[Work]] = {}
    for w in works:
        works_by_contract.setdefault(w.contract_id, []).append(w)

    report: list[ContractRow] = []

    for contract in contracts:
        row = ContractRow(
            contract_id=contract.contract_id,
            contractor=contract.contractor,
            contract_amount=contract.amount,
        )

        contract_works = works_by_contract.get(contract.contract_id, [])

        # Строки по работам: активные на дату отчёта.
        # Статус берём «на дату», а не «на момент выгрузки».
        work_rows: list[WorkRow] = []
        for w in contract_works:
            if not w.is_active(on_date):
                continue  # отменённые до даты отчёта работы в отчёт не входят
            work_rows.append(
                WorkRow(
                    work_id=w.work_id,
                    contract_id=w.contract_id,
                    title=w.title,
                    status=w.effective_status(on_date),
                    price=w.price,
                )
            )
        for wr in work_rows:
            row.add_work(wr)  # добавляет в список и копит works_price

        # 1-2. Платежи, привязанные к работам.
        # Платёж за работу, отменённую до даты отчёта, в другие работы
        # не перекладываем: деньги ушли за неё, показываем «сверх работ».
        by_work_id = {wr.work_id: wr for wr in work_rows}
        unbound_pool = Money("0.00")  # деньги по договору без привязки
        paid_beyond_works = Money("0.00")  # за отменённые работы + нераспределённый остаток

        contract_payments = [
            p for p in payments if p.contract_id == contract.contract_id
        ]
        # стабильный порядок: как в payments.csv
        contract_payments.sort(key=lambda p: p.payment_id)

        for payment in contract_payments:
            money = payment.paid_money(on_date)
            if money == 0:
                continue
            target = by_work_id.get(payment.work_id) if payment.work_id else None
            if target is not None:
                target.paid += money
                target.remaining = target.price - target.paid
            elif payment.work_id is not None:
                # привязан к работе, которой нет в отчёте на эту дату (отменена)
                paid_beyond_works += money
            else:
                unbound_pool += money

        # 3. Распределяем непривязанные деньги на работы.
        leftover = _allocate_unallocated(work_rows, unbound_pool)
        row.unallocated_paid = paid_beyond_works + leftover

        # Итоги по договору: всё, что реально ушло подрядчику на дату.
        for wr in work_rows:
            row.paid += wr.paid
        row.paid += row.unallocated_paid  # сверх цен работ (за отменённые + нераспределённое)
        row.remaining = contract.amount - row.paid

        report.append(row)

    return report


def _allocate_unallocated(work_rows: list[WorkRow], total: Money) -> Money:
    """Распределяет total на работы; возвращает нераспределённый остаток.

    Порядок: done -> planned, внутри группы - порядок works.csv.
    На каждую работу - не больше её цены (остатка к оплате).
    """
    if total <= 0:
        return Money("0.00")

    remaining_pool = total
    ordered = sorted(
        enumerate(work_rows),
        key=lambda item: (_STATUS_ORDER.get(item[1].status, 99), item[0]),
    )
    for _, wr in ordered:
        if remaining_pool <= 0:
            break
        free = wr.price - wr.paid
        if free <= 0:
            continue
        take = min(free, remaining_pool)
        wr.add_allocated(take)
        remaining_pool -= take
    return remaining_pool
