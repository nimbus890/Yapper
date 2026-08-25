import unittest

from aura_flow.formatting import DeterministicFormatter, Dictionary, FormatContext


class FormattingTests(unittest.TestCase):
    def test_commands_preserve_fillers_and_apply_dictionary(self):
        formatter = DeterministicFormatter(Dictionary({"whisper flow": "Wispr Flow"}))
        result = formatter.format("um hello comma whisper flow question mark")
        self.assertEqual(result.text, "Um hello, Wispr Flow?")

    def test_backtrack_keeps_correction(self):
        result = DeterministicFormatter().format("meet on Thursday scratch that meet on Friday")
        self.assertEqual(result.text, "Meet on Friday.")

    def test_list_formatting(self):
        result = DeterministicFormatter().format("first update the API second add tests third deploy it")
        self.assertEqual(result.text, "1. Update the API\n2. Add tests\n3. Deploy it")

    def test_cardinal_list_formatting(self):
        result = DeterministicFormatter().format(
            "one comma update the API two comma add tests three comma deploy it"
        )
        self.assertEqual(result.text, "1. Update the API\n2. Add tests\n3. Deploy it")

    def test_discourse_words_are_left_for_the_single_ai_pass(self):
        result = DeterministicFormatter().format("so yeah okay send the report")
        self.assertEqual(result.text, "So yeah okay send the report.")
        self.assertEqual(DeterministicFormatter().format("I think so").text, "I think so.")

    def test_chat_style_drops_short_period(self):
        result = DeterministicFormatter().format("sounds good", FormatContext(style="casual"))
        self.assertEqual(result.text, "Sounds good")

    def test_app_category_does_not_change_tone(self):
        result = DeterministicFormatter().format("sounds good", FormatContext(app_category="work"))
        self.assertEqual(result.text, "Sounds good.")

    def test_press_enter_is_an_action(self):
        result = DeterministicFormatter().format("send this press enter")
        self.assertEqual(result.text, "Send this.")
        self.assertTrue(result.press_enter)

    def test_ambiguous_inline_correction_is_not_deleted_by_rules(self):
        result = DeterministicFormatter().format("meet on Thursday actually Friday")
        self.assertEqual(result.text, "Meet on Thursday actually Friday.")

    def test_explicit_day_correction_keeps_the_final_choice(self):
        result = DeterministicFormatter().format(
            "it launches Thursday no actually Friday morning"
        )
        self.assertEqual(result.text, "It launches Friday morning.")

    def test_ordinary_no_phrase_is_not_treated_as_a_correction(self):
        result = DeterministicFormatter().format("we do no harm on Friday")
        self.assertEqual(result.text, "We do no harm on Friday.")

    def test_new_para_is_an_explicit_blank_line(self):
        result = DeterministicFormatter().format("first thought new para second thought")
        self.assertEqual(result.text, "First thought\n\nsecond thought")

    def test_natural_numbered_list_keeps_intro_and_accepts_is_that(self):
        result = DeterministicFormatter().format(
            "we need three things number one fix login number two is that update docs number three deploy"
        )
        self.assertEqual(
            result.text,
            "We need three things:\n1. Fix login\n2. Update docs\n3. Deploy",
        )

    def test_decimal_version_is_not_treated_as_a_list_marker(self):
        result = DeterministicFormatter().format(
            "for version 2.3 we need three things number one fix login number two update docs number three deploy"
        )
        self.assertEqual(
            result.text,
            "For version 2.3 we need three things:\n1. Fix login\n2. Update docs\n3. Deploy",
        )

    def test_stray_second_and_third_markers_do_not_create_a_list(self):
        result = DeterministicFormatter().format(
            "Hi this is Yapper1, it can transcribe anything, 2 it formats, 3 it inserts"
        )
        self.assertNotIn("\n1.", result.text)
        self.assertTrue(result.text.startswith("Hi this is Yapper1"))

    def test_snippet_expansion(self):
        formatter = DeterministicFormatter(snippets={"meeting link": "https://meet.example/test"})
        result = formatter.format("insert meeting link")
        self.assertEqual(result.text, "https://meet.example/test")
        self.assertEqual(result.snippet_trigger, "meeting link")

    def test_snippet_expands_inside_a_sentence(self):
        formatter = DeterministicFormatter(snippets={"meeting link": "https://meet.example/test"})
        result = formatter.format("please use meeting link tomorrow")
        self.assertEqual(result.text, "Please use https://meet.example/test tomorrow.")
        self.assertEqual(result.snippet_trigger, "meeting link")

    def test_email_and_url_are_not_changed_by_punctuation_spacing(self):
        result = DeterministicFormatter().format(
            "email maya@example.com and open https://example.com/report"
        )
        self.assertEqual(
            result.text,
            "Email maya@example.com and open https://example.com/report.",
        )

    def test_selected_text_rewrite_command(self):
        result = DeterministicFormatter().format("make this concise")
        self.assertEqual(result.action, "rewrite_concise")

    def test_voice_action(self):
        result = DeterministicFormatter().format("paste last transcript")
        self.assertEqual(result.action, "paste_last")
        self.assertEqual(result.text, "")

    def test_undo_cleanup_voice_action(self):
        result = DeterministicFormatter().format("undo formatting")
        self.assertEqual(result.action, "undo_cleanup")

    def test_style_override(self):
        result = DeterministicFormatter().format("very casual mode Sounds good")
        self.assertEqual(result.text, "sounds good")
        self.assertEqual(result.style, "very_casual")

    def test_excited_style(self):
        result = DeterministicFormatter().format("we shipped it", FormatContext(style="excited"))
        self.assertEqual(result.text, "We shipped it!")


if __name__ == "__main__":
    unittest.main()
