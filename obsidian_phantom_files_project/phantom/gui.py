"""PySide6 desktop UI for scanning an Obsidian vault."""

from __future__ import annotations

import os
from datetime import datetime

from PySide6.QtCore import QSettings, Qt, QThread, QUrl, Signal
from PySide6.QtGui import QAction, QCursor, QDesktopServices, QGuiApplication, QKeySequence
from PySide6.QtWidgets import (
    QApplication,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QSplitter,
    QStackedWidget,
    QStatusBar,
    QTableWidget,
    QTableWidgetItem,
    QToolBar,
    QToolTip,
    QVBoxLayout,
    QWidget,
)

from phantom.actions import trash_paths
from phantom.core import ScanResult, Settings, looks_like_vault, scan
from phantom.report import grouped_broken, write_report

ORG = "obsidian-phantom"
APP = "ObsidianPhantom"

STYLESHEET = """
QMainWindow, QDialog, QWidget {
    background: #1e1e1e;
    color: #dcddde;
    font-size: 13px;
}
QToolBar {
    background: #161616;
    border: none;
    spacing: 8px;
    padding: 10px 14px;
}
QLabel#title {
    font-size: 18px;
    font-weight: 600;
    color: #ffffff;
}
QLabel#subtitle {
    color: #8b8b8b;
    font-size: 12px;
}
QLineEdit, QPlainTextEdit {
    background: #2a2a2a;
    color: #dcddde;
    border: 1px solid #3f3f3f;
    border-radius: 6px;
    padding: 7px 10px;
    selection-background-color: #7f6df2;
}
QLineEdit:focus, QPlainTextEdit:focus {
    border: 1px solid #7f6df2;
}
QPushButton {
    background: #2a2a2a;
    color: #dcddde;
    border: 1px solid #3f3f3f;
    border-radius: 6px;
    padding: 8px 14px;
}
QPushButton:hover {
    background: #333333;
    border-color: #555555;
}
QPushButton:disabled {
    color: #666666;
}
QPushButton#primary {
    background: #7f6df2;
    color: #ffffff;
    border: none;
    font-weight: 600;
    padding: 8px 18px;
}
QPushButton#primary:hover {
    background: #8f80f5;
}
QPushButton#danger {
    background: #3b1f1f;
    color: #ffb4b4;
    border: 1px solid #5a2a2a;
}
QPushButton#danger:hover {
    background: #4a2626;
}
QListWidget {
    background: #161616;
    border: none;
    outline: none;
    padding: 8px;
}
QListWidget::item {
    padding: 10px 12px;
    border-radius: 6px;
    margin-bottom: 4px;
}
QListWidget::item:selected {
    background: #7f6df2;
    color: #ffffff;
}
QTableWidget {
    background: #1e1e1e;
    alternate-background-color: #242424;
    gridline-color: #2f2f2f;
    border: none;
    selection-background-color: #3d3468;
    selection-color: #ffffff;
}
QHeaderView::section {
    background: #161616;
    color: #9b9b9b;
    border: none;
    border-bottom: 1px solid #2f2f2f;
    padding: 8px;
    font-weight: 600;
}
QStatusBar {
    background: #161616;
    color: #8b8b8b;
}
QSplitter::handle {
    background: #2a2a2a;
    width: 1px;
}
QToolTip {
    background: #2a2a2a;
    color: #c8c8c8;
    border: 1px solid #3f3f3f;
    padding: 5px 7px;
    font-size: 11px;
}
QFrame#banner {
    background: #3d3414;
    color: #e6d48a;
    border-radius: 6px;
    padding: 6px;
}
"""


class ScanWorker(QThread):
    finished_ok = Signal(object)
    failed = Signal(str)

    def __init__(self, vault: str, settings: Settings) -> None:
        super().__init__()
        self.vault = vault
        self.settings = settings

    def run(self) -> None:
        try:
            self.finished_ok.emit(scan(self.vault, self.settings))
        except Exception as exc:  # noqa: BLE001 — surface any scan failure in the UI
            self.failed.emit(str(exc))


