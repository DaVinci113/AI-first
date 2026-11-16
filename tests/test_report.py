"""Тесты расчёта отчёта: распределение платежей по работам и итоги."""

from __future__ import annotations

import datetime as dt
from decimal import Decimal

from contract_report.models import Contract, Payment, Work
from contract_report.report import build_report

D = Decimal
DATE = dt.date(2026, 11, 10)


def contract(cid="D-1", amount="600000.00") -> Contract:
    return Contract(cid, "Подрядчик", D(amount), dt.date(2026, 8, 25))


def work(wid, cid="D-1", price="100000.00", status="done", completed="2026-09-20") -> Work:
    return Work(
        work_id=wid,
        contract_id=cid,
        title=f"работа {wid}",
        price=D(price),
        status=status,
        completed_at=dt.date.fromisoformat(completed) if completed else None,
        cancelled_at=None,
    )


def payment(pid, amount, cid="D-1", work_id=None, status="paid",
            created="2026-09-01", paid="2026-09-01", refunded=None) -> Payment:
    return Payment(
        payment_id=pid,
        contract_id=cid,
        work_id=work_id,
        purpose="тест",
        amount=D(amount),
        status=status,
        created_at=dt.date.fromisoformat(created),
        paid_at=dt.date.fromisoformat(paid) if paid else None,
        refunded_at=dt.date.fromisoformat(refunded) if refunded else None,
    )


def by_work(report):
    return {w.work_id: w for c in report for w in c.works}


class TestAllocation:
    def test_unbound_money_fills_done_works_first_in_file_order(self):
        # 250k без привязки: сначала закрываем done-работы по порядку works.csv
        contracts = [contract()]
        works = [
            work("W-1", status="done", completed="2026-09-20"),
            work("W-2", status="done", completed="2026-10-05"),
            work("W-3", status="planned", completed=None),
        ]
        payments = [payment("P-1", "250000.00", work_id=None, paid="2026-09-01")]
        report = build_report(contracts, works, payments, DATE)
        rows = by_work(report)
        assert rows["W-1"].paid == D("100000.00")
        assert rows["W-2"].paid == D("100000.00")
        assert rows["W-3"].paid == D("50000.00")
        assert report[0].paid == D("250000.00")
        assert report[0].remaining == D("350000.00")

    def test_work_bound_payment_goes_to_its_work(self):
        contracts = [contract()]
        works = [work("W-1"), work("W-2", completed="2026-10-05")]
        payments = [payment("P-1", "15000.00", work_id="W-2")]
        report = build_report(contracts, works, payments, DATE)
        rows = by_work(report)
        assert rows["W-1"].paid == D("0.00")
        assert rows["W-2"].paid == D("15000.00")

    def test_bound_payment_overwork_price_shows_in_unallocated(self):
        # за работу заплатили больше цены: излишек не перекладываем на другие работы
        contracts = [contract()]
        works = [work("W-1", price="10000.00"), work("W-2", price="20000.00", completed="2026-10-05")]
        payments = [payment("P-1", "15000.00", work_id="W-1")]
        report = build_report(contracts, works, payments, DATE)
        rows = by_work(report)
        assert rows["W-1"].paid == D("15000.00")
        assert rows["W-2"].paid == D("0.00")
        assert report[0].unallocated_paid == D("0.00")  # весь платёж числится за W-1

    def test_payment_for_cancelled_work_is_not_spread(self):
        # платёж за отменённую до даты работу - «сверх работ», не в другие работы
        contracts = [contract()]
        works = [
            Work("W-1", "D-1", "а", D("50000.00"), "cancelled", None, dt.date(2026, 10, 12)),
            work("W-2", price="50000.00"),
        ]
        payments = [payment("P-1", "30000.00", work_id="W-1")]
        report = build_report(contracts, works, payments, DATE)
        rows = by_work(report)
        assert "W-1" not in rows  # отменённая работа не в отчёте
        assert rows["W-2"].paid == D("0.00")
        assert report[0].unallocated_paid == D("30000.00")
        assert report[0].paid == D("30000.00")

    def test_cancelled_after_date_work_stays_in_report(self):
        contracts = [contract()]
        works = [
            Work("W-1", "D-1", "а", D("50000.00"), "cancelled", None, dt.date(2026, 11, 20)),
        ]
        payments = []
        report = build_report(contracts, works, payments, DATE)
        assert [w.work_id for w in report[0].works] == ["W-1"]

    def test_unbound_money_beyond_work_prices_leftover_shown(self):
        # непривязанных денег больше, чем сумма цен работ: остаток виден отдельно
        contracts = [contract(amount="300000.00")]
        works = [work("W-1", price="100000.00")]
        payments = [payment("P-1", "150000.00", work_id=None)]
        report = build_report(contracts, works, payments, DATE)
        rows = by_work(report)
        assert rows["W-1"].paid == D("100000.00")
        assert report[0].unallocated_paid == D("50000.00")
        assert report[0].paid == D("150000.00")

    def test_contract_without_works(self):
        contracts = [contract(amount="90000.00")]
        payments = [payment("P-1", "45000.00", work_id=None)]
        report = build_report(contracts, [], payments, DATE)
        assert report[0].works == []
        assert report[0].paid == D("45000.00")
        assert report[0].remaining == D("45000.00")
        assert report[0].unallocated_paid == D("45000.00")

    def test_done_after_date_treated_as_planned_in_allocation(self):
        # работа, принятая после даты отчёта, в распределении идёт после done
        contracts = [contract()]
        works = [
            work("W-1", status="done", completed="2026-11-11"),  # принята позже даты
            work("W-2", status="done", completed="2026-09-20"),
        ]
        payments = [payment("P-1", "150000.00", work_id=None)]
        report = build_report(contracts, works, payments, DATE)
        rows = by_work(report)
        assert rows["W-1"].status == "planned"
        assert rows["W-1"].paid == D("50000.00")  # получила только остаток после W-2
        assert rows["W-2"].paid == D("100000.00")

    def test_payment_after_date_excluded(self):
        contracts = [contract()]
        works = [work("W-1")]
        payments = [
            payment("P-1", "20000.00", created="2026-11-12", paid="2026-11-12"),
            payment("P-2", "5000.00", work_id="W-1", created="2026-11-02", paid="2026-11-02"),
        ]
        report = build_report(contracts, works, payments, DATE)
        rows = by_work(report)
        assert rows["W-1"].paid == D("5000.00")
        assert report[0].paid == D("5000.00")


class TestTotals:
    def test_totals_sum(self):
        contracts = [contract()]
        works = [work("W-1"), work("W-2", completed="2026-10-05")]
        payments = [
            payment("P-1", "300000.00", work_id=None),
            payment("P-2", "50000.00", work_id=None, status="refunded",
                    paid="2026-09-02", refunded="2026-09-10"),
        ]
        report = build_report(contracts, works, payments, DATE)
        assert report[0].paid == D("300000.00")
        assert report[0].remaining == D("300000.00")
        assert report[0].works_price == D("200000.00")

    def test_multiple_contracts_independent(self):
        contracts = [contract("D-1"), contract("D-2", amount="90000.00")]
        works = [work("W-1", cid="D-1"), work("W-2", cid="D-2", price="90000.00")]
        payments = [
            payment("P-1", "100000.00", cid="D-1", work_id=None),
            payment("P-2", "45000.00", cid="D-2", work_id=None),
        ]
        report = build_report(contracts, works, payments, DATE)
        by_cid = {c.contract_id: c for c in report}
        assert by_cid["D-1"].paid == D("100000.00")
        assert by_cid["D-2"].paid == D("45000.00")
