from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from app.database.models import TicketBenefit
from app.database.repository import SalaryConfigRepository, TicketBenefitRepository
from app.services.date_service import month_range
from app.services.financial_cycle_service import FinancialCycle, FinancialCycleService
from app.utils.money import ZERO, to_money


PAYMENT_MONEY = "money"
PAYMENT_TICKET_ALIMENTACAO = "ticket_alimentacao"
PAYMENT_TICKET_REFEICAO = "ticket_refeicao"

BENEFIT_ALIMENTACAO = "alimentacao"
BENEFIT_REFEICAO = "refeicao"

PAYMENT_TO_BENEFIT = {
    PAYMENT_TICKET_ALIMENTACAO: BENEFIT_ALIMENTACAO,
    PAYMENT_TICKET_REFEICAO: BENEFIT_REFEICAO,
}

BENEFIT_TO_PAYMENT = {
    BENEFIT_ALIMENTACAO: PAYMENT_TICKET_ALIMENTACAO,
    BENEFIT_REFEICAO: PAYMENT_TICKET_REFEICAO,
}

BENEFIT_LABELS = {
    BENEFIT_ALIMENTACAO: "Ticket Alimentacao",
    BENEFIT_REFEICAO: "Ticket Refeicao",
}


class TicketBalanceError(ValueError):
    pass


@dataclass(frozen=True)
class TicketSummaryItem:
    benefit_type: str
    payment_source: str
    label: str
    configured_amount: Decimal
    current_balance: Decimal
    spent: Decimal


class TicketService:
    def __init__(
        self,
        repository: TicketBenefitRepository,
        salary_config_repository: SalaryConfigRepository | None = None,
    ):
        self.repository = repository
        self.salary_config_repository = salary_config_repository

    def configure_benefit(
        self,
        user_id: int,
        benefit_type: str,
        amount: Decimal | float | int | str,
        target_date: date | None = None,
    ) -> TicketBenefit:
        self._validate_benefit_type(benefit_type)
        cycle = self._current_cycle(user_id, target_date)
        return self.repository.upsert(
            user_id=user_id,
            benefit_type=benefit_type,
            configured_amount=amount,
            current_balance=amount,
            cycle_start=cycle.start_day,
            is_active=True,
        )

    def active_payment_sources(self, user_id: int, target_date: date | None = None) -> list[str]:
        self.refresh_cycle_balances(user_id, target_date)
        return [
            BENEFIT_TO_PAYMENT[benefit.benefit_type]
            for benefit in self.repository.list_by_user(user_id)
            if benefit.benefit_type in BENEFIT_TO_PAYMENT
        ]

    def debit(self, user_id: int, payment_source: str, amount: Decimal | float | int | str) -> None:
        if payment_source == PAYMENT_MONEY:
            return
        benefit_type = PAYMENT_TO_BENEFIT.get(payment_source)
        if not benefit_type:
            raise TicketBalanceError("Origem de pagamento invalida.")

        self.refresh_cycle_balances(user_id)
        benefit = self.repository.get_by_type(user_id, benefit_type)
        if not benefit or not benefit.is_active:
            raise TicketBalanceError(f"{BENEFIT_LABELS[benefit_type]} nao esta cadastrado.")

        amount_money = to_money(amount)
        if benefit.current_balance < amount_money:
            raise TicketBalanceError(
                f"Saldo insuficiente em {BENEFIT_LABELS[benefit_type]}. "
                f"Saldo atual: R$ {benefit.current_balance:.2f}".replace(".", ",")
            )

        self.repository.update_balance(
            user_id=user_id,
            benefit_type=benefit_type,
            current_balance=benefit.current_balance - amount_money,
        )

    def refresh_cycle_balances(self, user_id: int, target_date: date | None = None) -> None:
        cycle = self._current_cycle(user_id, target_date)
        for benefit in self.repository.list_by_user(user_id):
            if benefit.cycle_start == cycle.start_day:
                continue
            self.repository.update_balance(
                user_id=user_id,
                benefit_type=benefit.benefit_type,
                current_balance=benefit.configured_amount,
                cycle_start=cycle.start_day,
            )

    def summary_by_period(
        self,
        user_id: int,
        spent_by_payment_source: dict[str, Decimal],
        target_date: date | None = None,
    ) -> list[TicketSummaryItem]:
        self.refresh_cycle_balances(user_id, target_date)
        items = []
        for benefit in self.repository.list_by_user(user_id):
            payment_source = BENEFIT_TO_PAYMENT.get(benefit.benefit_type)
            if not payment_source:
                continue
            items.append(
                TicketSummaryItem(
                    benefit_type=benefit.benefit_type,
                    payment_source=payment_source,
                    label=BENEFIT_LABELS[benefit.benefit_type],
                    configured_amount=to_money(benefit.configured_amount),
                    current_balance=to_money(benefit.current_balance),
                    spent=to_money(spent_by_payment_source.get(payment_source, ZERO)),
                )
            )
        return items

    def _current_cycle(self, user_id: int, target_date: date | None = None) -> FinancialCycle:
        target_date = target_date or date.today()
        if self.salary_config_repository:
            return FinancialCycleService(self.salary_config_repository).current_cycle(user_id, target_date)
        start_date, end_date = month_range(target_date)
        return FinancialCycle(start_date=start_date, end_date=end_date, is_salary_cycle=False)

    @staticmethod
    def _validate_benefit_type(benefit_type: str) -> None:
        if benefit_type not in BENEFIT_TO_PAYMENT:
            raise ValueError("Tipo de ticket invalido.")
