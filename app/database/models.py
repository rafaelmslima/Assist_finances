from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import BigInteger, Boolean, Date, DateTime, ForeignKey, Index, Integer, Numeric, String, UniqueConstraint, text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class Expense(Base):
    __tablename__ = "expenses"
    __table_args__ = (
        Index("ix_expenses_user_created_at", "user_id", "created_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False)
    telegram_user_id: Mapped[int | None] = mapped_column(BigInteger, index=True, nullable=True)
    amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    category: Mapped[str] = mapped_column(String(80), index=True, nullable=False)
    description: Mapped[str | None] = mapped_column(String(255), nullable=True)
    payment_source: Mapped[str] = mapped_column(String(30), default="money", nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=datetime.now,
        nullable=False,
    )
    user: Mapped["User"] = relationship(back_populates="expenses")


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    telegram_user_id: Mapped[int] = mapped_column(BigInteger, unique=True, index=True, nullable=False)
    telegram_chat_id: Mapped[int] = mapped_column(BigInteger, index=True, nullable=False)
    first_name: Mapped[str | None] = mapped_column(String(120), nullable=True)
    username: Mapped[str | None] = mapped_column(String(120), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    receive_updates_notifications: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=datetime.now,
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=datetime.now,
        onupdate=datetime.now,
        nullable=False,
    )
    expenses: Mapped[list["Expense"]] = relationship(back_populates="user", cascade="all, delete-orphan")
    incomes: Mapped[list["Income"]] = relationship(back_populates="user", cascade="all, delete-orphan")
    budgets: Mapped[list["Budget"]] = relationship(back_populates="user", cascade="all, delete-orphan")
    fixed_expenses: Mapped[list["FixedExpense"]] = relationship(back_populates="user", cascade="all, delete-orphan")
    daily_notifications: Mapped[list["DailyNotification"]] = relationship(back_populates="user", cascade="all, delete-orphan")
    ticket_benefits: Mapped[list["TicketBenefit"]] = relationship(back_populates="user", cascade="all, delete-orphan")
    salary_config: Mapped["SalaryConfig | None"] = relationship(
        back_populates="user",
        cascade="all, delete-orphan",
        uselist=False,
    )
    onboarding_completed: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)


class UpdateBroadcast(Base):
    __tablename__ = "update_broadcasts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    admin_user_id: Mapped[int] = mapped_column(Integer, index=True, nullable=False)
    message: Mapped[str] = mapped_column(String(4096), nullable=False)
    total_users: Mapped[int] = mapped_column(Integer, nullable=False)
    sent_count: Mapped[int] = mapped_column(Integer, nullable=False)
    failed_count: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=datetime.now,
        nullable=False,
    )


class Income(Base):
    __tablename__ = "incomes"
    __table_args__ = (
        Index("ix_incomes_user_created_at", "user_id", "created_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False)
    telegram_user_id: Mapped[int | None] = mapped_column(BigInteger, index=True, nullable=True)
    amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    description: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=datetime.now,
        nullable=False,
    )
    user: Mapped["User"] = relationship(back_populates="incomes")


class SalaryConfig(Base):
    __tablename__ = "salary_configs"
    __table_args__ = (
        UniqueConstraint("user_id", name="uq_salary_config_user"),
        Index("ix_salary_configs_active", "is_active"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False)
    telegram_user_id: Mapped[int | None] = mapped_column(BigInteger, index=True, nullable=True)
    amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    schedule_type: Mapped[str] = mapped_column(String(20), nullable=False)
    pay_day: Mapped[int | None] = mapped_column(Integer, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    current_cycle_start: Mapped[date | None] = mapped_column(Date, nullable=True)
    last_auto_salary_on: Mapped[date | None] = mapped_column(Date, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=datetime.now,
        onupdate=datetime.now,
        nullable=False,
    )
    user: Mapped["User"] = relationship(back_populates="salary_config")


class Budget(Base):
    __tablename__ = "budgets"
    __table_args__ = (
        UniqueConstraint("user_id", "month", "category", name="uq_budget_user_month_category"),
        Index("ix_budgets_user_month", "user_id", "month"),
        Index(
            "uq_budgets_user_month_total",
            "user_id",
            "month",
            unique=True,
            sqlite_where=text("category IS NULL"),
            postgresql_where=text("category IS NULL"),
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False)
    telegram_user_id: Mapped[int | None] = mapped_column(BigInteger, index=True, nullable=True)
    month: Mapped[str] = mapped_column(String(7), nullable=False)
    category: Mapped[str | None] = mapped_column(String(80), nullable=True)
    amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=datetime.now,
        onupdate=datetime.now,
        nullable=False,
    )
    user: Mapped["User"] = relationship(back_populates="budgets")


class FixedExpense(Base):
    __tablename__ = "fixed_expenses"
    __table_args__ = (
        Index("ix_fixed_expenses_user", "user_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False)
    telegram_user_id: Mapped[int | None] = mapped_column(BigInteger, index=True, nullable=True)
    amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    category: Mapped[str] = mapped_column(String(80), index=True, nullable=False)
    description: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=datetime.now,
        nullable=False,
    )
    user: Mapped["User"] = relationship(back_populates="fixed_expenses")


class TicketBenefit(Base):
    __tablename__ = "ticket_benefits"
    __table_args__ = (
        UniqueConstraint("user_id", "benefit_type", name="uq_ticket_benefit_user_type"),
        Index("ix_ticket_benefits_user_type", "user_id", "benefit_type"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False)
    telegram_user_id: Mapped[int | None] = mapped_column(BigInteger, index=True, nullable=True)
    benefit_type: Mapped[str] = mapped_column(String(30), nullable=False)
    configured_amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    current_balance: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    cycle_start: Mapped[date | None] = mapped_column(Date, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=datetime.now,
        onupdate=datetime.now,
        nullable=False,
    )
    user: Mapped["User"] = relationship(back_populates="ticket_benefits")


class DailyNotification(Base):
    __tablename__ = "daily_notifications"
    __table_args__ = (
        UniqueConstraint("user_id", "sent_on", name="uq_daily_notification_user_date"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False)
    telegram_user_id: Mapped[int | None] = mapped_column(BigInteger, index=True, nullable=True)
    sent_on: Mapped[date] = mapped_column(Date, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=datetime.now,
        nullable=False,
    )
    user: Mapped["User"] = relationship(back_populates="daily_notifications")
