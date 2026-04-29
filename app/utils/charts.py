from io import BytesIO

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt


def build_category_chart(category_totals: dict[str, float]) -> BytesIO:
    labels = list(category_totals.keys())
    values = list(category_totals.values())

    fig, ax = plt.subplots(figsize=(7, 7))
    colors = ["#2d7dd2", "#f45d48", "#7ac74f", "#f9c80e", "#8f2d56", "#00a6a6"]

    ax.pie(
        values,
        labels=labels,
        autopct="%1.1f%%",
        startangle=90,
        colors=colors,
        textprops={"fontsize": 10},
    )
    ax.set_title("Gastos por categoria no mes")
    ax.axis("equal")
    plt.tight_layout()

    buffer = BytesIO()
    fig.savefig(buffer, format="png", dpi=140)
    plt.close(fig)
    buffer.seek(0)
    return buffer
