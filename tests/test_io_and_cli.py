"""Тесты чтения CSV (валидация, ошибки) и CLI на реальных данных из data/."""

from __future__ import annotations

import datetime as dt
import pathlib

import pytest

from contract_report.cli import main as cli_main
from contract_report.io_csv import (
    DataError,
    check_references,
    load_contracts,
    load_payments,
    load_works,
)
from contract_report.report import build_report

DATA = pathlib.Path(__file__).resolve().parent.parent / "data"
DATE = dt.date(2026, 11, 10)


@pytest.fixture()
def real_data():
    contracts = load_contracts(DATA / "contracts.csv")
    works = load_works(DATA / "works.csv")
    payments = load_payments(DATA / "payments.csv")
    check_references(contracts, works, payments)
    return contracts, works, payments


class TestRealData:
    """Интеграционный тест на данных задания: контрольные цифры на 10.11.2026."""

    def test_report_on_2026_11_10(self, real_data):
        contracts, works, payments = real_data
        report = build_report(contracts, works, payments, DATE)
        by_cid = {c.contract_id: c for c in report}
        by_wid = {w.work_id: w for c in report for w in c.works}

        # D-1: выплачено 300000 (аванс) + 15000 (материалы W-14) = 315000
        d1 = by_cid["D-1"]
        assert d1.paid == __import__("decimal").Decimal("315000.00")
        assert d1.remaining == __import__("decimal").Decimal("285000.00")
        assert d1.unallocated_paid == 0

        # W-14: цена 100000, привязанный платёж 15000 + распределённый аванс 85000
        w14 = by_wid["W-14"]
        assert w14.paid == __import__("decimal").Decimal("100000.00")
        assert w14.remaining == 0

        # W-23 (принята 11.11 - позже даты): статус planned;
        # получила остаток непривязанных денег: 75000 - 20000 - 30000 = 25000
        w23 = by_wid["W-23"]
        assert w23.status == "planned"
        assert w23.paid == __import__("decimal").Decimal("25000.00")
        assert w23.remaining == __import__("decimal").Decimal("15000.00")

        # D-2: 45000 + 25000 + 5000 = 75000; P-8 (20k, 12.11) не в счёт
        d2 = by_cid["D-2"]
        assert d2.paid == __import__("decimal").Decimal("75000.00")
        assert d2.remaining == __import__("decimal").Decimal("15000.00")

        # W-13 отменена 12.10 - не в отчёте
        assert "W-13" not in by_wid

    def test_report_on_2026_11_30(self, real_data):
        contracts, works, payments = real_data
        report = build_report(contracts, works, payments, dt.date(2026, 11, 30))
        by_cid = {c.contract_id: c for c in report}
        by_wid = {w.work_id: w for c in report for w in c.works}

        d2 = by_cid["D-2"]
        assert d2.paid == __import__("decimal").Decimal("95000.00")  # + P-8 20000
        w23 = by_wid["W-23"]
        assert w23.status == "done"
        assert w23.paid == __import__("decimal").Decimal("40000.00")

    def test_w11_fully_paid_on_nov10(self, real_data):
        # W-11 закрыта целиком авансом
        contracts, works, payments = real_data
        report = build_report(contracts, works, payments, DATE)
        w11 = {w.work_id: w for c in report for w in c.works}["W-11"]
        assert w11.paid == __import__("decimal").Decimal("100000.00")


