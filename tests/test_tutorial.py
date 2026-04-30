import os
import unittest
from pathlib import Path

os.environ.setdefault("TELEGRAM_BOT_TOKEN", "test-token")
os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")

from app.bot.keyboards import (
    CHART_BACK_CALLBACK,
    CHART_CLOSE_CALLBACK,
    CHART_OPTIONS,
    TUTORIAL_EXIT_CALLBACK,
    TUTORIAL_TOPICS,
    build_chart_menu_keyboard,
    build_chart_result_keyboard,
    build_tutorial_detail_keyboard,
    build_tutorial_menu_keyboard,
)
from app.bot.commands import PUBLIC_BOT_COMMANDS, START_TEXT, HELP_TEXT
from app.bot.tutorial import TUTORIAL_CONTENT
from main import DEFAULT_BOT_COMMANDS


class TutorialKeyboardTest(unittest.TestCase):
    def test_menu_has_all_topics_and_exit(self):
        keyboard = build_tutorial_menu_keyboard()
        buttons = [button for row in keyboard.inline_keyboard for button in row]
        labels = [button.text for button in buttons]
        callbacks = [button.callback_data for button in buttons]

        for label, topic in TUTORIAL_TOPICS:
            self.assertIn(label, labels)
            self.assertIn(f"tutorial:topic:{topic}", callbacks)
            self.assertIn(topic, TUTORIAL_CONTENT)

        self.assertIn("❌ Sair do tutorial", labels)
        self.assertIn(TUTORIAL_EXIT_CALLBACK, callbacks)

    def test_detail_keyboard_has_back_and_exit(self):
        keyboard = build_tutorial_detail_keyboard()
        labels = [button.text for row in keyboard.inline_keyboard for button in row]

        self.assertEqual(labels, ["⬅️ Voltar ao tutorial", "❌ Sair"])


class ChartKeyboardTest(unittest.TestCase):
    def test_chart_menu_has_all_options_and_cancel(self):
        keyboard = build_chart_menu_keyboard()
        buttons = [button for row in keyboard.inline_keyboard for button in row]
        labels = [button.text for button in buttons]
        callbacks = [button.callback_data for button in buttons]

        for label, chart_type in CHART_OPTIONS:
            self.assertIn(label, labels)
            self.assertIn(f"chart:show:{chart_type}", callbacks)

        self.assertIn(CHART_CLOSE_CALLBACK, callbacks)

    def test_chart_result_keyboard_has_back_and_close(self):
        keyboard = build_chart_result_keyboard()
        callbacks = [button.callback_data for row in keyboard.inline_keyboard for button in row]

        self.assertEqual(callbacks, [CHART_BACK_CALLBACK, CHART_CLOSE_CALLBACK])


class TutorialCommandRegistrationTest(unittest.TestCase):
    def test_public_bot_menu_is_built_from_the_shared_command_list(self):
        self.assertEqual(
            [command.command for command in DEFAULT_BOT_COMMANDS],
            [command for command, _ in PUBLIC_BOT_COMMANDS],
        )
        self.assertIn("disponivel", [command.command for command in DEFAULT_BOT_COMMANDS])
        self.assertIn("resumo", [command.command for command in DEFAULT_BOT_COMMANDS])
        self.assertIn("insights", [command.command for command in DEFAULT_BOT_COMMANDS])

    def test_start_and_help_include_all_public_commands_except_utility_only_entries(self):
        utility_only = {"start", "help", "tutorial"}
        for command, _ in PUBLIC_BOT_COMMANDS:
            if command in utility_only:
                continue
            self.assertIn(f"/{command}", START_TEXT)
            self.assertIn(f"/{command}", HELP_TEXT)

    def test_tutorial_and_charts_are_registered_in_telegram_commands(self):
        main_py = Path(__file__).resolve().parents[1] / "main.py"
        content = main_py.read_text(encoding="utf-8")

        self.assertNotIn('BotCommand("saldo"', content)
        self.assertIn("PUBLIC_BOT_COMMANDS", content)
        self.assertIn('CommandHandler("tutorial"', content)
        self.assertIn('CommandHandler("disponivel", available_daily)', content)
        self.assertIn('CommandHandler("resumo", smart_summary)', content)
        self.assertIn('CommandHandler("saldo", balance)', content)
        self.assertIn("CallbackQueryHandler(tutorial_callback", content)
        self.assertIn('CommandHandler("grafico", chart_menu)', content)
        self.assertIn("CallbackQueryHandler(chart_callback", content)


if __name__ == "__main__":
    unittest.main()
