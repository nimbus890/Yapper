from __future__ import annotations

from datetime import datetime
import threading
from typing import Callable

from PySide6.QtCore import QUrl, Qt, Signal
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QButtonGroup,
    QCheckBox,
    QComboBox,
    QFrame,
    QFileDialog,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMenu,
    QMessageBox,
    QPushButton,
    QSplitter,
    QStackedWidget,
    QTableWidget,
    QTableWidgetItem,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from .config import DATA_DIR
from .credentials import ApiCredentialStore
from .api_connection import (
    PROVIDER_PRESETS,
    detect_provider_from_key,
    list_available_models,
    provider_preset,
)
from .startup import is_startup_enabled, set_startup_enabled
from .usage_analysis import analyze_usage
from .theme import apply_soft_shadow
from .support import create_testing_export
from .download_manager import DownloadsPanel
from .version import VERSION


class PersonalizationPanel(QWidget):
    """Full in-dashboard personalization workspace with persistent sidebar navigation."""

    models_discovered = Signal(list, str)

    def __init__(
        self,
        pipeline,
        on_saved: Callable[[], None],
        on_close: Callable[[], None],
        on_calibrate: Callable[[], None] | None = None,
        on_open_history_entry: Callable[[str], None] | None = None,
        parent=None,
    ):
        super().__init__(parent)
        self.pipeline = pipeline
        self.on_saved = on_saved
        self.on_close = on_close
        self.on_calibrate = on_calibrate or (lambda: None)
        self.on_open_history_entry = on_open_history_entry or (lambda entry_id: None)
        self.credentials = ApiCredentialStore(DATA_DIR / "api_key.bin")
        self._pending_api_key = ""
        self._pending_api_settings: dict[str, str] | None = None
        self._api_discovery_verified = False
        self.models_discovered.connect(self._models_discovered)
        self.setObjectName("personalizationRoot")
        root = QHBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(28)

        sidebar = QFrame()
        sidebar.setObjectName("personalNav")
        sidebar.setFixedWidth(220)
        apply_soft_shadow(sidebar, 24, 6)
        navigation = QVBoxLayout(sidebar)
        navigation.setContentsMargins(18, 22, 18, 22)
        navigation.setSpacing(7)
        navigation.addWidget(self._heading("PERSONALIZE", "Settings that make yapper_ yours."))
        navigation.addSpacing(20)
        self.nav_group = QButtonGroup(self)
        self.nav_group.setExclusive(True)
        self.nav_buttons: list[QPushButton] = []
        self.pages = QStackedWidget()
        self.downloads_panel = DownloadsPanel(self.pipeline, self.on_saved)
        page_specs = (
            ("Overview", self._overview_page()),
            ("Vocabulary", self._vocabulary_page()),
            ("Replacements", self._pairs_page("replacements")),
            ("Snippets", self._pairs_page("snippets")),
            ("Preferences", self._preferences_page()),
            ("Downloads", self.downloads_panel),
            ("API connection", self._api_page()),
            ("About", self._about_page()),
        )
        for index, (title, page) in enumerate(page_specs):
            button = QPushButton(title)
            button.setObjectName("navButton")
            button.setCheckable(True)
            button.clicked.connect(lambda checked=False, value=index: self._select_page(value))
            self.nav_group.addButton(button)
            self.nav_buttons.append(button)
            navigation.addWidget(button)
            self.pages.addWidget(page)
            if index == 0:
                button.setChecked(True)
        navigation.addStretch()
        back = QPushButton("←  Back to dashboard")
        back.setObjectName("ghostButton")
        back.clicked.connect(on_close)
        navigation.addWidget(back)
        root.addWidget(sidebar)
        root.addWidget(self.pages, 1)

    @staticmethod
    def _heading(title: str, description: str) -> QWidget:
        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(5)
        heading = QLabel(title)
        heading.setObjectName("pageTitle")
        detail = QLabel(description)
        detail.setObjectName("hint")
        detail.setWordWrap(True)
        layout.addWidget(heading)
        layout.addWidget(detail)
        return container

    def _select_page(self, index: int) -> None:
        self.pages.setCurrentIndex(index)
        button = self.nav_buttons[index]
        button.setChecked(True)
        if index == 0:
            self.refresh_stats()
        elif index == 5:
            self.downloads_panel.refresh()

    def _overview_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 18, 24, 18)
        layout.addWidget(self._heading("Your yapper_", "A quick view of your dictation habits and personal language layer."))
        layout.addSpacing(28)
        metrics = QHBoxLayout()
        metrics.setSpacing(0)
        self.overview_stats: dict[str, QLabel] = {}
        for key, title in (
            ("dictations_today", "DICTATIONS TODAY"),
            ("words_today", "WORDS TODAY"),
            ("time_saved_minutes", "MINUTES SAVED"),
            ("total_words", "TOTAL WORDS"),
        ):
            column = QVBoxLayout()
            value = QLabel("0")
            value.setObjectName("overviewStat")
            column.addWidget(value)
            column.addWidget(QLabel(title, objectName="fieldTitle"))
            metrics.addLayout(column, 1)
            self.overview_stats[key] = value
        layout.addLayout(metrics)
        layout.addSpacing(44)
        layout.addWidget(QLabel("PERSONAL LANGUAGE", objectName="cardTitle"))
        self.language_summary = QLabel()
        self.language_summary.setObjectName("sectionLead")
        self.language_summary.setWordWrap(True)
        layout.addWidget(self.language_summary)
        layout.addSpacing(34)
        layout.addWidget(QLabel("LOCAL INSIGHTS  ·  UPDATED AUTOMATICALLY", objectName="cardTitle"))
        insight_row = QHBoxLayout()
        self.insight_labels: dict[str, QLabel] = {}
        for key, title in (
            ("favorite_word", "MOST-USED WORD"),
            ("average_words", "AVG. DICTATION"),
            ("filler_rate", "FILLER RATE"),
            ("longest_streak", "LONGEST STREAK"),
        ):
            column = QVBoxLayout()
            value = QLabel("—")
            value.setObjectName("insightStat")
            column.addWidget(value)
            column.addWidget(QLabel(title, objectName="fieldTitle"))
            insight_row.addLayout(column, 1)
            self.insight_labels[key] = value
        layout.addLayout(insight_row)
        extra_row = QHBoxLayout()
        self.extra_insight_labels: dict[str, QLabel] = {}
        for key, title in (
            ("current_streak", "CURRENT STREAK"),
            ("most_productive_hour", "BEST HOUR"),
            ("most_used_app", "TOP APP"),
            ("lifetime_time_saved_minutes", "LIFETIME SAVED"),
        ):
            column = QVBoxLayout()
            value = QLabel("—")
            value.setObjectName("insightStat")
            column.addWidget(value)
            column.addWidget(QLabel(title, objectName="fieldTitle"))
            extra_row.addLayout(column, 1)
            self.extra_insight_labels[key] = value
        layout.addLayout(extra_row)
        self.longest_button = QPushButton("Longest dictation · —")
        self.longest_button.setObjectName("ghostButton")
        self.longest_button.clicked.connect(self._open_longest)
        layout.addWidget(self.longest_button, 0, Qt.AlignLeft)
        self.analysis_detail = QLabel("Stats are calculated privately on this device.")
        self.analysis_detail.setObjectName("hint")
        self.analysis_detail.setWordWrap(True)
        layout.addWidget(self.analysis_detail)
        layout.addStretch()
        return page

    def _about_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 18, 24, 18)
        layout.addWidget(
            self._heading(
                "About yapper_",
                "Open source, local first, and deliberately yours.",
            )
        )
        layout.addSpacing(24)

        card = QFrame()
        card.setObjectName("apiCard")
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(24, 22, 24, 22)
        line = QLabel("A wrapper, yes. A rent-seeking wrapper, no.")
        line.setObjectName("sectionLead")
        line.setWordWrap(True)
        card_layout.addWidget(line)
        story = QLabel(
            "I built yapper_ because I hated seeing wrappers around excellent "
            "open-source tools turned into wild monthly bills. So I made an "
            "open-source wrapper of my own. Open source for open source."
        )
        story.setWordWrap(True)
        card_layout.addWidget(story)
        card_layout.addSpacing(10)
        first = QLabel(
            "This is my first project. I hope you enjoy using it—and improving it."
        )
        first.setObjectName("hint")
        first.setWordWrap(True)
        card_layout.addWidget(first)
        made_with = QLabel(
            "Vibe-coded with an LLM as a coding contributor; shaped, directed, and tested by Nimbus."
        )
        made_with.setObjectName("hint")
        made_with.setWordWrap(True)
        card_layout.addWidget(made_with)
        layout.addWidget(card)
        layout.addSpacing(18)

        privacy = QLabel(
            "PRIVATE BY DEFAULT\n"
            "Dictation, history, and local cleanup stay on this computer. "
            "Nothing is shared unless you explicitly choose to export or send it."
        )
        privacy.setObjectName("hint")
        privacy.setWordWrap(True)
        layout.addWidget(privacy)
        layout.addSpacing(10)
        version = QLabel(f"yapper_ {VERSION}  ·  published by Nimbus  ·  MIT licensed")
        version.setObjectName("fieldTitle")
        layout.addWidget(version)
        layout.addStretch()
        return page

    def refresh_stats(self) -> None:
        stats = self.pipeline.usage_stats()
        for key, label in self.overview_stats.items():
            label.setText(f"{int(stats.get(key, 0) or 0):,}")
        data = self.pipeline.personalization.data
        self.language_summary.setText(
            f"{len(data.vocabulary)} vocabulary terms  ·  "
            f"{len(data.replacements)} replacements  ·  {len(data.snippets)} snippets"
        )
        self._analyze_stats()

    def _analyze_stats(self) -> None:
        analysis = analyze_usage(self.pipeline.history.recent(10_000))
        self._longest_entry_id = str(analysis.get("longest_entry_id", ""))
        streak_days = int(analysis["longest_streak"])
        active_days = int(analysis["active_days"])
        self.insight_labels["favorite_word"].setText(str(analysis["favorite_word"]).title())
        self.insight_labels["average_words"].setText(f"{analysis['average_words']} words")
        self.insight_labels["filler_rate"].setText(f"{analysis['filler_rate']}%")
        self.insight_labels["longest_streak"].setText(
            f"{streak_days} {'day' if streak_days == 1 else 'days'}"
        )
        current_streak = int(analysis["current_streak"])
        self.extra_insight_labels["current_streak"].setText(
            f"{current_streak} {'day' if current_streak == 1 else 'days'}"
        )
        self.extra_insight_labels["most_productive_hour"].setText(str(analysis["most_productive_hour"]))
        self.extra_insight_labels["most_used_app"].setText(str(analysis["most_used_app"]))
        self.extra_insight_labels["lifetime_time_saved_minutes"].setText(
            f"{analysis['lifetime_time_saved_minutes']} min"
        )
        self.longest_button.setText(f"Longest dictation · {analysis['longest_dictation']} words  →")
        top_words = ", ".join(
            f"{item['word']} ({item['count']})" for item in analysis.get("top_words", [])
        ) or "No meaningful words yet"
        self.analysis_detail.setText(
            f"Top words: {top_words}  ·  this week {analysis['words_this_week']} words "
            f"({analysis['week_change_percent']:+}%)  ·  filler trend {analysis['filler_trend']:+}%  ·  "
            f"cleanup reduction {analysis['cleanup_reduction']}%  ·  smart fallback "
            f"{analysis['smart_fallback_rate']}%  ·  active on {active_days} days"
        )

    def _open_longest(self) -> None:
        if getattr(self, "_longest_entry_id", ""):
            self.on_open_history_entry(self._longest_entry_id)

    def _preferences_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 18, 24, 18)
        layout.addWidget(self._heading("Preferences", "Simple global behavior—no separate work, email, or personal profiles."))
        layout.addSpacing(24)

        layout.addWidget(QLabel("APPEARANCE", objectName="fieldTitle"))
        self.theme_combo = QComboBox()
        for label, value in (("System", "system"), ("Light", "light"), ("Dark", "dark")):
            self.theme_combo.addItem(label, value)
        self.theme_combo.setCurrentIndex(max(0, self.theme_combo.findData(self.pipeline.config.theme_mode)))
        layout.addWidget(self.theme_combo)

        self.context_check = QCheckBox("Read bounded text around the focused cursor")
        self.context_check.setChecked(self.pipeline.config.context_awareness)
        self.direct_check = QCheckBox("Prefer direct Windows accessibility insertion")
        self.direct_check.setChecked(self.pipeline.config.direct_insertion)
        self.partial_check = QCheckBox("Show live partial transcript using isolated CPU model")
        self.partial_check.setChecked(self.pipeline.config.partial_transcription)
        self.overlay_check = QCheckBox("Show the ambient dot and transcript while running in the tray")
        self.overlay_check.setChecked(self.pipeline.config.show_compact_overlay)
        self.tray_check = QCheckBox("Keep running in the system tray when the dashboard closes")
        self.tray_check.setChecked(self.pipeline.config.close_to_tray)
        self.startup_check = QCheckBox("Run yapper_ automatically after I sign in to Windows")
        self.startup_check.setChecked(is_startup_enabled() or self.pipeline.config.run_at_startup)
        for control in (
            self.context_check,
            self.direct_check,
            self.partial_check,
            self.overlay_check,
            self.tray_check,
            self.startup_check,
        ):
            layout.addWidget(control)
        layout.addSpacing(16)
        layout.addWidget(QLabel("PRIVACY & TESTING  ·  ALL OFF BY DEFAULT", objectName="fieldTitle"))
        self.diagnostics_check = QCheckBox("Share anonymous diagnostics when I submit feedback")
        self.diagnostics_check.setChecked(self.pipeline.config.share_anonymous_diagnostics)
        self.transcripts_check = QCheckBox("Allow me to include selected transcripts in feedback")
        self.transcripts_check.setChecked(self.pipeline.config.allow_selected_transcripts)
        self.full_export_check = QCheckBox("Enable manual export of my complete testing dataset")
        self.full_export_check.setChecked(self.pipeline.config.enable_complete_data_export)
        for control in (self.diagnostics_check, self.transcripts_check, self.full_export_check):
            layout.addWidget(control)
        action_row = QHBoxLayout()
        downloads = QPushButton("Manage local AI downloads")
        downloads.clicked.connect(lambda: self._select_page(5))
        export = QPushButton("Export testing data…")
        export.clicked.connect(self._export_testing_data)
        calibrate = QPushButton("Run microphone calibration")
        calibrate.clicked.connect(self.on_calibrate)
        action_row.addWidget(downloads)
        action_row.addWidget(export)
        action_row.addWidget(calibrate)
        action_row.addStretch()
        layout.addLayout(action_row)
        layout.addStretch()
        save = QPushButton("Save preferences")
        save.setObjectName("accentButton")
        save.clicked.connect(self._save_preferences)
        layout.addWidget(save, 0, Qt.AlignLeft)
        return page

    def _vocabulary_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 18, 24, 18)
        layout.addWidget(self._heading(
            "Vocabulary",
            "Names, brands, and specialist terms that Whisper should prioritize. Double-click any item to edit it.",
        ))
        layout.addSpacing(16)
        self.vocabulary_list = QListWidget()
        self.vocabulary_list.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.vocabulary_list.setEditTriggers(
            QAbstractItemView.DoubleClicked | QAbstractItemView.EditKeyPressed
        )
        self.vocabulary_list.setContextMenuPolicy(Qt.CustomContextMenu)
        self.vocabulary_list.customContextMenuRequested.connect(
            self._show_vocabulary_context_menu
        )
        for value in self.pipeline.personalization.data.vocabulary:
            self._append_vocabulary_item(value)
        self.vocabulary_list.itemChanged.connect(self._vocabulary_item_changed)
        row = QHBoxLayout()
        add = QPushButton("Add word or phrase")
        edit = QPushButton("Edit selected")
        remove = QPushButton("Remove selected")
        add.clicked.connect(self._add_vocabulary)
        edit.clicked.connect(self._edit_vocabulary)
        remove.clicked.connect(self._remove_vocabulary)
        row.addWidget(add)
        row.addWidget(edit)
        row.addWidget(remove)
        row.addStretch()
        layout.addLayout(row)
        layout.addWidget(self.vocabulary_list)
        return page

    def _pairs_page(self, kind: str) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 18, 24, 18)
        title = "Snippets" if kind == "snippets" else "Replacements"
        detail = (
            "Say a short trigger and insert a reusable block of text. Double-click any cell to edit it."
            if kind == "snippets"
            else "Correct predictable recognition mistakes automatically. Double-click any cell to edit it."
        )
        layout.addWidget(self._heading(title, detail))
        layout.addSpacing(16)
        table = QTableWidget(0, 2)
        table.setHorizontalHeaderLabels(
            ("When you say", "Insert exactly") if kind == "snippets" else ("Heard as", "Replace with")
        )
        table.horizontalHeader().setStretchLastSection(True)
        table.verticalHeader().hide()
        table.setSelectionMode(QAbstractItemView.ExtendedSelection)
        table.setEditTriggers(
            QAbstractItemView.DoubleClicked
            | QAbstractItemView.EditKeyPressed
            | QAbstractItemView.SelectedClicked
        )
        pairs = getattr(self.pipeline.personalization.data, kind)
        for key, value in pairs.items():
            self._append_pair(table, key, value)
        setattr(self, f"{kind}_table", table)
        table.itemChanged.connect(lambda item, value=kind: self._pair_item_changed(value, item))
        table.setContextMenuPolicy(Qt.CustomContextMenu)
        table.customContextMenuRequested.connect(
            lambda position, value=kind: self._show_pair_context_menu(value, position)
        )
        row = QHBoxLayout()
        add = QPushButton("Add")
        edit = QPushButton("Edit selected")
        remove = QPushButton("Remove selected")
        add.clicked.connect(lambda: self._add_pair(kind))
        edit.clicked.connect(lambda: self._edit_pair(kind))
        remove.clicked.connect(lambda: self._remove_pair(kind))
        row.addWidget(add)
        row.addWidget(edit)
        row.addWidget(remove)
        row.addStretch()
        layout.addLayout(row)
        layout.addWidget(table)
        return page

    def _api_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 18, 24, 18)
        layout.addWidget(self._heading(
            "API connection",
            "Connect any provider in three clear steps. Nothing goes online until you save the connection.",
        ))
        layout.addSpacing(18)

        card = QFrame()
        card.setObjectName("apiCard")
        apply_soft_shadow(card, 32, 9)
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(26, 24, 26, 25)
        card_layout.setSpacing(11)

        def add_step(number: str, title: str, detail: str) -> None:
            row = QHBoxLayout()
            badge = QLabel(number)
            badge.setObjectName("stepNumber")
            badge.setAlignment(Qt.AlignCenter)
            badge.setFixedSize(28, 28)
            text = QVBoxLayout()
            text.setSpacing(1)
            heading = QLabel(title)
            heading.setStyleSheet("font-size: 15px; font-weight: 700;")
            description = QLabel(detail)
            description.setObjectName("hint")
            text.addWidget(heading)
            text.addWidget(description)
            row.addWidget(badge, 0, Qt.AlignTop)
            row.addSpacing(5)
            row.addLayout(text, 1)
            card_layout.addLayout(row)

        add_step("1", "Add your key", "It stays encrypted for this Windows account.")
        self.api_key = QLineEdit()
        self.api_key.setEchoMode(QLineEdit.Password)
        existing = self.credentials.load()
        if existing:
            self.api_key.setPlaceholderText("Saved securely for this Windows user")
        else:
            self.api_key.setPlaceholderText("Paste a key")
        card_layout.addWidget(self.api_key)
        row = QHBoxLayout()
        self.detect_models_button = QPushButton("REFRESH MODELS" if existing else "FIND MODELS")
        self.detect_models_button.setObjectName("accentButton")
        self.clear_api_button = QPushButton("Remove saved key")
        self.api_advanced_button = QPushButton("Advanced / custom provider")
        self.detect_models_button.clicked.connect(self._save_api)
        self.clear_api_button.clicked.connect(self._clear_api)
        self.api_advanced_button.clicked.connect(self._toggle_api_advanced)
        row.addWidget(self.detect_models_button)
        row.addWidget(self.clear_api_button)
        row.addWidget(self.api_advanced_button)
        row.addStretch()
        card_layout.addLayout(row)
        if self.pipeline.config.api_enabled and self.pipeline.config.api_model:
            initial_status = (
                f"Online profile · {self.pipeline.config.api_provider} · "
                f"{self.pipeline.config.api_model}"
            )
        elif existing:
            initial_status = "A key is saved. Refresh models, choose one, then save the connection."
        else:
            initial_status = "OpenAI, Anthropic, Gemini, Groq, OpenRouter, Mistral, Cohere, xAI, and custom providers are supported."
        self.api_status = QLabel(initial_status)
        self.api_status.setObjectName("hint")
        self.api_status.setWordWrap(True)
        card_layout.addWidget(self.api_status)

        card_layout.addSpacing(10)
        add_step("2", "Choose a model", "Select a discovered model or type its exact ID.")
        self.api_model_label = QLabel("AVAILABLE MODELS", objectName="fieldTitle")
        card_layout.addWidget(self.api_model_label)
        self.api_model = QComboBox()
        self.api_model.setObjectName("modelPicker")
        self.api_model.setEditable(False)
        self.api_model.setInsertPolicy(QComboBox.NoInsert)
        self.api_model.setPlaceholderText("Models appear after the key is checked")
        if self.pipeline.config.api_model:
            self.api_model.addItem(self.pipeline.config.api_model)
            self.api_model.setCurrentText(self.pipeline.config.api_model)
        self.api_model.currentTextChanged.connect(self._api_model_changed)
        model_row = QHBoxLayout()
        model_row.addWidget(self.api_model, 1)
        self.open_models_button = QPushButton("CHOOSE MODEL  ▾")
        self.open_models_button.clicked.connect(self.api_model.showPopup)
        model_row.addWidget(self.open_models_button)
        card_layout.addLayout(model_row)
        show_model = bool(self.pipeline.config.api_model)
        self.api_model_label.setVisible(show_model)
        self.api_model.setVisible(show_model)
        self.open_models_button.setVisible(show_model)
        self.clear_api_button.setVisible(bool(existing or self.pipeline.config.api_enabled))

        card_layout.addSpacing(10)
        add_step("3", "Save the connection", "The header changes to ONLINE when this profile is active.")
        save_row = QHBoxLayout()
        self.save_api_button = QPushButton("SAVE CONNECTION")
        self.save_api_button.setObjectName("accentButton")
        self.save_api_button.clicked.connect(self._commit_api)
        self.save_api_button.setVisible(show_model)
        self.save_api_button.setEnabled(bool(self.api_model.currentText().strip()))
        save_row.addWidget(self.save_api_button)
        save_row.addStretch()
        card_layout.addLayout(save_row)

        self.api_advanced = QFrame()
        advanced_layout = QVBoxLayout(self.api_advanced)
        advanced_layout.setContentsMargins(0, 12, 0, 0)
        advanced_layout.addWidget(QLabel("PROVIDER", objectName="fieldTitle"))
        self.api_provider_choice = QComboBox()
        for preset in PROVIDER_PRESETS:
            self.api_provider_choice.addItem(preset.name, preset.key)
        self.api_provider_choice.addItem("Custom provider", "custom")
        advanced_layout.addWidget(self.api_provider_choice)
        advanced_layout.addWidget(QLabel("PROVIDER NAME", objectName="fieldTitle"))
        self.api_provider = QLineEdit(self.pipeline.config.api_provider or "Custom provider")
        advanced_layout.addWidget(self.api_provider)
        advanced_layout.addWidget(QLabel("API BASE URL", objectName="fieldTitle"))
        self.api_base_url = QLineEdit(self.pipeline.config.api_base_url)
        self.api_base_url.setPlaceholderText("https://provider.example/v1")
        advanced_layout.addWidget(self.api_base_url)
        endpoint_row = QHBoxLayout()
        self.api_models_path = QLineEdit(self.pipeline.config.api_models_path)
        self.api_models_path.setPlaceholderText("Models path, usually /models")
        endpoint_row.addWidget(self.api_models_path)
        self.api_key_header = QLineEdit(self.pipeline.config.api_key_header)
        self.api_key_header.setPlaceholderText("Key header")
        endpoint_row.addWidget(self.api_key_header)
        self.api_key_prefix = QLineEdit(self.pipeline.config.api_key_prefix)
        self.api_key_prefix.setPlaceholderText("Value prefix")
        endpoint_row.addWidget(self.api_key_prefix)
        advanced_layout.addLayout(endpoint_row)
        card_layout.addWidget(self.api_advanced)
        self.api_advanced.hide()

        configured_preset = provider_preset(self.pipeline.config.api_provider)
        if configured_preset:
            configured_index = self.api_provider_choice.findData(configured_preset.key)
            self.api_provider_choice.setCurrentIndex(max(0, configured_index))
        else:
            self.api_provider_choice.setCurrentIndex(self.api_provider_choice.count() - 1)
        self.api_provider_choice.currentIndexChanged.connect(self._api_provider_changed)
        layout.addWidget(card)
        layout.addStretch()
        return page

    def _toggle_api_advanced(self) -> None:
        visible = not self.api_advanced.isVisible()
        self.api_advanced.setVisible(visible)
        self.api_advanced_button.setText("Hide advanced" if visible else "Advanced / custom provider")

    def _api_provider_changed(self, index: int) -> None:
        preset = provider_preset(str(self.api_provider_choice.itemData(index) or ""))
        if preset:
            self._apply_provider_preset(preset)

    def _apply_provider_preset(self, preset) -> None:
        index = self.api_provider_choice.findData(preset.key)
        if index >= 0:
            self.api_provider_choice.blockSignals(True)
            self.api_provider_choice.setCurrentIndex(index)
            self.api_provider_choice.blockSignals(False)
        self.api_provider.setText(preset.name)
        self.api_base_url.setText(preset.base_url)
        self.api_models_path.setText(preset.models_path)
        self.api_key_header.setText(preset.api_key_header)
        self.api_key_prefix.setText(preset.api_key_prefix)

    def _api_model_changed(self, model: str) -> None:
        model = model.strip()
        if hasattr(self, "save_api_button"):
            self.save_api_button.setEnabled(bool(model))
            self.save_api_button.setText("SAVE CONNECTION")
        if model and self.api_model.isVisible():
            self._set_api_status("Model selected. Save the connection to make it active.")

    def _set_api_status(self, text: str, state: str = "hint") -> None:
        object_name = {
            "success": "successText",
            "error": "errorText",
        }.get(state, "hint")
        self.api_status.setText(text)
        self.api_status.setObjectName(object_name)
        self.api_status.style().unpolish(self.api_status)
        self.api_status.style().polish(self.api_status)

    @staticmethod
    def _append_pair(table: QTableWidget, key: str, value: str) -> None:
        was_blocked = table.blockSignals(True)
        try:
            row = table.rowCount()
            table.insertRow(row)
            key_item = QTableWidgetItem(key)
            key_item.setData(Qt.UserRole, key)
            value_item = QTableWidgetItem(value)
            value_item.setData(Qt.UserRole, value)
            table.setItem(row, 0, key_item)
            table.setItem(row, 1, value_item)
        finally:
            table.blockSignals(was_blocked)

    def _append_vocabulary_item(self, value: str) -> QListWidgetItem:
        was_blocked = self.vocabulary_list.blockSignals(True)
        try:
            item = QListWidgetItem(value)
            item.setData(Qt.UserRole, value)
            item.setFlags(item.flags() | Qt.ItemIsEditable)
            self.vocabulary_list.addItem(item)
            return item
        finally:
            self.vocabulary_list.blockSignals(was_blocked)

    def _edit_vocabulary(self) -> None:
        item = self.vocabulary_list.currentItem()
        if item:
            self.vocabulary_list.editItem(item)

    def _show_vocabulary_context_menu(self, position) -> None:
        item = self.vocabulary_list.itemAt(position)
        if item is not None:
            if not item.isSelected():
                self.vocabulary_list.clearSelection()
                item.setSelected(True)
            self.vocabulary_list.setCurrentItem(item)

        has_selection = bool(self.vocabulary_list.selectedItems())
        has_clipboard = bool(QApplication.clipboard().text().strip())
        menu = QMenu(self.vocabulary_list)
        edit = menu.addAction("Edit")
        cut = menu.addAction("Cut")
        copy = menu.addAction("Copy")
        paste = menu.addAction("Paste")
        delete = menu.addAction("Delete")
        menu.addSeparator()
        select_all = menu.addAction("Select All")
        edit.setEnabled(self.vocabulary_list.currentItem() is not None)
        cut.setEnabled(has_selection)
        copy.setEnabled(has_selection)
        paste.setEnabled(has_clipboard)
        delete.setEnabled(has_selection)
        edit.triggered.connect(self._edit_vocabulary)
        cut.triggered.connect(self._cut_vocabulary)
        copy.triggered.connect(self._copy_vocabulary)
        paste.triggered.connect(self._paste_vocabulary)
        delete.triggered.connect(self._remove_vocabulary)
        select_all.triggered.connect(self.vocabulary_list.selectAll)
        menu.exec(self.vocabulary_list.viewport().mapToGlobal(position))

    def _copy_vocabulary(self) -> None:
        items = self.vocabulary_list.selectedItems()
        if not items and self.vocabulary_list.currentItem():
            items = [self.vocabulary_list.currentItem()]
        if items:
            QApplication.clipboard().setText("\n".join(item.text() for item in items))

    def _cut_vocabulary(self) -> None:
        self._copy_vocabulary()
        self._remove_vocabulary()

    def _paste_vocabulary(self) -> None:
        values = [
            line.strip()
            for line in QApplication.clipboard().text().splitlines()
            if line.strip()
        ]
        existing = {
            item.casefold() for item in self.pipeline.personalization.data.vocabulary
        }
        added: list[QListWidgetItem] = []
        for value in values:
            if value.casefold() in existing:
                continue
            self.pipeline.personalization.add_vocabulary(value)
            added.append(self._append_vocabulary_item(value))
            existing.add(value.casefold())
        if added:
            self.pipeline.reload_personalization()
            self.vocabulary_list.clearSelection()
            for item in added:
                item.setSelected(True)
            self.vocabulary_list.setCurrentItem(added[-1])

    def _vocabulary_item_changed(self, item: QListWidgetItem) -> None:
        old_value = str(item.data(Qt.UserRole) or "")
        new_value = item.text().strip()
        if old_value == new_value:
            return
        if not self.pipeline.personalization.update_vocabulary(old_value, new_value):
            was_blocked = self.vocabulary_list.blockSignals(True)
            item.setText(old_value)
            self.vocabulary_list.blockSignals(was_blocked)
            QMessageBox.warning(
                self,
                "Vocabulary",
                "Vocabulary entries cannot be empty or duplicated.",
            )
            return
        was_blocked = self.vocabulary_list.blockSignals(True)
        item.setText(new_value)
        item.setData(Qt.UserRole, new_value)
        self.vocabulary_list.blockSignals(was_blocked)
        self.pipeline.reload_personalization()

    def _add_vocabulary(self) -> None:
        value, accepted = QInputDialog.getText(self, "Vocabulary", "Word or phrase to prioritize:")
        if accepted and value.strip():
            clean_value = value.strip()
            existing = {
                item.casefold() for item in self.pipeline.personalization.data.vocabulary
            }
            if clean_value.casefold() in existing:
                QMessageBox.information(self, "Vocabulary", "That entry already exists.")
                return
            self.pipeline.personalization.add_vocabulary(clean_value)
            self.pipeline.reload_personalization()
            item = self._append_vocabulary_item(clean_value)
            self.vocabulary_list.setCurrentItem(item)

    def _remove_vocabulary(self) -> None:
        items = self.vocabulary_list.selectedItems()
        if not items and self.vocabulary_list.currentItem():
            items = [self.vocabulary_list.currentItem()]
        for item in items:
            self.pipeline.personalization.remove_vocabulary(str(item.data(Qt.UserRole) or item.text()))
        if items:
            self.pipeline.reload_personalization()
            for item in items:
                self.vocabulary_list.takeItem(self.vocabulary_list.row(item))

    def _edit_pair(self, kind: str) -> None:
        table: QTableWidget = getattr(self, f"{kind}_table")
        item = table.currentItem()
        if item is None and table.currentRow() >= 0:
            item = table.item(table.currentRow(), 0)
        if item:
            table.editItem(item)

    def _show_pair_context_menu(self, kind: str, position) -> None:
        table: QTableWidget = getattr(self, f"{kind}_table")
        item = table.itemAt(position)
        if item is not None:
            if not item.isSelected():
                table.clearSelection()
                item.setSelected(True)
            table.setCurrentItem(item)

        has_selection = bool(table.selectedItems())
        has_clipboard = bool(QApplication.clipboard().text())
        menu = QMenu(table)
        edit = menu.addAction("Edit")
        cut = menu.addAction("Cut")
        copy = menu.addAction("Copy")
        paste = menu.addAction("Paste")
        delete = menu.addAction("Delete")
        menu.addSeparator()
        select_all = menu.addAction("Select All")
        edit.setEnabled(table.currentItem() is not None)
        cut.setEnabled(has_selection)
        copy.setEnabled(has_selection)
        paste.setEnabled(has_clipboard and table.currentItem() is not None)
        delete.setEnabled(has_selection)
        edit.triggered.connect(lambda: self._edit_pair(kind))
        cut.triggered.connect(lambda: self._cut_pair(kind))
        copy.triggered.connect(lambda: self._copy_pair(kind))
        paste.triggered.connect(lambda: self._paste_pair(kind))
        delete.triggered.connect(lambda: self._remove_pair(kind))
        select_all.triggered.connect(table.selectAll)
        menu.exec(table.viewport().mapToGlobal(position))

    def _copy_pair(self, kind: str) -> None:
        table: QTableWidget = getattr(self, f"{kind}_table")
        ranges = table.selectedRanges()
        if not ranges and table.currentItem() is not None:
            QApplication.clipboard().setText(table.currentItem().text())
            return
        if not ranges:
            return
        selection = ranges[0]
        lines = []
        for row in range(selection.topRow(), selection.bottomRow() + 1):
            cells = []
            for column in range(selection.leftColumn(), selection.rightColumn() + 1):
                item = table.item(row, column)
                cells.append(item.text() if item else "")
            lines.append("\t".join(cells))
        QApplication.clipboard().setText("\n".join(lines))

    def _cut_pair(self, kind: str) -> None:
        self._copy_pair(kind)
        self._remove_pair(kind)

    def _paste_pair(self, kind: str) -> None:
        table: QTableWidget = getattr(self, f"{kind}_table")
        item = table.currentItem()
        if item is not None:
            item.setText(QApplication.clipboard().text())

    def _pair_item_changed(self, kind: str, item: QTableWidgetItem) -> None:
        table: QTableWidget = getattr(self, f"{kind}_table")
        row = item.row()
        key_item = table.item(row, 0)
        value_item = table.item(row, 1)
        if key_item is None or value_item is None:
            return
        old_key = str(key_item.data(Qt.UserRole) or "")
        old_value = str(value_item.data(Qt.UserRole) or "")
        new_key = key_item.text().strip()
        new_value = value_item.text()
        saved_key = (
            self.pipeline.personalization.normalize_trigger(new_key)
            if kind == "snippets"
            else new_key
        )
        if old_key == saved_key and old_value == new_value:
            return
        if not self.pipeline.personalization.update_pair(
            kind, old_key, saved_key, new_value
        ):
            was_blocked = table.blockSignals(True)
            key_item.setText(old_key)
            value_item.setText(old_value)
            table.blockSignals(was_blocked)
            QMessageBox.warning(
                self,
                kind.title(),
                "Triggers and values cannot be empty, and triggers must be unique.",
            )
            return
        was_blocked = table.blockSignals(True)
        key_item.setText(saved_key)
        key_item.setData(Qt.UserRole, saved_key)
        value_item.setData(Qt.UserRole, new_value)
        table.blockSignals(was_blocked)
        self.pipeline.reload_personalization()

    def _add_pair(self, kind: str) -> None:
        first_label = "Voice trigger:" if kind == "snippets" else "When yapper_ hears:"
        key, accepted = QInputDialog.getText(self, kind.title(), first_label)
        if not accepted or not key.strip():
            return
        value, accepted = QInputDialog.getMultiLineText(
            self,
            kind.title(),
            "Expansion text:" if kind == "snippets" else "Replace it with:",
        )
        if not accepted or not value:
            return
        clean_key = (
            self.pipeline.personalization.normalize_trigger(key)
            if kind == "snippets"
            else key.strip()
        )
        pairs = getattr(self.pipeline.personalization.data, kind)
        if clean_key in pairs:
            QMessageBox.information(self, kind.title(), "That trigger already exists. Edit its row instead.")
            return
        if kind == "snippets":
            self.pipeline.personalization.set_snippet(clean_key, value)
        else:
            self.pipeline.personalization.set_replacement(clean_key, value)
        self.pipeline.reload_personalization()
        self._append_pair(getattr(self, f"{kind}_table"), clean_key, value)

    def _remove_pair(self, kind: str) -> None:
        table: QTableWidget = getattr(self, f"{kind}_table")
        rows = {index.row() for index in table.selectedIndexes()}
        if not rows and table.currentRow() >= 0:
            rows = {table.currentRow()}
        valid_rows = sorted(
            (row for row in rows if table.item(row, 0) is not None),
            reverse=True,
        )
        if not valid_rows:
            return
        for row in valid_rows:
            key_item = table.item(row, 0)
            key = str(key_item.data(Qt.UserRole) or key_item.text())
            if kind == "snippets":
                self.pipeline.personalization.remove_snippet(key)
            else:
                self.pipeline.personalization.remove_replacement(key)
            table.removeRow(row)
        self.pipeline.reload_personalization()

    def _save_preferences(self) -> None:
        config = self.pipeline.config
        config.context_awareness = self.context_check.isChecked()
        config.direct_insertion = self.direct_check.isChecked()
        config.partial_transcription = self.partial_check.isChecked()
        config.show_compact_overlay = self.overlay_check.isChecked()
        config.close_to_tray = self.tray_check.isChecked()
        config.run_at_startup = self.startup_check.isChecked()
        config.theme_mode = str(self.theme_combo.currentData() or "dark")
        config.share_anonymous_diagnostics = self.diagnostics_check.isChecked()
        config.allow_selected_transcripts = self.transcripts_check.isChecked()
        config.enable_complete_data_export = self.full_export_check.isChecked()
        try:
            set_startup_enabled(config.run_at_startup)
        except OSError as exc:
            QMessageBox.warning(self, "Run at startup", f"Windows could not update startup: {exc}")
            config.run_at_startup = is_startup_enabled()
            self.startup_check.setChecked(config.run_at_startup)
        config.save()
        self.pipeline.reload_personalization()
        self.on_saved()
        self.refresh_stats()

    def _export_testing_data(self) -> None:
        if not self.full_export_check.isChecked():
            QMessageBox.information(
                self, "Testing export is off",
                "Turn on the complete testing-data option first. Nothing is exported automatically."
            )
            return
        folder = QFileDialog.getExistingDirectory(self, "Choose where to save the testing ZIP")
        if not folder:
            return
        try:
            output = create_testing_export(
                self.pipeline.config,
                self.pipeline.history,
                DATA_DIR / "metrics.jsonl",
                __import__("pathlib").Path(folder),
            )
        except Exception as exc:
            QMessageBox.warning(self, "Export failed", str(exc))
            return
        QApplication.clipboard().setText(str(output))
        message = QMessageBox(self)
        message.setWindowTitle("Testing data exported")
        message.setText(f"Created {output.name}. The path is copied; you decide whether to send it.")
        open_folder = message.addButton("Open folder", QMessageBox.AcceptRole)
        email = message.addButton("Open email draft", QMessageBox.ActionRole)
        message.addButton(QMessageBox.Close)
        message.exec()
        if message.clickedButton() is open_folder:
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(output.parent)))
        elif message.clickedButton() is email:
            address = self.pipeline.config.feedback_email.strip()
            if address:
                QDesktopServices.openUrl(QUrl(f"mailto:{address}?subject=yapper_%20testing%20data"))
            else:
                QMessageBox.information(self, "Email setup pending", "The feedback email has not been configured yet.")

    def _save_api(self) -> None:
        try:
            entered_key = self.api_key.text().strip()
            raw_key = entered_key or self.credentials.load()
            if not raw_key:
                local_url = self.api_base_url.text().strip().casefold()
                if not (
                    self.api_advanced.isVisible()
                    and local_url.startswith(("http://localhost", "http://127.0.0.1"))
                ):
                    raise ValueError("Paste an API key first")

            detected, clean_key = detect_provider_from_key(raw_key) if raw_key else (None, "")
            selected = provider_preset(
                str(self.api_provider_choice.currentData() or "")
            )
            if not self.api_advanced.isVisible():
                if detected is None:
                    self.api_advanced.show()
                    self.api_advanced_button.setText("Hide advanced")
                    self.api_status.setText(
                        "This key has no provider prefix. Choose its provider below, then connect again."
                    )
                    return
                selected = detected
                self._apply_provider_preset(selected)
            elif detected and selected is None:
                selected = detected
                self._apply_provider_preset(selected)

            provider = self.api_provider.text().strip()
            if not provider:
                raise ValueError("Add a provider name")
            base_url = self.api_base_url.text().strip()
            self._pending_api_key = clean_key
            self._pending_api_settings = {
                "provider": provider,
                "base_url": base_url,
                "models_path": self.api_models_path.text().strip() or "/models",
                "key_header": self.api_key_header.text().strip(),
                "key_prefix": self.api_key_prefix.text().strip(),
            }
            self._api_discovery_verified = False
            self.detect_models_button.setEnabled(False)
            self.detect_models_button.setText("FINDING MODELS…")
            self._set_api_status(f"Checking {provider} and loading its model list…")

            def discover() -> None:
                try:
                    models = list_available_models(
                        base_url,
                        clean_key,
                        models_path=self._pending_api_settings["models_path"],
                        api_key_header=self._pending_api_settings["key_header"],
                        api_key_prefix=self._pending_api_settings["key_prefix"],
                        provider=provider,
                    )
                    self.models_discovered.emit(models, "")
                except Exception as exc:
                    self.models_discovered.emit([], str(exc))

            threading.Thread(target=discover, name="api-model-discovery", daemon=True).start()
        except Exception as exc:
            self._set_api_status(f"Could not check the connection: {exc}", "error")

    def _models_discovered(self, models: list, error: str) -> None:
        self.detect_models_button.setEnabled(True)
        self.detect_models_button.setText("REFRESH MODELS")
        if error:
            self._api_discovery_verified = False
            if "credentials were rejected" in error.casefold():
                self._set_api_status(error + ". Check the key and try again.", "error")
                return
            self.api_model_label.show()
            self.api_model.show()
            self.api_model.setEditable(True)
            self.open_models_button.setText("TYPE MODEL ID")
            self.open_models_button.clicked.disconnect()
            self.open_models_button.clicked.connect(
                lambda checked=False: self.api_model.setFocus()
            )
            self.open_models_button.show()
            self.save_api_button.show()
            self.save_api_button.setEnabled(bool(self.api_model.currentText().strip()))
            self._set_api_status(
                f"{error}. If this provider does not list models, type the exact model ID above and save.",
                "error",
            )
            return
        selected = self.pipeline.config.api_model
        self.api_model.blockSignals(True)
        self.api_model.setEditable(False)
        self.api_model.clear()
        for model in models:
            self.api_model.addItem(str(model))
        if selected and selected in models:
            self.api_model.setCurrentText(selected)
        elif models:
            self.api_model.setCurrentIndex(0)
        self.api_model.blockSignals(False)
        self._api_discovery_verified = True
        self.api_model_label.show()
        self.api_model_label.setText(f"AVAILABLE MODELS  ·  {len(models)}")
        self.api_model.show()
        self.open_models_button.setText("CHOOSE MODEL  ▾")
        try:
            self.open_models_button.clicked.disconnect()
        except RuntimeError:
            pass
        self.open_models_button.clicked.connect(self.api_model.showPopup)
        self.open_models_button.show()
        self.save_api_button.show()
        self.save_api_button.setEnabled(bool(self.api_model.currentText().strip()))
        self.api_advanced.hide()
        self.api_advanced_button.setText("Advanced / custom provider")
        provider = (self._pending_api_settings or {}).get("provider", "provider")
        self._set_api_status(
            f"Found {len(models)} models from {provider}. Choose one, then save the connection.",
            "success",
        )

    def _commit_api(self) -> None:
        model = self.api_model.currentText().strip()
        if not model:
            self._set_api_status("Choose a model before saving the connection.", "error")
            return
        settings = self._pending_api_settings or {
            "provider": self.pipeline.config.api_provider,
            "base_url": self.pipeline.config.api_base_url,
            "models_path": self.pipeline.config.api_models_path,
            "key_header": self.pipeline.config.api_key_header,
            "key_prefix": self.pipeline.config.api_key_prefix,
        }
        existing_key = self.credentials.load()
        local_endpoint = settings["base_url"].casefold().startswith(
            ("http://localhost", "http://127.0.0.1")
        )
        if not (self._pending_api_key or existing_key or local_endpoint):
            self._set_api_status("Add the key and find models before saving.", "error")
            return
        try:
            if self._pending_api_key:
                self.credentials.save(self._pending_api_key)
            config = self.pipeline.config
            config.api_provider = settings["provider"]
            config.api_base_url = settings["base_url"]
            config.api_models_path = settings["models_path"]
            config.api_key_header = settings["key_header"]
            config.api_key_prefix = settings["key_prefix"]
            config.api_model = model
            config.api_enabled = True
            config.save()
        except Exception as exc:
            self._set_api_status(f"Could not save the connection: {exc}", "error")
            return
        self._pending_api_key = ""
        self._pending_api_settings = None
        self.api_key.clear()
        self.api_key.setPlaceholderText("Saved securely for this Windows user")
        self.clear_api_button.show()
        self.save_api_button.setText("SAVED · ONLINE")
        self._set_api_status(
            f"Online with {config.api_provider} · {config.api_model}", "success"
        )
        self.pipeline.reload_api_formatter()
        self.on_saved()

    def _clear_api(self) -> None:
        self.credentials.clear()
        self._pending_api_key = ""
        self._pending_api_settings = None
        self._api_discovery_verified = False
        self.api_key.clear()
        self.api_key.setPlaceholderText("Paste a key")
        self.pipeline.config.api_model = ""
        self.pipeline.config.api_enabled = False
        self.pipeline.config.save()
        self.api_model.blockSignals(True)
        self.api_model.clear()
        self.api_model.setEditText("")
        self.api_model.blockSignals(False)
        self.api_model_label.hide()
        self.api_model.hide()
        self.open_models_button.hide()
        self.save_api_button.hide()
        self.clear_api_button.hide()
        self.detect_models_button.setText("FIND MODELS")
        self._set_api_status("Connection removed. yapper_ is offline and fully local.")
        self.pipeline.reload_api_formatter()
        self.on_saved()

    def connection_ready(self) -> bool:
        config = self.pipeline.config
        local_endpoint = config.api_base_url.casefold().startswith(
            ("http://localhost", "http://127.0.0.1")
        )
        return bool(
            config.api_enabled
            and config.api_model.strip()
            and (local_endpoint or self.credentials.load())
        )

    def saved_connection_available(self) -> bool:
        config = self.pipeline.config
        local_endpoint = config.api_base_url.casefold().startswith(
            ("http://localhost", "http://127.0.0.1")
        )
        return bool(
            config.api_model.strip()
            and config.api_base_url.strip()
            and (local_endpoint or self.credentials.load())
        )


