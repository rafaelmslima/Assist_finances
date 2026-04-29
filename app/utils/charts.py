from io import BytesIO
from textwrap import shorten

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt


COLORS = ["#2d7dd2", "#f45d48", "#7ac74f", "#f9c80e", "#8f2d56", "#00a6a6", "#5b5f97"]
MANY_CATEGORIES_THRESHOLD = 7
OTHER_CATEGORY_THRESHOLD = 0.04


def build_category_chart(category_totals: dict[str, float]) -> BytesIO:
    grouped = _group_small_categories(category_totals)
    total = sum(grouped.values())
    title = f"Gastos por categoria - total R$ {total:.2f}".replace(".", ",")

    if len(grouped) <= MANY_CATEGORIES_THRESHOLD:
        fig, ax = plt.subplots(figsize=(7, 7))
        ax.pie(
            list(grouped.values()),
            labels=list(grouped.keys()),
            autopct="%1.1f%%",
            startangle=90,
            colors=COLORS,
            textprops={"fontsize": 10},
        )
        ax.set_title(title)
        ax.axis("equal")
        return _save_figure(fig)

    labels = [
        f"{category} ({((value / total) * 100):.1f}%)".replace(".", ",")
        for category, value in grouped.items()
    ]
    return _build_horizontal_bar_chart(
        title=title,
        labels=labels,
        values=list(grouped.values()),
        value_label="Valor gasto",
    )


def build_daily_evolution_chart(daily_totals: dict[int, float], average: float) -> BytesIO:
    days = list(daily_totals.keys())
    values = list(daily_totals.values())

    fig, ax = plt.subplots(figsize=(10, 5))
    ax.bar(days, values, color="#2d7dd2")
    ax.plot(days, values, color="#f45d48", marker="o", linewidth=1.8)
    ax.axhline(average, color="#5b5f97", linestyle="--", linewidth=1.4, label="Media diaria")
    ax.set_title("Evolucao diaria dos gastos")
    ax.set_xlabel("Dia do mes")
    ax.set_ylabel("Valor gasto")
    ax.legend()
    ax.grid(axis="y", alpha=0.25)
    ax.set_xticks(days[::2] if len(days) > 16 else days)
    return _save_figure(fig)


def build_top_expenses_chart(expenses: list[dict[str, object]]) -> BytesIO:
    labels = [
        shorten(
            f"{item['category']} - {item['description']}" if item.get("description") else str(item["category"]),
            width=36,
            placeholder="...",
        )
        for item in expenses
    ]
    values = [float(item["amount"]) for item in expenses]
    return _build_horizontal_bar_chart(
        title="Top 5 maiores gastos do mes",
        labels=labels,
        values=values,
        value_label="Valor",
    )


def build_month_comparison_chart(comparison: dict[str, object]) -> BytesIO:
    current_total = float(comparison["current_total"])
    previous_total = float(comparison["previous_total"])
    categories = comparison.get("categories") or {}

    fig, axes = plt.subplots(1, 2 if categories else 1, figsize=(12 if categories else 7, 5))
    if not isinstance(axes, list) and not hasattr(axes, "__len__"):
        axes = [axes]

    axes[0].bar(["Mes anterior", "Mes atual"], [previous_total, current_total], color=["#8f2d56", "#2d7dd2"])
    axes[0].set_title("Total por mes")
    axes[0].set_ylabel("Valor gasto")
    axes[0].grid(axis="y", alpha=0.25)

    if categories:
        top_categories = sorted(
            categories.items(),
            key=lambda item: float(item[1]["current"]) + float(item[1]["previous"]),
            reverse=True,
        )[:6]
        labels = [shorten(category, width=16, placeholder="...") for category, _ in top_categories]
        previous_values = [float(item["previous"]) for _, item in top_categories]
        current_values = [float(item["current"]) for _, item in top_categories]
        positions = range(len(labels))
        width = 0.38
        axes[1].bar([position - width / 2 for position in positions], previous_values, width, label="Anterior", color="#8f2d56")
        axes[1].bar([position + width / 2 for position in positions], current_values, width, label="Atual", color="#2d7dd2")
        axes[1].set_title("Categorias principais")
        axes[1].set_xticks(list(positions), labels, rotation=30, ha="right")
        axes[1].legend()
        axes[1].grid(axis="y", alpha=0.25)

    return _save_figure(fig)


