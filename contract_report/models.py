"""Доменные модели: договоры, работы, платежи.

Все денежные величины - Decimal, все даты - datetime.date.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field
from decimal import Decimal


Money = Decimal


@dataclass(frozen=True, slots=True)
class Contract:
    """Договор с подрядчиком."""

    contract_id: str
    contractor: str
    amount: Money
    signed_at: dt.date


@dataclass(frozen=True, slots=True)
class Work:
    """Работа в рамках договора."""

    work_id: str
    contract_id: str
    title: str
    price: Money
    status: str  # planned | done | cancelled
    completed_at: dt.date | None
    cancelled_at: dt.date | None

    @property
    def is_cancelled(self) -> bool:
        return self.status == "cancelled"

    def is_active(self, on_date: dt.date) -> bool:
        """Работа входит в отчёт на дату: не отменена или отменена позднее даты отчёта."""
        if self.status != "cancelled":
            return True
        assert self.cancelled_at is not None  # инвариант данных
        return self.cancelled_at > on_date

    def effective_status(self, on_date: dt.date) -> str:
        """Статус на дату отчёта (в файлах статус - «на момент выгрузки»).

        Работу, принятую после даты отчёта, на эту дату считаем ещё
        незавершённой: обязательство платить за неё ещё не наступило.
        """
        if self.status == "done" and self.completed_at is not None and self.completed_at > on_date:
            return "planned"
        return self.status


@dataclass(frozen=True, slots=True)
class Payment:
    """Платёж по договору, возможно с привязкой к работе."""

    payment_id: str
    contract_id: str
    work_id: str | None
    purpose: str
    amount: Money
    status: str  # paid | queued | refunded
    created_at: dt.date
    paid_at: dt.date | None
    refunded_at: dt.date | None

    def paid_money(self, on_date: dt.date) -> Money:
        """Сколько денег фактически ушло подрядчику и не вернулось, на дату.

        - paid: ушли (учитываем paid_at, если он есть, иначе created_at);
        - queued: ещё не ушли - 0;
        - refunded: ушли, потом вернулись - итог 0,
          при этом возврат мог случиться уже после даты отчёта:
          тогда на дату отчёта деньги ещё числились уплаченными.
        """
        if self.status == "queued":
            return Money("0.00")
        if self.status == "refunded":
            assert self.refunded_at is not None  # инвариант данных
            if self.refunded_at <= on_date:
                return Money("0.00")
            # возврат был позже даты отчёта: на дату отчёта деньги числились уплаченными
            return self._paid_by(on_date)
        # paid
        return self._paid_by(on_date)

    def _paid_by(self, on_date: dt.date) -> Money:
        """Деньги ушли подрядчику не позднее on_date."""
        when = self.paid_at or self.created_at
        return self.amount if when <= on_date else Money("0.00")


@dataclass(slots=True)
class WorkRow:
    """Строка отчёта по работе."""

    work_id: str
    contract_id: str
    title: str
    status: str
    price: Money
    paid: Money = Money("0.00")
    allocated: Money = Money("0.00")  # сколько непривязанных денег распределено на работу
    remaining: Money = Money("0.00")

    def __post_init__(self) -> None:
        self.remaining = self.price - self.paid

    def add_allocated(self, amount: Money) -> None:
        self.paid += amount
        self.allocated += amount
        self.remaining = self.price - self.paid


@dataclass(slots=True)
class ContractRow:
    """Итоговая строка отчёта по договору."""

    contract_id: str
    contractor: str
    contract_amount: Money
    works_price: Money = Money("0.00")  # сумма цен активных работ
    paid: Money = Money("0.00")
    remaining: Money = Money("0.00")  # contract_amount - paid
    works: list[WorkRow] = field(default_factory=list)
    unallocated_paid: Money = Money("0.00")  # выплачено сверх цен работ (или в договор без активных работ)

    def add_work(self, work: WorkRow) -> None:
        self.works.append(work)
        self.works_price += work.price