class HistoryPanel(QWidget):
    """Searchable history page embedded in the main application stack."""

    def __init__(
        self, pipeline, on_close: Callable[[], None],
        on_feedback: Callable[[dict[str, object]], None] | None = None, parent=None,
    ):
        super().__init__(parent)
        self.pipeline = pipeline
        self.on_close = on_close
        self.on_feedback = on_feedback or (lambda entry: None)
        self.entries: list[dict[str, object]] = []
        root = QVBoxLayout(self)
        root.setContentsMargins(18, 18, 18, 12)
        root.setSpacing(8)
        title = QLabel("HISTORY")
        title.setObjectName("pageTitle")
        root.addWidget(title)
        description = QLabel("Review, search, copy, or reinsert previous dictations.")
        description.setObjectName("hint")
        root.addWidget(description)
        root.addSpacing(10)
        search_row = QHBoxLayout()
        self.search = QLineEdit()
        self.search.setPlaceholderText("Search raw or formatted text…")
        self.search.textChanged.connect(self.refresh)
        search_row.addWidget(self.search)
        root.addLayout(search_row)

        splitter = QSplitter(Qt.Horizontal)
        self.table = QTableWidget(0, 4)
        self.table.setHorizontalHeaderLabels(("Time", "App", "Cleanup", "Final text"))
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.verticalHeader().hide()
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table.itemSelectionChanged.connect(self._show_selected)
        splitter.addWidget(self.table)

        details = QWidget()
        details_layout = QVBoxLayout(details)
        details_layout.addWidget(QLabel("RAW DICTATION"))
        self.raw = QTextEdit()
        self.raw.setReadOnly(True)
        details_layout.addWidget(self.raw)
        details_layout.addWidget(QLabel("FORMATTED"))
        self.final = QTextEdit()
        self.final.setReadOnly(True)
        details_layout.addWidget(self.final)
        splitter.addWidget(details)
        splitter.setSizes((540, 340))
        apply_soft_shadow(splitter, 24, 6)
        root.addWidget(splitter, 1)

        actions = QHBoxLayout()
        original = QPushButton("Undo latest formatting")
        reinsert = QPushButton("Reinsert formatted")
        copy_raw = QPushButton("Copy raw")
        copy_final = QPushButton("Copy finished")
        feedback = QPushButton("Feedback on this")
        close = QPushButton("Back to dashboard")
        original.clicked.connect(self._undo_latest)
        reinsert.clicked.connect(lambda: self._restore(False))
        copy_raw.clicked.connect(lambda: self._copy(True))
        copy_final.clicked.connect(lambda: self._copy(False))
        feedback.clicked.connect(self._feedback)
        close.clicked.connect(self.on_close)
        actions.addWidget(original)
        actions.addWidget(reinsert)
        actions.addWidget(copy_raw)
        actions.addWidget(copy_final)
        actions.addWidget(feedback)
        actions.addStretch()
        actions.addWidget(close)
        root.addLayout(actions)
        self.refresh()

    def refresh(self) -> None:
        self.entries = self.pipeline.history.recent(200, self.search.text())
        self.table.setRowCount(0)
        for entry in self.entries:
            row = self.table.rowCount()
            self.table.insertRow(row)
            timestamp = datetime.fromtimestamp(float(entry.get("timestamp", 0))).strftime("%d %b  %H:%M")
            values = (
                timestamp,
                str(entry.get("app", "")) or "Unknown",
                {
                    "minimal": "Minimal",
                    "smart": "Smart",
                    "light": "Light",
                    "medium": "Medium",
                    "ai_light": "AI light",
                    "ai_medium": "AI medium",
                }.get(
                    str(entry.get("cleanup_level", "minimal")),
                    str(entry.get("cleanup_level", "minimal")).replace("_", " ").title(),
                ),
                str(entry.get("final", "")).replace("\n", " "),
            )
            for column, value in enumerate(values):
                self.table.setItem(row, column, QTableWidgetItem(value))
        if self.entries:
            self.table.selectRow(0)

    def _selected_entry(self) -> dict[str, object] | None:
        row = self.table.currentRow()
        return self.entries[row] if 0 <= row < len(self.entries) else None

    def _show_selected(self) -> None:
        entry = self._selected_entry()
        self.raw.setPlainText(str(entry.get("raw", "")) if entry else "")
        self.final.setPlainText(str(entry.get("final", "")) if entry else "")

    def _restore(self, raw: bool) -> None:
        entry = self._selected_entry()
        if entry and self.pipeline.restore_history(str(entry.get("id", "")), raw):
            self.on_close()

    def _copy(self, raw: bool) -> None:
        entry = self._selected_entry()
        if entry:
            QApplication.clipboard().setText(str(entry.get("raw" if raw else "final", "")))

    def select_entry(self, entry_id: str) -> None:
        for row, entry in enumerate(self.entries):
            if str(entry.get("id", "")) == entry_id:
                self.table.selectRow(row)
                self.table.scrollToItem(self.table.item(row, 0))
                break

    def _feedback(self) -> None:
        entry = self._selected_entry()
        if entry:
            self.on_feedback(entry)

    def _undo_latest(self) -> None:
        if self.pipeline.undo_last_formatting():
            self.on_close()
