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
from app.bot.tutorial import TUTORIAL_CONTENT


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
    def test_tutorial_and_charts_are_registered_in_telegram_commands(self):
        main_py = Path(__file__).resolve().parents[1] / "main.py"
        content = main_py.read_text(encoding="utf-8")

        self.assertIn('BotCommand("tutorial"', content)
        self.assertIn('CommandHandler("tutorial"', content)
        self.assertIn("CallbackQueryHandler(tutorial_callback", content)
        self.assertIn('CommandHandler("grafico", chart_menu)', content)
        self.assertIn("CallbackQueryHandler(chart_callback", content)


if __name__ == "__main__":
    unittest.main()
