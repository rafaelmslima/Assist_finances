from telegram import Update
from telegram.ext import ContextTypes

from app.bot.keyboards import (
    TUTORIAL_BACK_CALLBACK,
    TUTORIAL_EXIT_CALLBACK,
    TUTORIAL_PREFIX,
    build_tutorial_detail_keyboard,
    build_tutorial_menu_keyboard,
)
from app.database.repository import UserRepository
from app.database.session import SessionLocal
from app.services.user_service import TelegramUserData, UnauthorizedUserError, UserService


UNAUTHORIZED_TEXT = "Voce nao esta autorizado a usar este bot."

TUTORIAL_MENU_TEXT = """
Tutorial do bot financeiro

Escolha uma funcionalidade para aprender com um exemplo rapido:
""".strip()

TUTORIAL_FINISHED_TEXT = "Tutorial encerrado. Use /help quando quiser ver todos os comandos."

TUTORIAL_CONTENT = {
    "expense": """
➕ Registrar gasto

Serve para salvar um gasto do dia a dia.
Use quando pagar mercado, transporte, lanche, conta ou qualquer compra.

Exemplo:
/add 25 mercado almoço

Dica: digite apenas /add para usar o modo guiado, com perguntas passo a passo.
""".strip(),
    "income_balance": """
💰 Receitas e saldo

Serve para registrar entradas de dinheiro e acompanhar quanto sobra.
Use quando receber salario, extra, reembolso ou quiser consultar seu saldo.

Exemplos:
/receita 3000 salário
/saldo

Dica: registre receitas antes de olhar o saldo para ter uma visao mais realista do mes.
""".strip(),
    "month_summary": """
📊 Resumo do mês

Serve para ver quanto voce gastou no mes atual.
Use quando quiser entender o total gasto e quais categorias pesaram mais.

Exemplo:
/mes

Dica: consulte algumas vezes por semana para ajustar o ritmo antes do fim do mes.
""".strip(),
    "day_summary": """
📅 Gastos por dia

Serve para ver gastos de hoje ou de uma data especifica.
Use quando quiser conferir o que foi lançado em um dia.

Exemplos:
/hoje
/dia 15
/dia 22/04/2026

Dica: se notar algo errado na lista, use o ID mostrado para editar ou apagar.
""".strip(),
    "fixed_expenses": """
📌 Gastos fixos

Serve para cadastrar compromissos previstos do mes, como aluguel, internet, academia ou gasolina.
Use para planejar despesas que costumam se repetir.

Exemplos:
/fixo 120 academia
/fixos

Dica: gasto fixo e uma previsao; ele nao vira gasto real automaticamente.
""".strip(),
    "budgets": """
🎯 Orçamentos

Serve para definir limites de gasto no mes ou em uma categoria.
Use quando quiser controlar um teto geral ou uma area especifica.

Exemplos:
/orcamento 2500
/orcamento alimentação 600

Dica: comece com um limite simples para o mes todo e refine por categoria depois.
""".strip(),
    "forecast": """
📈 Previsão de gastos

Serve para estimar como o mes pode terminar com base no seu historico.
Use no meio do mes para saber se esta dentro do planejado.

Exemplo:
/previsao

Dica: a previsao melhora quanto mais gastos voce registra ao longo do tempo.
""".strip(),
    "charts": """
🖼️ Gráficos

Serve para ver visualmente o percentual gasto por categoria.
Use quando quiser identificar rapidamente para onde o dinheiro esta indo.

Exemplo:
/grafico

Dica: categorias bem nomeadas deixam o grafico muito mais facil de entender.
""".strip(),
    "edit_delete": """
✏️ Editar ou apagar lançamentos

Serve para corrigir erros em gastos ou remover lançamentos indevidos.
Use quando digitou valor, categoria ou descricao errada.

Exemplos:
/edit 3 45 mercado almoço
/delete 3
/delete_fixo 2

Dica: veja o ID do lançamento nas listas de /hoje ou /dia.
""".strip(),
}


async def tutorial_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not await _ensure_authorized(update):
        return

    await update.message.reply_text(
        TUTORIAL_MENU_TEXT,
        reply_markup=build_tutorial_menu_keyboard(),
    )


async def tutorial_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()

    if not await _ensure_authorized(update):
        return

    data = query.data or ""
    if data == TUTORIAL_BACK_CALLBACK:
        await query.edit_message_text(
            TUTORIAL_MENU_TEXT,
            reply_markup=build_tutorial_menu_keyboard(),
        )
        return

    if data == TUTORIAL_EXIT_CALLBACK:
        await query.edit_message_text(TUTORIAL_FINISHED_TEXT)
        return

    if data.startswith(f"{TUTORIAL_PREFIX}:topic:"):
        topic = data.rsplit(":", 1)[1]
        content = TUTORIAL_CONTENT.get(topic)
        if content:
            await query.edit_message_text(
                content,
                reply_markup=build_tutorial_detail_keyboard(),
            )
            return

    await query.edit_message_text(
        "Opcao do tutorial invalida. Digite /tutorial para abrir o menu novamente."
    )


async def _ensure_authorized(update: Update) -> bool:
    telegram_user = update.effective_user
    chat = update.effective_chat
    if not telegram_user or not chat:
        await _send_access_message(update, "Nao consegui identificar seu usuario no Telegram.")
        return False

    data = TelegramUserData(
        telegram_user_id=telegram_user.id,
        telegram_chat_id=chat.id,
        first_name=telegram_user.first_name,
        username=telegram_user.username,
    )

    try:
        with SessionLocal() as db:
            UserService(UserRepository(db)).register_or_update_from_telegram(data)
    except UnauthorizedUserError:
        await _send_access_message(update, UNAUTHORIZED_TEXT)
        return False

    return True


async def _send_access_message(update: Update, text: str) -> None:
    if update.callback_query:
        await update.callback_query.edit_message_text(text)
        return

    if update.message:
        await update.message.reply_text(text)
