from dataclasses import dataclass
from datetime import date, datetime


@dataclass(frozen=True)
class ParsedExpense:
    amount: float
    category: str
    description: str | None


@dataclass(frozen=True)
class ParsedIncome:
    amount: float
    description: str | None


@dataclass(frozen=True)
class ParsedBudget:
    amount: float
    category: str | None


@dataclass(frozen=True)
class ParsedFixedExpense:
    amount: float
    category: str
    description: str | None


class ExpenseValidationError(ValueError):
    pass


def parse_add_command(args: list[str]) -> ParsedExpense:
    return _parse_expense_fields(args, command="/add")


def parse_edit_command(args: list[str]) -> tuple[int, ParsedExpense]:
    if len(args) < 3:
        raise ExpenseValidationError(
            "Use: /edit id valor categoria descricao opcional\nExemplo: /edit 3 42.50 mercado feira"
        )

    expense_id = parse_expense_id(args[0])
    return expense_id, _parse_expense_fields(args[1:], command="/edit")


def parse_delete_command(args: list[str]) -> int:
    if len(args) != 1:
        raise ExpenseValidationError("Use: /delete id\nExemplo: /delete 3")
    return parse_expense_id(args[0])


def parse_income_command(args: list[str]) -> ParsedIncome:
    if not args:
        raise ExpenseValidationError(
            "Use: /receita valor descricao opcional\nExemplo: /receita 3500 salario"
        )

    amount = parse_amount(args[0], command="/receita")
    description = " ".join(args[1:]).strip() or None
    return ParsedIncome(amount=amount, description=description)


def parse_budget_command(args: list[str]) -> ParsedBudget:
    if len(args) == 1:
        return ParsedBudget(amount=parse_amount(args[0], command="/orcamento"), category=None)

    if len(args) == 2:
        category = args[0].strip().lower()
        if not category:
            raise ExpenseValidationError("Informe uma categoria. Exemplo: /orcamento alimentacao 900")
        return ParsedBudget(amount=parse_amount(args[1], command="/orcamento"), category=category)

    raise ExpenseValidationError(
        "Use: /orcamento valor ou /orcamento categoria valor\n"
        "Exemplos: /orcamento 3000 ou /orcamento alimentacao 900"
    )


def parse_fixed_expense_command(args: list[str]) -> ParsedFixedExpense:
    parsed = _parse_expense_fields(args, command="/fixo")
    return ParsedFixedExpense(
        amount=parsed.amount,
        category=parsed.category,
        description=parsed.description,
    )


def parse_fixed_expense_id(args: list[str]) -> int:
    if len(args) != 1:
        raise ExpenseValidationError("Use: /delete_fixo id\nExemplo: /delete_fixo 2")
    return parse_expense_id(args[0])


def parse_expense_id(raw_value: str) -> int:
    try:
        expense_id = int(raw_value)
    except ValueError as exc:
        raise ExpenseValidationError("O id precisa ser um numero inteiro. Exemplo: /delete 3") from exc

    if expense_id <= 0:
        raise ExpenseValidationError("O id deve ser maior que zero.")
    return expense_id


def parse_amount(raw_value: str, command: str) -> float:
    normalized_value = raw_value.replace(",", ".")
    try:
        amount = float(normalized_value)
    except ValueError as exc:
        raise ExpenseValidationError(f"O valor precisa ser numerico. Exemplo: {command} 25") from exc

    if amount <= 0:
        raise ExpenseValidationError("O valor deve ser maior que zero.")
    return round(amount, 2)


def parse_day_command(args: list[str], today: date | None = None) -> date:
    today = today or datetime.now().date()

    if not args:
        return today

    if len(args) != 1:
        raise ExpenseValidationError("Use: /dia 15 ou /dia 22/04/2026")

    raw_date = args[0].strip()
    if raw_date.isdigit():
        day = int(raw_date)
        try:
            return date(today.year, today.month, day)
        except ValueError as exc:
            raise ExpenseValidationError("Dia invalido para o mes atual.") from exc

    try:
        return datetime.strptime(raw_date, "%d/%m/%Y").date()
    except ValueError as exc:
        raise ExpenseValidationError("Data invalida. Use /dia 15 ou /dia 22/04/2026.") from exc


def _parse_expense_fields(args: list[str], command: str) -> ParsedExpense:
    if len(args) < 2:
        raise ExpenseValidationError(
            f"Use: {command} valor categoria descricao opcional\n"
            f"Exemplo: {command} 59.90 alimentacao almoco"
        )

    amount = parse_amount(args[0], command=command)

    category = args[1].strip().lower()
    if not category:
        raise ExpenseValidationError(f"Informe uma categoria. Exemplo: {command} 120 transporte uber")

    description = " ".join(args[2:]).strip() or None
    return ParsedExpense(amount=amount, category=category, description=description)
