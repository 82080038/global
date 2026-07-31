"""Indonesia stock tax calculator — adaptasi dari pasar_modal/src/trading/tax_calculator.py.

Reference: PASAR_MODAL_KNOWLEDGE_BASE.md Section 11.13
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass
class TaxRates:
    """Konfigurasi tarif pajak Indonesia."""

    dividend_tax_rate: float = 0.10
    transaction_tax_rate: float = 0.001
    broker_fee_rate: float = 0.002
    clearing_fee_rate: float = 0.0003
    custody_fee_rate: float = 0.0001


@dataclass
class TransactionCostBreakdown:
    """Rincian biaya transaksi."""

    gross_amount: float
    broker_fee: float
    clearing_fee: float
    custody_fee: float
    transaction_tax: float
    total_cost: float
    net_amount: float


@dataclass
class DividendTaxResult:
    """Hasil perhitungan pajak dividen."""

    gross_dividend: float
    dividend_tax: float
    net_dividend: float
    tax_rate: float


@dataclass
class TradeResult:
    """Hasil perhitungan trade dengan pajak dan biaya."""

    entry_price: float
    exit_price: float
    position_size: int
    gross_pnl: float
    buy_costs: TransactionCostBreakdown
    sell_costs: TransactionCostBreakdown
    transaction_tax: float
    net_pnl: float
    net_pnl_pct: float


def calculate_buy_costs(
    price: float,
    position_size: int,
    rates: Optional[TaxRates] = None,
) -> TransactionCostBreakdown:
    """Hitung biaya pembelian saham."""
    if rates is None:
        rates = TaxRates()

    gross_amount = price * position_size
    broker_fee = gross_amount * rates.broker_fee_rate
    clearing_fee = gross_amount * rates.clearing_fee_rate
    custody_fee = gross_amount * rates.custody_fee_rate
    transaction_tax = 0.0

    total_cost = broker_fee + clearing_fee + custody_fee + transaction_tax
    net_amount = gross_amount + total_cost

    return TransactionCostBreakdown(
        gross_amount=gross_amount,
        broker_fee=broker_fee,
        clearing_fee=clearing_fee,
        custody_fee=custody_fee,
        transaction_tax=transaction_tax,
        total_cost=total_cost,
        net_amount=net_amount,
    )


def calculate_sell_costs(
    price: float,
    position_size: int,
    rates: Optional[TaxRates] = None,
) -> TransactionCostBreakdown:
    """Hitung biaya penjualan saham."""
    if rates is None:
        rates = TaxRates()

    gross_amount = price * position_size
    broker_fee = gross_amount * rates.broker_fee_rate
    clearing_fee = gross_amount * rates.clearing_fee_rate
    custody_fee = gross_amount * rates.custody_fee_rate
    transaction_tax = gross_amount * rates.transaction_tax_rate

    total_cost = broker_fee + clearing_fee + custody_fee + transaction_tax
    net_amount = gross_amount - total_cost

    return TransactionCostBreakdown(
        gross_amount=gross_amount,
        broker_fee=broker_fee,
        clearing_fee=clearing_fee,
        custody_fee=custody_fee,
        transaction_tax=transaction_tax,
        total_cost=total_cost,
        net_amount=net_amount,
    )


def calculate_dividend_tax(
    dividend_per_share: float,
    position_size: int,
    rates: Optional[TaxRates] = None,
) -> DividendTaxResult:
    """Hitung pajak dividen."""
    if rates is None:
        rates = TaxRates()

    gross_dividend = dividend_per_share * position_size
    dividend_tax = gross_dividend * rates.dividend_tax_rate
    net_dividend = gross_dividend - dividend_tax

    return DividendTaxResult(
        gross_dividend=gross_dividend,
        dividend_tax=dividend_tax,
        net_dividend=net_dividend,
        tax_rate=rates.dividend_tax_rate,
    )


def calculate_trade_result(
    entry_price: float,
    exit_price: float,
    position_size: int,
    rates: Optional[TaxRates] = None,
) -> TradeResult:
    """Hitung hasil trade lengkap dengan pajak dan biaya."""
    if rates is None:
        rates = TaxRates()

    buy_costs = calculate_buy_costs(entry_price, position_size, rates)
    sell_costs = calculate_sell_costs(exit_price, position_size, rates)

    gross_pnl = (exit_price - entry_price) * position_size
    transaction_tax = sell_costs.transaction_tax
    net_pnl = sell_costs.net_amount - buy_costs.net_amount
    net_pnl_pct = (net_pnl / buy_costs.net_amount) * 100 if buy_costs.net_amount > 0 else 0.0

    return TradeResult(
        entry_price=entry_price,
        exit_price=exit_price,
        position_size=position_size,
        gross_pnl=gross_pnl,
        buy_costs=buy_costs,
        sell_costs=sell_costs,
        transaction_tax=transaction_tax,
        net_pnl=net_pnl,
        net_pnl_pct=net_pnl_pct,
    )


def calculate_effective_rate(
    entry_price: float,
    exit_price: float,
    position_size: int,
    rates: Optional[TaxRates] = None,
) -> dict[str, float]:
    """Hitung effective rate (biaya total sebagai persentase dari nilai transaksi)."""
    if rates is None:
        rates = TaxRates()

    buy_costs = calculate_buy_costs(entry_price, position_size, rates)
    sell_costs = calculate_sell_costs(exit_price, position_size, rates)

    total_transaction_value = buy_costs.gross_amount + sell_costs.gross_amount
    total_costs = buy_costs.total_cost + sell_costs.total_cost

    effective_rate = (total_costs / total_transaction_value) * 100 if total_transaction_value > 0 else 0.0

    return {
        "buy_effective_rate": (buy_costs.total_cost / buy_costs.gross_amount) * 100
        if buy_costs.gross_amount > 0
        else 0.0,
        "sell_effective_rate": (sell_costs.total_cost / sell_costs.gross_amount) * 100
        if sell_costs.gross_amount > 0
        else 0.0,
        "overall_effective_rate": effective_rate,
        "total_buy_costs": buy_costs.total_cost,
        "total_sell_costs": sell_costs.total_cost,
        "total_costs": total_costs,
    }
