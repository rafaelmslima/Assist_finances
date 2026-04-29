class AlertService:
    def build_alerts(self, analysis: dict[str, object]) -> list[str]:
        alerts: list[str] = []

        historical_daily_average = float(analysis.get("historical_daily_average") or 0)
        current_daily_average = float(analysis.get("current_daily_average") or 0)
        if historical_daily_average > 0 and current_daily_average >= historical_daily_average * 1.2:
            alerts.append("Voce esta gastando acima do seu padrao historico.")

        total_budget = analysis.get("total_budget")
        total_forecast = float(analysis.get("total_forecast") or 0)
        if total_budget and total_forecast > float(total_budget):
            alerts.append("A previsao ultrapassa o orcamento mensal.")

        fixed_expenses = float(analysis.get("fixed_expenses") or 0)
        monthly_income = float(analysis.get("monthly_income") or 0)
        if monthly_income > 0 and fixed_expenses > monthly_income:
            alerts.append("Seus gastos fixos ja ultrapassam sua receita mensal.")

        projected_balance = analysis.get("projected_balance")
        if projected_balance is not None and float(projected_balance) < 0:
            alerts.append("Seu saldo projetado esta negativo.")

        for item in analysis.get("category_alerts", []):
            alerts.append(str(item))

        return alerts

    def build_suggestion(self, analysis: dict[str, object]) -> str:
        category_alerts = analysis.get("category_alerts", [])
        if category_alerts:
            categories = analysis.get("top_categories", [])
            if categories:
                return f"Reduza gastos em categorias como {', '.join(categories[:2])}."
        if float(analysis.get("projected_balance") or 0) < 0:
            return "Revise gastos variaveis e adie despesas nao essenciais para proteger o saldo."
        if analysis.get("total_budget") and float(analysis.get("total_forecast") or 0) > float(analysis["total_budget"]):
            return "Use o orcamento como teto diario e acompanhe as categorias mais usadas."
        return "Mantenha o ritmo atual e revise novas despesas antes de assumir compromissos fixos."
