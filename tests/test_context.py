import unittest

from aura_flow.context import TargetWindow, WindowsContextProvider, _category


class ContextTests(unittest.TestCase):
    def test_native_app_categories(self):
        self.assertEqual(_category("slack.exe", ""), "work")
        self.assertEqual(_category("outlook.exe", ""), "email")
        self.assertEqual(_category("whatsapp.exe", ""), "personal")

    def test_browser_title_categories(self):
        self.assertEqual(_category("chrome.exe", "Inbox - Gmail"), "email")
        self.assertEqual(_category("msedge.exe", "Slack"), "work")

    def test_formatting_context_is_bounded_target_data(self):
        target = TargetWindow(1, 2, "notepad.exe", "Note", "other", before_cursor="hello", selected_text="world")
        context = WindowsContextProvider.formatting_context(target)
        self.assertEqual(context.before_cursor, "hello")
        self.assertEqual(context.selected_text, "world")

    def test_text_pattern_captures_exact_caret_context(self):
        class Range:
            def __init__(self, text, start, end):
                self.text, self.start, self.end = text, start, end

            def Clone(self):
                return Range(self.text, self.start, self.end)

            def GetText(self, limit=-1):
                value = self.text[self.start:self.end]
                return value if limit < 0 else value[:limit]

            def MoveEndpointByUnit(self, endpoint, unit, count, waitTime=0):
                del unit, waitTime
                if endpoint == 0:
                    self.start = max(0, min(len(self.text), self.start + count))
                else:
                    self.end = max(0, min(len(self.text), self.end + count))

            def MoveEndpointByRange(self, endpoint, other, other_endpoint, waitTime=0):
                del waitTime
                position = other.start if other_endpoint == 0 else other.end
                if endpoint == 0:
                    self.start = position
                else:
                    self.end = position

        text = "hello selected world"
        selection = Range(text, 6, 14)

        class TextPattern:
            DocumentRange = Range(text, 0, len(text))

            @staticmethod
            def GetSelection():
                return [selection]

        class ValuePattern:
            Value = text

        class Control:
            IsPassword = False
            ProcessId = 77
            Name = "Editor"
            ControlTypeName = "EditControl"

            @staticmethod
            def GetValuePattern():
                return ValuePattern()

            @staticmethod
            def GetTextPattern():
                return TextPattern()

        class Endpoint:
            Start, End = 0, 1

        class Unit:
            Character = 0

        class FakeUia:
            TextPatternRangeEndpoint = Endpoint
            TextUnit = Unit

            @staticmethod
            def GetFocusedControl():
                return Control()

        provider = WindowsContextProvider(enabled=False)
        provider.uia = FakeUia()
        target = provider._with_accessibility_context(TargetWindow(1, 77, "notepad.exe", "Note", "other"))
        self.assertEqual(target.before_cursor, "hello ")
        self.assertEqual(target.selected_text, "selected")
        self.assertEqual(target.after_cursor, " world")
        self.assertTrue(target.direct_insertion_available)


if __name__ == "__main__":
    unittest.main()