class SettingsDialog(QDialog):
    def __init__(self, settings: Settings, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Ignore rules")
        self.setMinimumWidth(420)
        layout = QFormLayout(self)
        self.dirs = QPlainTextEdit("\n".join(settings.ignore_dirs))
        self.files = QPlainTextEdit("\n".join(settings.ignore_files))
        self.exts = QPlainTextEdit("\n".join(settings.ignore_extensions))
        self.tags = QPlainTextEdit("\n".join(settings.ignore_tags))
        for widget in (self.dirs, self.files, self.exts, self.tags):
            widget.setPlaceholderText("One per line")
            widget.setFixedHeight(80)
        layout.addRow("Ignore folders", self.dirs)
        layout.addRow("Ignore files", self.files)
        layout.addRow("Ignore extensions", self.exts)
        layout.addRow("Ignore tags", self.tags)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addRow(buttons)

    def settings(self) -> Settings:
        return Settings(
            ignore_dirs=_lines(self.dirs),
            ignore_files=_lines(self.files),
            ignore_extensions=_lines(self.exts),
            ignore_tags=_lines(self.tags),
        )


def _lines(widget: QPlainTextEdit) -> list[str]:
    return [line.strip() for line in widget.toPlainText().splitlines() if line.strip()]


NAV_TIPS = {
    "Broken links": (
        "Broken means a [[wikilink]] or markdown link whose target file does not exist.\n"
        "The note under Found in is the source of that link — it is not junk and will not be deleted.\n"
        "Code that looks like [[this]] (for example a bash test) can show up here too."
    ),
    "Orphans": (
        "Orphan means nothing in the vault [[links]] or embeds this file.\n"
        "It is not empty, and it will not be deleted.\n"
        "Notes you open from the file list still count if no other note points at them."
    ),
    "Junk files": (
        "Junk is filename clutter: ._* AppleDouble files, .DS_Store, Thumbs.db, and desktop.ini.\n"
        "A normal note is never junk, even if it is broken or orphaned.\n"
        "Only this list can be moved to .trash — and only after you confirm."
    ),
    "Empty files": (
        "Empty means the file has no body (a note with only YAML frontmatter counts).\n"
        "That does not make it junk, and it will not be deleted.\n"
        "This list is informational only."
    ),
    "Empty folders": (
        "Empty folders have no visible files left in them.\n"
        "They are leftover directory clutter, not missing notes.\n"
        "Nothing here is deleted automatically."
    ),
}


def _nav_item(label: str, count: int) -> QListWidgetItem:
    item = QListWidgetItem(f"{label}\n{count}")
    tip = NAV_TIPS.get(label)
    if tip:
        item.setToolTip(tip)
    return item


class MainWindow(QMainWindow):
    def __init__(self, vault: str | None = None) -> None:
        super().__init__()
        self.settings_store = QSettings(ORG, APP)
        self.scan_settings = Settings()
        self.result: ScanResult | None = None
        self.worker: ScanWorker | None = None

        self.setWindowTitle("Obsidian Phantom")
        self.resize(1100, 720)

        self.vault_input = QLineEdit()
        self.vault_input.setPlaceholderText("Path to your Obsidian vault (the folder with .obsidian)")
        remembered = vault or self.settings_store.value("last_vault", "", str)
        if remembered:
            self.vault_input.setText(remembered)

        self.banner = QLabel("This folder has no .obsidian directory. It will still be scanned.")
        self.banner.setObjectName("banner")
        self.banner.setVisible(False)
        self.banner.setWordWrap(True)

        browse = QPushButton("Browse")
        browse.clicked.connect(self.browse_vault)
        self.scan_btn = QPushButton("Scan")
        self.scan_btn.setObjectName("primary")
        self.scan_btn.clicked.connect(self.start_scan)

        vault_row = QHBoxLayout()
        vault_row.addWidget(self.vault_input, 1)
        vault_row.addWidget(browse)
        vault_row.addWidget(self.scan_btn)

        header = QVBoxLayout()
        title = QLabel("Obsidian Phantom")
        title.setObjectName("title")
        subtitle = QLabel("Broken links, orphans, and junk files — without opening Obsidian.")
        subtitle.setObjectName("subtitle")
        header.addWidget(title)
        header.addWidget(subtitle)
        header.addSpacing(8)
        header.addLayout(vault_row)
        header.addWidget(self.banner)

        self.nav = QListWidget()
        self.nav.setFixedWidth(180)
        self.nav.setMouseTracking(True)
        self.nav.viewport().setMouseTracking(True)
        self.nav.setAttribute(Qt.WidgetAttribute.WA_AlwaysShowToolTips, True)
        self.stack = QStackedWidget()
        self.tables: dict[str, QTableWidget] = {}
        pages = [
            ("broken", ["Target", "Found in", "Kind"]),
            ("orphans", ["Path"]),
            ("junk", ["Path"]),
            ("empty_files", ["Path"]),
            ("empty_folders", ["Path"]),
        ]
        for key, headers in pages:
            table = self._make_table(headers)
            self.tables[key] = table
            self.stack.addWidget(table)
        self._reset_nav(ScanResult(vault="", files=[]))
        self.nav.currentRowChanged.connect(self.stack.setCurrentIndex)
        self.nav.itemEntered.connect(self._on_nav_hover)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.addWidget(self.nav)
        splitter.addWidget(self.stack)
        splitter.setStretchFactor(1, 1)

        export_btn = QPushButton("Export report")
        export_btn.clicked.connect(self.export_report)
        self.trash_btn = QPushButton("Move junk to .trash")
        self.trash_btn.setObjectName("danger")
        self.trash_btn.clicked.connect(self.trash_junk)
        self.trash_btn.setEnabled(False)
        open_btn = QPushButton("Open selected")
        open_btn.clicked.connect(self.open_selected)

        actions = QHBoxLayout()
        actions.addWidget(export_btn)
        actions.addWidget(self.trash_btn)
        actions.addWidget(open_btn)
        actions.addStretch()

        root = QWidget()
        layout = QVBoxLayout(root)
        layout.setContentsMargins(16, 12, 16, 12)
        layout.setSpacing(12)
        layout.addLayout(header)
        layout.addWidget(splitter, 1)
        layout.addLayout(actions)
        self.setCentralWidget(root)

        status = QStatusBar()
        self.setStatusBar(status)
        status.showMessage("Choose a vault and press Scan.")

        toolbar = QToolBar()
        toolbar.setMovable(False)
        self.addToolBar(toolbar)
        settings_action = QAction("Ignore rules", self)
        settings_action.setShortcut(QKeySequence("Ctrl+,"))
        settings_action.triggered.connect(self.edit_settings)
        scan_action = QAction("Scan", self)
        scan_action.setShortcut(QKeySequence("Ctrl+R"))
        scan_action.triggered.connect(self.start_scan)
        toolbar.addAction(settings_action)
        toolbar.addAction(scan_action)

        self.vault_input.textChanged.connect(self._update_banner)
        self._update_banner()

        geometry = self.settings_store.value("geometry")
        if geometry is not None:
            self.restoreGeometry(geometry)

    def _make_table(self, headers: list[str]) -> QTableWidget:
        table = QTableWidget(0, len(headers))
        table.setHorizontalHeaderLabels(headers)
        table.setAlternatingRowColors(True)
        table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        table.setSelectionMode(QTableWidget.SelectionMode.ExtendedSelection)
        table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        table.horizontalHeader().setStretchLastSection(True)
        table.verticalHeader().setVisible(False)
        table.doubleClicked.connect(self.open_selected)
        return table

    def closeEvent(self, event) -> None:  # noqa: N802 — Qt API
        self.settings_store.setValue("geometry", self.saveGeometry())
        self.settings_store.setValue("last_vault", self.vault_input.text().strip())
        super().closeEvent(event)

    def _update_banner(self) -> None:
        path = self.vault_input.text().strip()
        self.banner.setVisible(bool(path) and os.path.isdir(path) and not looks_like_vault(path))

    def browse_vault(self) -> None:
        start = self.vault_input.text().strip() or os.path.expanduser("~")
        chosen = QFileDialog.getExistingDirectory(self, "Select Obsidian vault", start)
        if chosen:
            self.vault_input.setText(chosen)

    def edit_settings(self) -> None:
        dialog = SettingsDialog(self.scan_settings, self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self.scan_settings = dialog.settings()

    def start_scan(self) -> None:
        vault = self.vault_input.text().strip()
        if not vault or not os.path.isdir(vault):
            QMessageBox.warning(self, "No vault", "Choose an existing vault folder first.")
            return
        if self.worker and self.worker.isRunning():
            return
        self.scan_btn.setEnabled(False)
        self.statusBar().showMessage("Scanning…")
        self.worker = ScanWorker(vault, self.scan_settings)
        self.worker.finished_ok.connect(self._on_scan_done)
        self.worker.failed.connect(self._on_scan_failed)
        self.worker.start()

    def _on_scan_failed(self, message: str) -> None:
        self.scan_btn.setEnabled(True)
        QMessageBox.critical(self, "Scan failed", message)
        self.statusBar().showMessage("Scan failed.")

    def _on_scan_done(self, result: ScanResult) -> None:
        self.scan_btn.setEnabled(True)
        self.result = result
        self.settings_store.setValue("last_vault", result.vault)
        self._reset_nav(result)
        self._fill_broken(result)
        self._fill_paths(self.tables["orphans"], result.orphans)
        self._fill_paths(self.tables["junk"], result.junk)
        self._fill_paths(self.tables["empty_files"], result.empty_files)
        self._fill_paths(self.tables["empty_folders"], result.empty_folders)
        self.trash_btn.setEnabled(bool(result.junk))
        counts = result.summary
        self.statusBar().showMessage(
            f"{counts['files']} files · {counts['broken']} broken · "
            f"{counts['orphans']} orphans · {counts['junk']} junk · "
            f"scanned {datetime.now().strftime('%H:%M:%S')}"
        )

    def _reset_nav(self, result: ScanResult) -> None:
        current = self.nav.currentRow()
        self.nav.blockSignals(True)
        self.nav.clear()
        labels = [
            ("Broken links", len({link.target for link in result.broken})),
            ("Orphans", len(result.orphans)),
            ("Junk files", len(result.junk)),
            ("Empty files", len(result.empty_files)),
            ("Empty folders", len(result.empty_folders)),
        ]
        for label, count in labels:
            self.nav.addItem(_nav_item(label, count))
        self.nav.blockSignals(False)
        self.nav.setCurrentRow(current if current >= 0 else 0)

    def _on_nav_hover(self, item: QListWidgetItem) -> None:
        tip = item.toolTip() if item else ""
        if tip:
            QToolTip.showText(QCursor.pos(), tip, self.nav)
        else:
            QToolTip.hideText()

    def _fill_broken(self, result: ScanResult) -> None:
        table = self.tables["broken"]
        rows = grouped_broken(result.broken)
        table.setRowCount(len(rows))
        for i, (target, sources, kinds) in enumerate(rows):
            table.setItem(i, 0, QTableWidgetItem(target))
            table.setItem(i, 1, QTableWidgetItem(sources))
            table.setItem(i, 2, QTableWidgetItem(kinds))

    def _fill_paths(self, table: QTableWidget, paths: list[str]) -> None:
        table.setRowCount(len(paths))
        for i, path in enumerate(paths):
            table.setItem(i, 0, QTableWidgetItem(path))

    def _current_paths(self) -> list[str]:
        table = self.tables[list(self.tables)[self.stack.currentIndex()]]
        rows = {index.row() for index in table.selectedIndexes()}
        if not rows:
            return []
        if table.columnCount() == 1:
            return [table.item(row, 0).text() for row in sorted(rows) if table.item(row, 0)]
        # Broken-link view: open the first source file if possible.
        paths = []
        for row in sorted(rows):
            item = table.item(row, 1)
            if not item:
                continue
            first = item.text().split(",")[0].strip()
            if first:
                paths.append(first)
        return paths

    def open_selected(self) -> None:
        if not self.result:
            return
        for rel in self._current_paths():
            path = os.path.join(self.result.vault, rel)
            if os.path.exists(path):
                QDesktopServices.openUrl(QUrl.fromLocalFile(path))

    def export_report(self) -> None:
        if not self.result:
            QMessageBox.information(self, "Nothing to export", "Scan a vault first.")
            return
        suggested = os.path.join(os.path.expanduser("~"), "phantom-report.md")
        path, _ = QFileDialog.getSaveFileName(self, "Export markdown report", suggested, "Markdown (*.md)")
        if not path:
            return
        write_report(path, self.result)
        self.statusBar().showMessage(f"Wrote {path}")

    def trash_junk(self) -> None:
        if not self.result or not self.result.junk:
            return
        preview = "\n".join(self.result.junk[:20])
        extra = "" if len(self.result.junk) <= 20 else f"\n… and {len(self.result.junk) - 20} more"
        confirm = QMessageBox.question(
            self,
            "Move junk to .trash",
            f"Move {len(self.result.junk)} junk file(s) into:\n"
            f"{os.path.join(self.result.vault, '.trash')}\n\n{preview}{extra}",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if confirm != QMessageBox.StandardButton.Yes:
            return
        trash_paths(self.result.vault, self.result.junk, apply=True)
        self.statusBar().showMessage(f"Moved {len(self.result.junk)} junk files to .trash")
        self.start_scan()


def run_gui(vault: str | None = None) -> int:
    app = QApplication.instance() or QApplication([])
    app.setApplicationName("Obsidian Phantom")
    app.setOrganizationName(ORG)
    app.setStyleSheet(STYLESHEET)
    window = MainWindow(vault)
    window.show()
    screen = QGuiApplication.primaryScreen()
    if screen:
        geo = screen.availableGeometry()
        window.move(
            geo.center().x() - window.width() // 2,
            geo.center().y() - window.height() // 2,
        )
    return app.exec()
