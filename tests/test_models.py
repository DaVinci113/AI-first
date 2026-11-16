"""Тесты на доменные правила: деньги платёжжа на дату, статусы работ."""

from __future__ import annotations

import datetime as dt
from decimal import Decimal

from contract_report.models import Contract, Payment, Work

D = Decimal
DATE = dt.date(2026, 11, 10)


def make_payment(status: str, amount: str, created="2026-09-01", paid=None, refunded=None, work_id=None) -> Payment:
    return Payment(
        payment_id="P-1",
        contract_id="D-1",
        work_id=work_id,
        purpose="тест",
        amount=D(amount),
        status=status,
        created_at=dt.date.fromisoformat(created),
        paid_at=dt.date.fromisoformat(paid) if paid else None,
        refunded_at=dt.date.fromisoformat(refunded) if refunded else None,
    )


class TestPaidMoney:
    def test_paid_before_date_counts(self):
        p = make_payment("paid", "100.00", paid="2026-09-01")
        assert p.paid_money(DATE) == D("100.00")

    def test_paid_after_date_ignored(self):
        p = make_payment("paid", "100.00", created="2026-11-12", paid="2026-11-12")
        assert p.paid_money(DATE) == D("0.00")

    def test_paid_exactly_on_date_counts(self):
        # платёж в дату отчёта: деньги ушли, считаем их ушедшими
        p = make_payment("paid", "100.00", created="2026-11-10", paid="2026-11-10")
        assert p.paid_money(DATE) == D("100.00")

    def test_queued_is_zero(self):
        p = make_payment("queued", "150000.00")
        assert p.paid_money(DATE) == D("0.00")

    def test_refunded_before_date_is_zero(self):
        p = make_payment("refunded", "50000.00", paid="2026-09-02", refunded="2026-09-10")
        assert p.paid_money(DATE) == D("0.00")

    def test_refunded_after_date_still_paid_on_date(self):
        # возврат случился после даты отчёта: на дату деньги числились уплаченными
        p = make_payment("refunded", "50000.00", paid="2026-09-02", refunded="2026-11-20")
        assert p.paid_money(DATE) == D("50000.00")

    def test_paid_without_paid_at_uses_created(self):
        # страхуемся: paid без даты оплаты считаем по created_at
        p = make_payment("paid", "10.00", created="2026-09-01", paid=None)
        assert p.paid_money(DATE) == D("10.00")


class TestWorkStatus:
    def make_work(self, status: str, completed=None, cancelled=None) -> Work:
        return Work(
            work_id="W-1",
            contract_id="D-1",
            title="работа",
            price=D("100.00"),
            status=status,
            completed_at=dt.date.fromisoformat(completed) if completed else None,
            cancelled_at=dt.date.fromisoformat(cancelled) if cancelled else None,
        )

    def test_cancelled_before_date_not_active(self):
        w = self.make_work("cancelled", cancelled="2026-10-12")
        assert w.is_active(DATE) is False

    def test_cancelled_after_date_still_active(self):
        w = self.make_work("cancelled", cancelled="2026-11-20")
        assert w.is_active(DATE) is True

    def test_done_after_date_downgraded_to_planned(self):
        # в выгрузке статус «на момент выгрузки»; на 10.11 работа ещё не принята
        w = self.make_work("done", completed="2026-11-11")
        assert w.effective_status(DATE) == "planned"

    def test_done_before_date_stays_done(self):
        w = self.make_work("done", completed="2026-10-05")
        assert w.effective_status(DATE) == "done"

    def test_planned_stays_planned(self):
        w = self.make_work("planned")
        assert w.effective_status(DATE) == "planned"


class TestContractModel:
    def test_simple_fields(self):
        c = Contract("D-1", "Студия", D("600000.00"), dt.date(2026, 8, 25))
        assert c.contract_id == "D-1"
        assert c.amount == D("600000.00")