class TestValidation:
    def _tmp_csv(self, tmp_path, name, header, rows):
        p = tmp_path / name
        p.write_text("\n".join([",".join(header)] + rows) + "\n", encoding="utf-8")
        return p

    def test_bad_date(self, tmp_path):
        p = self._tmp_csv(
            tmp_path, "contracts.csv",
            ["contract_id", "contractor", "amount", "signed_at"],
            ["D-1,Иванов,100.00,2026-13-45"],
        )
        with pytest.raises(DataError, match="signed_at"):
            load_contracts(p)

    def test_bad_money(self, tmp_path):
        p = self._tmp_csv(
            tmp_path, "contracts.csv",
            ["contract_id", "contractor", "amount", "signed_at"],
            ["D-1,Иванов,abc,2026-09-01"],
        )
        with pytest.raises(DataError, match="amount"):
            load_contracts(p)

    def test_bad_status(self, tmp_path):
        p = self._tmp_csv(
            tmp_path, "works.csv",
            ["work_id", "contract_id", "title", "price", "status", "completed_at", "cancelled_at"],
            ["W-1,D-1,тест,100.00,unknown,, "],
        )
        with pytest.raises(DataError, match="status"):
            load_works(p)

    def test_unknown_contract_reference(self, tmp_path):
        contracts = self._tmp_csv(
            tmp_path, "contracts.csv",
            ["contract_id", "contractor", "amount", "signed_at"],
            ["D-1,Иванов,100.00,2026-09-01"],
        )
        works = self._tmp_csv(
            tmp_path, "works.csv",
            ["work_id", "contract_id", "title", "price", "status", "completed_at", "cancelled_at"],
            ["W-1,D-9,тест,100.00,planned,,"],
        )
        payments = self._tmp_csv(
            tmp_path, "payments.csv",
            ["payment_id", "contract_id", "work_id", "purpose", "amount", "status",
             "created_at", "paid_at", "refunded_at"],
            ["P-1,D-1,,аванс,50.00,paid,2026-09-01,2026-09-01,"],
        )
        with pytest.raises(DataError, match="неизвестный договор"):
            check_references(load_contracts(contracts), load_works(works), load_payments(payments))

    def test_payment_work_from_other_contract(self, tmp_path):
        contracts = self._tmp_csv(
            tmp_path, "contracts.csv",
            ["contract_id", "contractor", "amount", "signed_at"],
            ["D-1,Иванов,100.00,2026-09-01", "D-2,Петров,200.00,2026-09-01"],
        )
        works = self._tmp_csv(
            tmp_path, "works.csv",
            ["work_id", "contract_id", "title", "price", "status", "completed_at", "cancelled_at"],
            ["W-1,D-2,тест,100.00,planned,,"],
        )
        payments = self._tmp_csv(
            tmp_path, "payments.csv",
            ["payment_id", "contract_id", "work_id", "purpose", "amount", "status",
             "created_at", "paid_at", "refunded_at"],
            ["P-1,D-1,W-1,аванс,50.00,paid,2026-09-01,2026-09-01,"],
        )
        with pytest.raises(DataError, match="другого договора"):
            check_references(load_contracts(contracts), load_works(works), load_payments(payments))

    def test_missing_file(self, tmp_path):
        with pytest.raises(DataError, match="не найден"):
            load_contracts(tmp_path / "nope.csv")

    def test_missing_header(self, tmp_path):
        p = tmp_path / "contracts.csv"
        p.write_text("a,b,c,d\nD-1,Иванов,100.00,2026-09-01\n", encoding="utf-8")
        with pytest.raises(DataError, match="заголовок"):
            load_contracts(p)


class TestCli:
    def test_run_on_real_data(self, tmp_path, capsys, real_data):
        rc = cli_main([
            "--data", str(DATA),
            "--date", "2026-11-10",
            "--out", str(tmp_path),
            "--no-console",
        ])
        assert rc == 0
        out = tmp_path / "report_2026-11-10.csv"
        assert out.exists()
        text = out.read_text(encoding="utf-8-sig")
        assert "W-14" in text
        assert "315000.00" in text
        captured = capsys.readouterr()
        assert "CSV:" in captured.out

    def test_bad_date_argument(self, tmp_path):
        with pytest.raises(SystemExit):
            cli_main(["--data", str(DATA), "--date", "10.11.2026"])

    def test_error_exit_code_on_broken_data(self, tmp_path):
        rc = cli_main(["--data", str(tmp_path), "--date", "2026-11-10"])
        assert rc == 2