def build_budget_chart(status: dict[str, object]) -> BytesIO:
    categories = status.get("categories") or []
    total_budget = status.get("total_budget")
    total_spent = float(status.get("total_spent") or 0)

    if categories:
        labels = [shorten(str(item["category"]), width=18, placeholder="...") for item in categories]
        budgets = [float(item["budget"]) for item in categories]
        spent = [float(item["spent"]) for item in categories]
        positions = range(len(labels))
        width = 0.38

        fig, ax = plt.subplots(figsize=(10, 5))
        ax.bar([position - width / 2 for position in positions], budgets, width, label="Orcamento", color="#7ac74f")
        ax.bar([position + width / 2 for position in positions], spent, width, label="Gasto", color="#f45d48")
        ax.set_title("Orcamento x gasto por categoria")
        ax.set_xticks(list(positions), labels, rotation=30, ha="right")
        ax.set_ylabel("Valor")
        ax.legend()
        ax.grid(axis="y", alpha=0.25)
        return _save_figure(fig)

    fig, ax = plt.subplots(figsize=(7, 5))
    ax.bar(["Orcamento", "Gasto atual"], [float(total_budget), total_spent], color=["#7ac74f", "#f45d48"])
    ax.set_title("Orcamento x gasto")
    ax.set_ylabel("Valor")
    ax.grid(axis="y", alpha=0.25)
    return _save_figure(fig)


def build_fixed_variable_chart(fixed_total: float, variable_total: float) -> BytesIO:
    fig, ax = plt.subplots(figsize=(7, 5))
    ax.bar(["Fixos previstos", "Variaveis reais"], [fixed_total, variable_total], color=["#5b5f97", "#00a6a6"])
    ax.set_title("Fixos x variaveis")
    ax.set_ylabel("Valor")
    ax.grid(axis="y", alpha=0.25)
    return _save_figure(fig)


def _group_small_categories(category_totals: dict[str, float]) -> dict[str, float]:
    ordered = dict(sorted(category_totals.items(), key=lambda item: item[1], reverse=True))
    total = sum(ordered.values())
    if not total:
        return ordered

    grouped: dict[str, float] = {}
    other_total = 0.0
    for category, value in ordered.items():
        if value / total < OTHER_CATEGORY_THRESHOLD and len(ordered) > MANY_CATEGORIES_THRESHOLD:
            other_total += value
        else:
            grouped[category] = value

    if other_total:
        grouped["Outros"] = round(other_total, 2)
    return grouped


def _build_horizontal_bar_chart(
    title: str,
    labels: list[str],
    values: list[float],
    value_label: str,
) -> BytesIO:
    fig_height = max(4, 0.55 * len(labels) + 1.5)
    fig, ax = plt.subplots(figsize=(9, fig_height))
    reversed_labels = list(reversed(labels))
    reversed_values = list(reversed(values))
    colors = [COLORS[index % len(COLORS)] for index in range(len(reversed_labels))]
    ax.barh(reversed_labels, reversed_values, color=colors)
    ax.set_title(title)
    ax.set_xlabel(value_label)
    ax.grid(axis="x", alpha=0.25)
    for index, value in enumerate(reversed_values):
        ax.text(value, index, f" R$ {value:.2f}".replace(".", ","), va="center", fontsize=9)
    return _save_figure(fig)


def _save_figure(fig) -> BytesIO:
    plt.tight_layout()
    buffer = BytesIO()
    fig.savefig(buffer, format="png", dpi=140)
    plt.close(fig)
    buffer.seek(0)
    return buffer
