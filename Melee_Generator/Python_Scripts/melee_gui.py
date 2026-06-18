#!/usr/bin/env python3
"""PySide6 GUI for the Melee_Generator toolset.

Launched via ``Launch_Melee_GUI.vbs``. This replaced the original Tkinter GUI,
mirroring the design of the Rivals_2_Generator Qt GUI.

The main game-specific difference from Rivals: costume alts are numbered 1-8
(e.g. ``Fox (5).png``) rather than named skins, and the character database is a
two-column ``alias -> filename`` mapping.

Fetch/generate work runs the sibling scripts via ``QProcess``; the player/
character CSV databases and the settings / custom-events JSON files are read and
written directly.
"""
from __future__ import annotations

import functools
import http.server
import json
import os
import re
import shutil
import socket
import socketserver
import subprocess
import sys
import threading
import webbrowser
import datetime as _dt
from pathlib import Path

from PySide6 import QtCore, QtGui, QtWidgets
from PySide6.QtCore import Qt, QProcess, Signal

# --------------------------------------------------------------------------- #
#  Paths & constants                                                          #
# --------------------------------------------------------------------------- #
ROOT = Path(__file__).parent.parent
REPO_ROOT = ROOT.parent            # git repo root (contains all generators)
GENERATOR_DIR = ROOT.name          # this generator's folder name (update pathspec)
PYTHON = sys.executable
THUMBNAIL_SCRIPT = ROOT / "Python_Scripts" / "generate_melee_thumbnails.py"
RENDERS_DIR = ROOT / "Resources" / "Character_Renders" / "Melee_Full_Renders"
FULL_RENDERS_DIR = ROOT / "Resources" / "Character_Renders" / "Melee_Full_Renders"
PLAYER_DB_PATH = ROOT / "Resources" / "Player_database.csv"
CHAR_DB_PATH = ROOT / "Resources" / "Character_database.csv"
SETTINGS_PATH = ROOT / "melee_gui_settings.json"
CUSTOM_EVENTS_PATH = ROOT / "melee_custom_events.json"
EVENT_CONFIGS_PATH = ROOT / "melee_event_configs.json"

# Dark palette
_BG = "#1c1c1c"
_BG2 = "#2b2b2b"
_BG3 = "#3b3b3b"
_FG = "#ffffff"
_MUTED = "#999999"
_SEL = "#0078d4"
_HILITE = "#2d8cff"  # brighter blue for hover/selection highlights

# Syntax highlighting palette (VS Code "Dark+" inspired)
_SYN_COMMENT = "#6a9955"
_SYN_KEY = "#9cdcfe"
_SYN_STRING = "#ce9178"
_SYN_TAG = "#569cd6"
_SYN_NUMBER = "#b5cea8"

# Events that support start.gg fetching
FETCH_EVENTS = [
    {
        "label": "CR Clash",
        "slug_template": "tournament/cr-clash-{n}/event/melee-singles",
        "name_template": "CR Clash {n}",
        "default_abbrev": "CRC",
        "default_num": "77",
        "default_link": "",
        "top8_file": "CR Clash Top 8 HTML.txt",
        "tweet_link": "",
    },
    {
        "label": "Immortal Fight Night",
        "slug_template": "tournament/immortal-fight-night-{n}/event/melee-singles",
        "name_template": "Immortal Fight Night {n}",
        "default_abbrev": "IFN",
        "default_num": "145",
        "default_link": "",
        "top8_file": "Immortal Fight Night Top 8 HTML.txt",
        "tweet_link": "",
    },
    {
        "label": "Clip It",
        "slug_template": "tournament/clip-it-{n}/event/melee-singles",
        "name_template": "Clip It {n}",
        "default_num": "3",
        "default_link": "",
        "top8_file": "Clip It Top 8 HTML.txt",
        "tweet_link": "",
    },
    {
        "label": "CR Arcadian",
        "slug_template": "tournament/cr-arcadian/event/melee-singles",
        "name_template": "CR Arcadian",
        "default_abbrev": "CRA",
        "default_num": "",
        "default_link": "",
        "top8_file": "CR Arcadian Top 8 HTML.txt",
        "tweet_link": "",
    },
]

_OUTPUT_FOLDERS = ["Vod_Names", "Youtube_Thumbnails", "Top_8_Texts", "Results_Posts"]

# VOD match-line length budget. Lines longer than this get the series abbreviation
# swapped in for the full tournament name (see fetch_sets.py --abbrev).
MAX_LINE_LEN = 100

try:
    import populate_melee_globals as _pg
except ImportError:
    _pg = None


# --------------------------------------------------------------------------- #
#  Pure helpers (database parsing, render lookups, dispatcher reflection)      #
# --------------------------------------------------------------------------- #
def _ordinal_date(date) -> str:
    if not isinstance(date, _dt.date):
        return ""
    day = date.day
    suffix = "th" if 11 <= day <= 13 else {1: "st", 2: "nd", 3: "rd"}.get(day % 10, "th")
    return date.strftime(f"%B {day}{suffix}")


def _base_event_props(series: str) -> dict:
    """Default property dict for a series, via the populate_melee_globals
    dispatcher. Used to pre-fill the Thumbnail Config form. Longer prefixes are
    checked first so e.g. 'AWG Just Tech It' wins over 'AWG'."""
    if _pg is None:
        return {}
    try:
        if series.startswith('Quarantainment'):
            return _pg.setGlobalsQuarantainment(series)
        elif series.startswith('Students x Treehouse'):
            return _pg.setGlobalsSxT(series)
        elif series.startswith('Fro Fridays'):
            return _pg.setGlobalsFro(series)
        elif series.startswith('AWG Just Tech It'):
            return _pg.setGlobalsJustTechIt(series)
        elif series.startswith('Immortal Fight Night') or series.startswith('NYS HS Esports Showcase'):
            return _pg.setGlobalsIFN(series)
        elif series.startswith('Clip It'):
            return _pg.setGlobalsClipIt(series)
        elif series.startswith('CR Clash'):
            return _pg.setGlobalsCRClash(series)
        elif series.startswith('CR Arcadian'):
            return _pg.setGlobalsCRArcadian(series)
        elif series.startswith('AWG'):
            return _pg.setGlobalsAWG(series)
        elif series.startswith('C2C Finale'):
            return _pg.setGlobalsC2C(series)
        elif series.startswith('Catman'):
            return _pg.setGlobalsCatman(series)
        elif series.startswith('IzAw Sub') or series.startswith('Big Forhead Plays'):
            return _pg.setGlobalsIzAw(series)
        else:
            return _pg.set_default_properties(series)
    except Exception:
        return {}
def get_characters_from_renders() -> list[str]:
    """Derive character names from the renders folder by stripping the ' (N)' suffix."""
    if not RENDERS_DIR.exists():
        return []
    names: set[str] = set()
    for f in RENDERS_DIR.glob("*.png"):
        names.add(re.sub(r"\s*\(\d+\)$", "", f.stem))
    return sorted(names)


def get_alts_for_char(char_name: str) -> list[str]:
    """Available costume numbers for a character, read from the renders folder.

    Falls back to 1-8 when the character has no render files yet so the user can
    still assign a costume number."""
    if not char_name:
        return []
    alts: list[int] = []
    if RENDERS_DIR.exists():
        for f in RENDERS_DIR.glob(f"{char_name} (*).png"):
            m = re.search(r"\((\d+)\)$", f.stem)
            if m:
                alts.append(int(m.group(1)))
    if not alts:
        return [str(i) for i in range(1, 9)]
    return [str(n) for n in sorted(set(alts))]


def load_player_db() -> tuple[list[str], dict[str, list[tuple[str, str]]]]:
    header_comments: list[str] = []
    players: dict[str, list[tuple[str, str]]] = {}
    try:
        lines = PLAYER_DB_PATH.read_text(encoding="utf-8").splitlines()
    except FileNotFoundError:
        return [], {}
    in_players = False
    for line in lines:
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            if not in_players:
                header_comments.append(line)
            continue
        in_players = True
        parts = stripped.split(",")
        result: list[str] = []
        for p in parts:
            p = p.strip()
            if p.startswith("#"):
                break
            result.append(p)
        while result and not result[-1]:
            result.pop()
        if not result:
            continue
        name = result[0]
        chars: list[tuple[str, str]] = []
        for i in range(1, len(result) - 1, 2):
            char = result[i]
            alt = result[i + 1] if i + 1 < len(result) else ""
            if char:
                chars.append((char, alt))
        players[name] = chars
    return header_comments, players


def save_player_db(header_comments: list[str], players: dict[str, list[tuple[str, str]]]) -> None:
    lines = list(header_comments)
    for name, chars in players.items():
        parts = [name]
        for char, alt in chars:
            parts += [char, alt]
        lines.append(",".join(parts))
    PLAYER_DB_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")


def load_char_db() -> tuple[list[str], list[tuple[str, str]]]:
    """Two-column character DB: returns (header_lines, [(alias, filename), ...])."""
    headers: list[str] = []
    entries: list[tuple[str, str]] = []
    try:
        lines = CHAR_DB_PATH.read_text(encoding="utf-8").splitlines()
    except FileNotFoundError:
        return [], []
    for line in lines:
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            headers.append(line)
        else:
            parts = [p.strip() for p in stripped.split(",", 1)]
            if len(parts) == 2:
                entries.append((parts[0], parts[1]))
    return headers, entries


def save_char_db(headers: list[str], entries: list[tuple[str, str]]) -> None:
    lines = list(headers)
    for alias, filename in entries:
        lines.append(f"{alias},{filename}")
    CHAR_DB_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")


def load_thumbnail_events() -> list[tuple[str, str]]:
    """Parse startswith() calls from the dispatcher in generate_melee_thumbnails.py."""
    try:
        source = THUMBNAIL_SCRIPT.read_text(encoding="utf-8")
        names = re.findall(r"weekly_event\.startswith\('([^']+)'\)", source)
        return [(name, f"{name} {{n}}") for name in names]
    except Exception:
        return []


# --------------------------------------------------------------------------- #
#  Dark stylesheet                                                             #
# --------------------------------------------------------------------------- #
def _make_check_icon() -> str:
    """Render a white checkmark PNG to a temp file for the checked-checkbox
    indicator and return a QSS-safe (forward-slash) path."""
    import tempfile
    path = Path(tempfile.gettempdir()) / "melee_qt_check.png"
    img = QtGui.QImage(16, 16, QtGui.QImage.Format.Format_ARGB32)
    img.fill(Qt.GlobalColor.transparent)
    p = QtGui.QPainter(img)
    p.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing, True)
    pen = QtGui.QPen(QtGui.QColor("#ffffff"), 2.2)
    pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
    p.setPen(pen)
    p.drawPolyline([QtCore.QPointF(3.5, 8.5), QtCore.QPointF(6.5, 11.5),
                    QtCore.QPointF(12.5, 4.5)])
    p.end()
    try:
        img.save(str(path), "PNG")
    except Exception:
        return ""
    return path.as_posix()


_CHECK_URL = _make_check_icon()

STYLESHEET = f"""
* {{ outline: 0; }}
QWidget {{
    background-color: {_BG2};
    color: {_FG};
    font-family: "Segoe UI";
    font-size: 10pt;
}}
QMainWindow, QScrollArea, QScrollArea > QWidget > QWidget {{ background-color: {_BG}; }}
QScrollArea {{ border: 0; }}
QLabel {{ background: transparent; }}
QLabel#muted {{ color: {_MUTED}; }}
QLabel#warning {{ color: #E08000; }}
QLabel#heading {{ font-weight: 600; font-size: 11pt; }}

QGroupBox {{
    border: 1px solid {_BG3};
    border-radius: 6px;
    margin-top: 10px;
    padding: 8px 8px 8px 8px;
    background-color: {_BG2};
}}
QGroupBox::title {{
    subcontrol-origin: margin;
    left: 10px;
    padding: 0 4px;
    color: {_MUTED};
}}

QLineEdit, QPlainTextEdit, QTextEdit, QSpinBox, QDateEdit {{
    background-color: {_BG3};
    border: 1px solid #4a4a4a;
    border-radius: 4px;
    padding: 3px 5px;
    selection-background-color: {_SEL};
}}
QLineEdit:focus, QPlainTextEdit:focus, QDateEdit:focus {{ border: 1px solid {_SEL}; }}
QPlainTextEdit, QTextEdit {{ font-family: "Consolas"; font-size: 10pt; }}

QComboBox {{
    background-color: {_BG3};
    border: 1px solid #4a4a4a;
    border-radius: 4px;
    padding: 3px 5px;
}}
QComboBox:focus {{ border: 1px solid {_SEL}; }}
QComboBox QAbstractItemView {{
    background-color: {_BG3};
    border: 1px solid #4a4a4a;
    outline: 0;
    selection-background-color: {_HILITE};
    selection-color: #ffffff;
}}

QPushButton {{
    background-color: {_BG3};
    border: 1px solid #4a4a4a;
    border-radius: 4px;
    padding: 5px 12px;
}}
QPushButton:hover {{ background-color: #474747; }}
QPushButton:pressed {{ background-color: #525252; }}
QPushButton:disabled {{ color: {_MUTED}; background-color: #303030; }}
QPushButton#accent {{
    background-color: {_SEL};
    border: 1px solid {_SEL};
    font-weight: 600;
}}
QPushButton#accent:hover {{ background-color: #1a86dd; }}
QPushButton#tool {{
    padding: 0;
    min-width: 30px;
    max-width: 30px;
    min-height: 30px;
    max-height: 30px;
    border-radius: 6px;
    font-size: 16px;
    color: {_MUTED};
}}
QPushButton#tool:hover {{
    color: {_FG};
    background-color: #474747;
    border-color: {_HILITE};
}}
QPushButton#tool:pressed {{ background-color: #525252; }}

QTabWidget::pane {{ border: 0; background-color: {_BG}; }}
QTabBar::tab {{
    background-color: {_BG2};
    color: {_MUTED};
    padding: 8px 16px;
    border: 0;
}}
QTabBar::tab:selected {{ color: {_FG}; border-bottom: 2px solid {_SEL}; }}
QTabBar::tab:hover {{ color: {_FG}; }}

QListWidget, QTreeWidget, QTableView, QListView {{
    background-color: {_BG3};
    border: 1px solid #4a4a4a;
    border-radius: 4px;
    selection-background-color: {_SEL};
    selection-color: {_FG};
}}
QHeaderView::section {{
    background-color: {_BG2};
    color: {_MUTED};
    border: 0;
    border-bottom: 1px solid #4a4a4a;
    padding: 4px;
}}
QTableView {{ gridline-color: #353535; }}

QCheckBox {{ background: transparent; spacing: 7px; }}
QCheckBox::indicator {{
    width: 16px;
    height: 16px;
    border: 1px solid #7a7a7a;
    border-radius: 3px;
    background-color: {_BG3};
}}
QCheckBox::indicator:hover {{ border-color: {_HILITE}; }}
QCheckBox::indicator:checked {{
    background-color: {_HILITE};
    border-color: {_HILITE};
    image: url({_CHECK_URL});
}}
QCheckBox::indicator:disabled {{ border-color: #4a4a4a; background-color: #303030; }}
QScrollBar:vertical {{ background: {_BG}; width: 12px; margin: 0; }}
QScrollBar::handle:vertical {{ background: #4a4a4a; border-radius: 6px; min-height: 24px; }}
QScrollBar::handle:vertical:hover {{ background: #5a5a5a; }}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
QScrollBar:horizontal {{ background: {_BG}; height: 12px; margin: 0; }}
QScrollBar::handle:horizontal {{ background: #4a4a4a; border-radius: 6px; min-width: 24px; }}
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{ width: 0; }}

QSplitter::handle {{ background: {_BG2}; }}
QToolButton {{ background: transparent; border: 0; padding: 2px; }}
QToolButton:hover {{ color: {_SEL}; }}
"""


# --------------------------------------------------------------------------- #
#  Reusable widgets                                                            #
# --------------------------------------------------------------------------- #
class CollapsibleBox(QtWidgets.QWidget):
    """A header button that shows/hides a content area below it."""

    def __init__(self, title: str, collapsed: bool = False, parent=None):
        super().__init__(parent)
        self._toggle = QtWidgets.QToolButton(self)
        self._toggle.setText(title)
        self._toggle.setCheckable(True)
        self._toggle.setChecked(not collapsed)
        self._toggle.setStyleSheet("QToolButton { font-weight: 600; color: %s; }" % _MUTED)
        self._toggle.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        self._toggle.setArrowType(Qt.ArrowType.DownArrow if not collapsed else Qt.ArrowType.RightArrow)
        self._toggle.clicked.connect(self._on_toggle)

        self.content = QtWidgets.QWidget(self)
        self.content_layout = QtWidgets.QVBoxLayout(self.content)
        self.content_layout.setContentsMargins(4, 6, 0, 6)
        self.content.setVisible(not collapsed)

        lay = QtWidgets.QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(2)
        lay.addWidget(self._toggle)
        lay.addWidget(self.content)

    def _on_toggle(self, checked: bool):
        self.content.setVisible(checked)
        self._toggle.setArrowType(Qt.ArrowType.DownArrow if checked else Qt.ArrowType.RightArrow)

    def addWidget(self, w):
        self.content_layout.addWidget(w)

    def addLayout(self, lay):
        self.content_layout.addLayout(lay)


class ColorField(QtWidgets.QWidget):
    """A hex line edit + colour swatch button that stay in sync."""

    def __init__(self, default: str = "#FFFFFF", width: int = 90, parent=None):
        super().__init__(parent)
        lay = QtWidgets.QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(3)
        self.edit = QtWidgets.QLineEdit(default)
        self.edit.setFixedWidth(width)
        self.swatch = QtWidgets.QPushButton()
        self.swatch.setFixedWidth(24)
        self.swatch.setCursor(Qt.CursorShape.PointingHandCursor)
        lay.addWidget(self.edit)
        lay.addWidget(self.swatch)
        self.edit.textChanged.connect(self._sync)
        self.swatch.clicked.connect(self._pick)
        self._sync()

    def _sync(self):
        c = self.edit.text().strip()
        if QtGui.QColor(c).isValid():
            self.swatch.setStyleSheet(f"background-color: {c}; border: 1px solid #4a4a4a;")

    def _pick(self):
        cur = QtGui.QColor(self.edit.text().strip() or "#FFFFFF")
        col = QtWidgets.QColorDialog.getColor(cur, self, "Pick color")
        if col.isValid():
            self.edit.setText(col.name())

    def value(self) -> str:
        return self.edit.text().strip()

    def setValue(self, v: str):
        self.edit.setText(v)


def _hline(text: str = "", w: int = 70) -> QtWidgets.QLineEdit:
    e = QtWidgets.QLineEdit(text)
    e.setFixedWidth(w)
    return e


def _muted(text: str) -> QtWidgets.QLabel:
    lbl = QtWidgets.QLabel(text)
    lbl.setObjectName("muted")
    lbl.setWordWrap(True)
    return lbl


# --------------------------------------------------------------------------- #
#  VOD list model (virtualized — handles large match lists smoothly)          #
# --------------------------------------------------------------------------- #
class VodModel(QtCore.QAbstractTableModel):
    HEADERS = ["", "", "Match line", "Len"]

    def __init__(self):
        super().__init__()
        self._rows: list[dict] = []  # {"checked": bool, "text": str}

    def rowCount(self, parent=QtCore.QModelIndex()):
        return 0 if parent.isValid() else len(self._rows)

    def columnCount(self, parent=QtCore.QModelIndex()):
        return 4

    def data(self, index, role=Qt.ItemDataRole.DisplayRole):
        if not index.isValid():
            return None
        row = self._rows[index.row()]
        col = index.column()
        if col == 2 and role in (Qt.ItemDataRole.DisplayRole, Qt.ItemDataRole.EditRole):
            return row["text"]
        if col == 3:
            length = len(row["text"].strip())
            if role == Qt.ItemDataRole.DisplayRole:
                return f"{length}/{MAX_LINE_LEN}"
            if role == Qt.ItemDataRole.TextAlignmentRole:
                return int(Qt.AlignmentFlag.AlignCenter)
            if role == Qt.ItemDataRole.ForegroundRole and length > MAX_LINE_LEN:
                return QtGui.QColor("#ff6b6b")
            if role == Qt.ItemDataRole.ToolTipRole:
                return ("Over the 100-character limit — set an Abbreviation for this "
                        "series in the Fetch tab and re-fetch" if length > MAX_LINE_LEN
                        else "Match-line length")
        if col == 1 and role == Qt.ItemDataRole.ToolTipRole:
            return "Copy line"
        if col == 0 and role == Qt.ItemDataRole.CheckStateRole:
            return Qt.CheckState.Checked if row["checked"] else Qt.CheckState.Unchecked
        if role == Qt.ItemDataRole.BackgroundRole and row["checked"]:
            return QtGui.QColor("#1e3a5f")
        return None

    def setData(self, index, value, role=Qt.ItemDataRole.EditRole):
        if not index.isValid():
            return False
        row = self._rows[index.row()]
        if index.column() == 2 and role == Qt.ItemDataRole.EditRole:
            row["text"] = value
            # Refresh both the edited cell and the length column beside it
            self.dataChanged.emit(index, self.index(index.row(), 3))
            return True
        if index.column() == 0 and role == Qt.ItemDataRole.CheckStateRole:
            row["checked"] = (Qt.CheckState(value) == Qt.CheckState.Checked)
            left = self.index(index.row(), 0)
            right = self.index(index.row(), 3)
            self.dataChanged.emit(left, right)
            return True
        return False

    def flags(self, index):
        if not index.isValid():
            return Qt.ItemFlag.NoItemFlags
        f = Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable
        if index.column() == 0:
            f |= Qt.ItemFlag.ItemIsUserCheckable
        elif index.column() == 2:
            f |= Qt.ItemFlag.ItemIsEditable
        return f

    def headerData(self, section, orientation, role=Qt.ItemDataRole.DisplayRole):
        if orientation == Qt.Orientation.Horizontal and role == Qt.ItemDataRole.DisplayRole:
            return self.HEADERS[section]
        return None

    def load(self, lines: list[str]):
        self.beginResetModel()
        self._rows = [{"checked": False, "text": ln} for ln in lines]
        self.endResetModel()

    def add_blank(self) -> int:
        pos = len(self._rows)
        self.beginInsertRows(QtCore.QModelIndex(), pos, pos)
        self._rows.append({"checked": False, "text": ""})
        self.endInsertRows()
        return pos

    def set_all(self, checked: bool):
        if not self._rows:
            return
        for r in self._rows:
            r["checked"] = checked
        self.dataChanged.emit(self.index(0, 0),
                              self.index(len(self._rows) - 1, 3))

    def delete_marked(self) -> int:
        keep = [r for r in self._rows if not r["checked"]]
        removed = len(self._rows) - len(keep)
        if removed:
            self.beginResetModel()
            self._rows = keep
            self.endResetModel()
        return removed

    def delete_row(self, r: int):
        if 0 <= r < len(self._rows):
            self.beginRemoveRows(QtCore.QModelIndex(), r, r)
            self._rows.pop(r)
            self.endRemoveRows()

    def any_checked(self) -> bool:
        return any(r["checked"] for r in self._rows)

    def text_at(self, r: int) -> str:
        return self._rows[r]["text"] if 0 <= r < len(self._rows) else ""

    def to_text(self) -> str:
        return "\n".join(r["text"] for r in self._rows)


# --------------------------------------------------------------------------- #
#  Syntax highlighters                                                         #
# --------------------------------------------------------------------------- #
def _fmt(color: str) -> QtGui.QTextCharFormat:
    f = QtGui.QTextCharFormat()
    f.setForeground(QtGui.QColor(color))
    return f


class Top8DataHighlighter(QtGui.QSyntaxHighlighter):
    KEY = _fmt(_SYN_KEY)
    NUMBER = _fmt(_SYN_NUMBER)
    COMMENT = _fmt(_SYN_COMMENT)

    def highlightBlock(self, text: str):
        if re.match(r"^[ \t]*#", text):
            self.setFormat(0, len(text), self.COMMENT)
            return
        m = re.match(r"^[^#\n][^:\t\n]*:", text)
        if m:
            self.setFormat(m.start(), m.end() - m.start(), self.KEY)
        m = re.match(r"^\d+", text)
        if m:
            self.setFormat(0, m.end(), self.NUMBER)


class HtmlHighlighter(QtGui.QSyntaxHighlighter):
    TAG = _fmt(_SYN_TAG)
    ATTR = _fmt(_SYN_KEY)
    STRING = _fmt(_SYN_STRING)
    COMMENT = _fmt(_SYN_COMMENT)

    IN_COMMENT = 1

    def highlightBlock(self, text: str):
        for m in re.finditer(r"</?[a-zA-Z][\w:-]*", text):
            self.setFormat(m.start(), m.end() - m.start(), self.TAG)
        for m in re.finditer(r"[a-zA-Z_:][\w:-]*(?==)", text):
            self.setFormat(m.start(), m.end() - m.start(), self.ATTR)
        for m in re.finditer(r"\"[^\"]*\"|'[^']*'", text):
            self.setFormat(m.start(), m.end() - m.start(), self.STRING)

        self.setCurrentBlockState(0)
        start = 0
        if self.previousBlockState() != self.IN_COMMENT:
            m = re.search(r"<!--", text)
            start = m.start() if m else -1
        while start >= 0:
            end = text.find("-->", start)
            if end == -1:
                self.setCurrentBlockState(self.IN_COMMENT)
                length = len(text) - start
            else:
                length = end - start + 3
            self.setFormat(start, length, self.COMMENT)
            nxt = text.find("<!--", start + length)
            start = nxt


# --------------------------------------------------------------------------- #
#  Combo-box popup delegate                                                    #
# --------------------------------------------------------------------------- #
class ComboItemDelegate(QtWidgets.QStyledItemDelegate):
    """Paints dropdown rows ourselves so the hovered/selected item is clearly
    highlighted (the app-wide stylesheet can't reliably reach combo popups under
    the Fusion style)."""

    def paint(self, painter, option, index):
        opt = QtWidgets.QStyleOptionViewItem(option)
        self.initStyleOption(opt, index)
        state = opt.state
        active = bool(state & QtWidgets.QStyle.StateFlag.State_Selected) or \
            bool(state & QtWidgets.QStyle.StateFlag.State_MouseOver)
        bg = QtGui.QColor(_HILITE) if active else QtGui.QColor(_BG3)
        fg = QtGui.QColor("#ffffff") if active else QtGui.QColor(_FG)
        painter.save()
        painter.fillRect(opt.rect, bg)
        painter.setPen(fg)
        text = index.data(Qt.ItemDataRole.DisplayRole)
        painter.drawText(opt.rect.adjusted(8, 0, -8, 0),
                         Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft,
                         "" if text is None else str(text))
        painter.restore()

    def sizeHint(self, option, index):
        s = super().sizeHint(option, index)
        s.setHeight(max(s.height(), 26))
        return s


# --------------------------------------------------------------------------- #
#  Copy-line button delegate (VOD table)                                       #
# --------------------------------------------------------------------------- #
class CopyButtonDelegate(QtWidgets.QStyledItemDelegate):
    """Paints a small clickable "copy" icon per row instead of using a real
    per-row widget, so the virtualized VOD table stays cheap. Emits
    ``copyRequested(row)`` on left-click."""

    copyRequested = QtCore.Signal(int)

    def paint(self, painter, option, index):
        painter.save()
        bg = index.data(Qt.ItemDataRole.BackgroundRole)
        base = QtGui.QColor(bg) if bg is not None else QtGui.QColor(_BG3)
        painter.fillRect(option.rect, base)

        hovered = bool(option.state & QtWidgets.QStyle.StateFlag.State_MouseOver)
        painter.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing, True)

        size = 22
        bx = option.rect.x() + (option.rect.width() - size) // 2
        by = option.rect.y() + (option.rect.height() - size) // 2
        btn = QtCore.QRect(bx, by, size, size)
        if hovered:
            base = QtGui.QColor("#474747")
            painter.setBrush(base)
            painter.setPen(QtGui.QPen(QtGui.QColor(_HILITE), 1))
            painter.drawRoundedRect(btn, 5, 5)

        cx, cy = btn.center().x(), btn.center().y()
        back = QtCore.QRectF(cx - 1.0, cy - 6.0, 7.0, 9.0)
        front = QtCore.QRectF(cx - 4.0, cy - 3.0, 7.0, 9.0)
        ink = QtGui.QColor(_FG if hovered else _MUTED)
        painter.setPen(QtGui.QPen(ink, 1.3))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawRoundedRect(back, 1.6, 1.6)
        path = QtGui.QPainterPath()
        path.addRoundedRect(front, 1.6, 1.6)
        painter.fillPath(path, base)
        painter.drawRoundedRect(front, 1.6, 1.6)
        painter.restore()

    def editorEvent(self, event, model, option, index):
        if (event.type() == QtCore.QEvent.Type.MouseButtonRelease
                and event.button() == Qt.MouseButton.LeftButton
                and option.rect.contains(event.pos())):
            self.copyRequested.emit(index.row())
            return True
        return False


# --------------------------------------------------------------------------- #
#  Main window                                                                 #
# --------------------------------------------------------------------------- #
class MeleeWindow(QtWidgets.QMainWindow):
    log_signal = Signal(str)
    update_status_signal = Signal(str, str)   # (message, level: ok|avail|err|busy)
    update_done_signal = Signal(bool, str)    # (success, new folder-tree sha)

    def __init__(self):
        super().__init__()
        self.setWindowTitle("Melee Generator Powered By Watherum")
        for folder in _OUTPUT_FOLDERS:
            (ROOT / folder).mkdir(exist_ok=True)

        self._procs: set[QProcess] = set()
        self._http_server = None
        self._http_server_port = None
        self._preview_cache: dict[str, QtGui.QPixmap] = {}

        self._load_settings()

        splitter = QtWidgets.QSplitter(Qt.Orientation.Vertical)
        self.setCentralWidget(splitter)

        self.tabs = QtWidgets.QTabWidget()
        splitter.addWidget(self.tabs)

        console_box = QtWidgets.QWidget()
        cbl = QtWidgets.QVBoxLayout(console_box)
        cbl.setContentsMargins(6, 4, 6, 6)
        hdr = QtWidgets.QHBoxLayout()
        hdr.addWidget(_muted("Console Output"))
        hdr.addStretch(1)
        clear_btn = QtWidgets.QPushButton("Clear Console")
        clear_btn.clicked.connect(self._clear_console)
        hdr.addWidget(clear_btn)
        cbl.addLayout(hdr)
        self.console = QtWidgets.QPlainTextEdit()
        self.console.setReadOnly(True)
        self.console.setStyleSheet(f"background-color: {_BG};")
        cbl.addWidget(self.console)
        splitter.addWidget(console_box)
        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 0)
        splitter.setSizes([720, 200])
        self._splitter = splitter

        self.log_signal.connect(self._append_console)
        self.update_status_signal.connect(self._on_update_status)
        self.update_done_signal.connect(self._on_update_done)

        # Build tabs
        self._build_fetch_tab()
        self._build_thumbnails_tab()
        self._build_top8_tab()
        self._build_posts_tab()
        self._build_renders_tab()
        self._build_player_db_tab()
        self._build_char_db_tab()
        self._build_update_tab()

        self._combo_delegate = ComboItemDelegate(self)
        for combo in self.findChildren(QtWidgets.QComboBox):
            combo.view().setItemDelegate(self._combo_delegate)

        self.resize(1280, 900)

    # ------------------------------------------------------------------ #
    #  Settings persistence                                              #
    # ------------------------------------------------------------------ #
    def _load_settings(self):
        try:
            self._settings = json.loads(SETTINGS_PATH.read_text(encoding="utf-8"))
        except Exception:
            self._settings = {}
        try:
            self._custom_events = json.loads(CUSTOM_EVENTS_PATH.read_text(encoding="utf-8"))
        except Exception:
            self._custom_events = []
        try:
            self._event_configs = json.loads(EVENT_CONFIGS_PATH.read_text(encoding="utf-8"))
        except Exception:
            self._event_configs = {}

    def _save_settings(self):
        if getattr(self, "_loading", False):
            return
        series = self._posts_series.currentText() if hasattr(self, "_posts_series") else ""
        posts_cfg = dict(self._settings.get("posts_cfg", {}))
        if series and hasattr(self, "_posts_has_next"):
            posts_cfg[series] = {
                "next_date": self._posts_date.date().toString("yyyy-MM-dd"),
                "next_link": self._posts_next_link.text(),
                "vods": self._posts_vods.text(),
                "has_next": self._posts_has_next.isChecked(),
            }
        data = {
            "last_event_nums": {
                label: w["num"].text() for label, w in self._fetch_widgets.items()
            },
            "abbrevs": {
                label: w["abbrev"].text() for label, w in self._fetch_widgets.items()
                if "abbrev" in w
            },
            "last_thumb_series": self._thumb_series.currentText() if hasattr(self, "_thumb_series") else "",
            "last_posts_series": series,
            "posts_cfg": posts_cfg,
            "last_update_tree": self._settings.get("last_update_tree", ""),
        }
        self._settings = data
        SETTINGS_PATH.write_text(json.dumps(data, indent=2), encoding="utf-8")

    def _save_custom_events(self):
        CUSTOM_EVENTS_PATH.write_text(json.dumps(self._custom_events, indent=2), encoding="utf-8")

    def _save_event_configs(self):
        EVENT_CONFIGS_PATH.write_text(json.dumps(self._event_configs, indent=2), encoding="utf-8")

    # ------------------------------------------------------------------ #
    #  Scroll-area tab helper                                            #
    # ------------------------------------------------------------------ #
    def _scroll_tab(self, title: str) -> QtWidgets.QVBoxLayout:
        scroll = QtWidgets.QScrollArea()
        scroll.setWidgetResizable(True)
        inner = QtWidgets.QWidget()
        lay = QtWidgets.QVBoxLayout(inner)
        lay.setContentsMargins(12, 12, 12, 12)
        lay.setSpacing(10)
        scroll.setWidget(inner)
        self.tabs.addTab(scroll, title)
        return lay

    # ================================================================== #
    #  Tab: Fetch from start.gg                                          #
    # ================================================================== #
    def _build_fetch_tab(self):
        lay = self._scroll_tab("Fetch From Start.gg")
        self._fetch_widgets: dict[str, dict] = {}

        for cfg in FETCH_EVENTS:
            box = QtWidgets.QGroupBox(cfg["label"])
            v = QtWidgets.QVBoxLayout(box)
            saved_num = self._settings.get("last_event_nums", {}).get(cfg["label"], cfg["default_num"])

            row1 = QtWidgets.QHBoxLayout()
            row1.addWidget(QtWidgets.QLabel("Event #:"))
            num = _hline(saved_num, 60)
            row1.addWidget(num)
            row1.addSpacing(12)
            row1.addWidget(QtWidgets.QLabel("Top 8 Link:"))
            link = QtWidgets.QLineEdit(cfg["default_link"].replace("{n}", saved_num))
            link.setMinimumWidth(280)
            row1.addWidget(link)
            row1.addStretch(1)
            v.addLayout(row1)

            rowa = QtWidgets.QHBoxLayout()
            rowa.addWidget(QtWidgets.QLabel("Abbrev:"))
            saved_abbrev = self._settings.get("abbrevs", {}).get(
                cfg["label"], cfg.get("default_abbrev", ""))
            abbrev = _hline(saved_abbrev, 90)
            abbrev.setToolTip("Short tournament name used for VOD lines over "
                              f"{MAX_LINE_LEN} characters (e.g. IFN). The event "
                              "number is appended automatically.")
            rowa.addWidget(abbrev)
            rowa.addWidget(_muted(f"used when a match line exceeds {MAX_LINE_LEN} chars"))
            rowa.addStretch(1)
            v.addLayout(rowa)
            abbrev.textChanged.connect(lambda _t: self._save_settings())

            def _on_num(text, lk=link, tmpl=cfg["default_link"], label=cfg["label"]):
                lk.setText(tmpl.replace("{n}", text.strip()))
                if hasattr(self, "_thumb_series") and self._thumb_series.currentText() == label:
                    self._thumb_num.setText(text.strip())
                if hasattr(self, "_posts_series") and self._posts_series.currentText() == label:
                    self._posts_num.setText(text.strip())
                self._save_settings()
            num.textChanged.connect(_on_num)

            row2 = QtWidgets.QHBoxLayout()
            b1 = QtWidgets.QPushButton("Fetch VOD Names")
            b1.clicked.connect(lambda _=False, c=cfg, n=num, a=abbrev: self._fetch_sets(c, n.text().strip(), a.text().strip()))
            row2.addWidget(b1)
            b2 = QtWidgets.QPushButton("Fetch Top 8")
            b2.clicked.connect(lambda _=False, c=cfg, n=num, lk=link: self._fetch_top8(c, n.text().strip(), lk.text().strip()))
            row2.addWidget(b2)
            row2.addStretch(1)
            v.addLayout(row2)
            lay.addWidget(box)
            self._fetch_widgets[cfg["label"]] = {"num": num, "link": link, "abbrev": abbrev}

        self._saved_custom_box = QtWidgets.QGroupBox("Saved Custom Tournaments")
        self._saved_custom_layout = QtWidgets.QVBoxLayout(self._saved_custom_box)
        lay.addWidget(self._saved_custom_box)
        self._build_saved_custom_rows()

        addbox = QtWidgets.QGroupBox("Add New Custom Tournament")
        form = QtWidgets.QGridLayout(addbox)
        form.addWidget(QtWidgets.QLabel("Slug:"), 0, 0)
        self._custom_slug = QtWidgets.QLineEdit()
        self._custom_slug.setFixedWidth(360)
        form.addWidget(self._custom_slug, 0, 1)
        form.addWidget(_muted("e.g. tournament/{event}-{n}/event/melee-singles"), 0, 2)
        form.addWidget(QtWidgets.QLabel("Name:"), 1, 0)
        self._custom_name = QtWidgets.QLineEdit()
        self._custom_name.setFixedWidth(250)
        form.addWidget(self._custom_name, 1, 1)
        form.addWidget(_muted("e.g. Immortal Fight Night"), 1, 2)
        form.addWidget(QtWidgets.QLabel("Abbrev:"), 2, 0)
        self._custom_abbrev = QtWidgets.QLineEdit()
        self._custom_abbrev.setFixedWidth(120)
        form.addWidget(self._custom_abbrev, 2, 1)
        form.addWidget(_muted(f"optional — used when a match line exceeds {MAX_LINE_LEN} chars"), 2, 2)
        form.addWidget(QtWidgets.QLabel("Event #:"), 3, 0)
        self._custom_num = _hline("", 60)
        form.addWidget(self._custom_num, 3, 1)
        save_fetch = QtWidgets.QPushButton("Save & Fetch VOD Names")
        save_fetch.clicked.connect(self._fetch_custom_sets)
        form.addWidget(save_fetch, 4, 1)
        form.setColumnStretch(3, 1)
        lay.addWidget(addbox)
        lay.addStretch(1)

    def _build_saved_custom_rows(self):
        while self._saved_custom_layout.count():
            item = self._saved_custom_layout.takeAt(0)
            w = item.widget()
            if w:
                w.deleteLater()
        if not self._custom_events:
            self._saved_custom_layout.addWidget(_muted("No saved custom tournaments"))
            return
        for entry in self._custom_events:
            slug_tmpl = entry.get("slug_template", entry.get("slug", ""))
            if not slug_tmpl:
                continue
            box = QtWidgets.QGroupBox(entry.get("label", slug_tmpl))
            v = QtWidgets.QVBoxLayout(box)
            row1 = QtWidgets.QHBoxLayout()
            row1.addWidget(QtWidgets.QLabel("Event #:"))
            num = _hline(entry.get("current_num", ""), 60)
            row1.addWidget(num)
            row1.addSpacing(12)
            row1.addWidget(QtWidgets.QLabel("Top 8 Link:"))
            link = QtWidgets.QLineEdit(entry.get("top8_link", ""))
            link.setMinimumWidth(260)
            row1.addWidget(link)
            row1.addStretch(1)
            v.addLayout(row1)

            def _on_num(text, e=entry):
                e["current_num"] = text
                self._save_custom_events()

            def _on_link(text, e=entry):
                e["top8_link"] = text
                self._save_custom_events()

            rowa = QtWidgets.QHBoxLayout()
            rowa.addWidget(QtWidgets.QLabel("Abbrev:"))
            abbrev = _hline(entry.get("abbrev", ""), 90)
            abbrev.setToolTip("Short tournament name used for VOD lines over "
                              f"{MAX_LINE_LEN} characters. The event number is "
                              "appended automatically.")
            rowa.addWidget(abbrev)
            rowa.addWidget(_muted(f"used when a match line exceeds {MAX_LINE_LEN} chars"))
            rowa.addStretch(1)
            v.addLayout(rowa)

            def _on_abbrev(text, e=entry):
                e["abbrev"] = text
                self._save_custom_events()

            num.textChanged.connect(_on_num)
            link.textChanged.connect(_on_link)
            abbrev.textChanged.connect(_on_abbrev)

            row2 = QtWidgets.QHBoxLayout()
            b1 = QtWidgets.QPushButton("Fetch VOD Names")
            b1.clicked.connect(lambda _=False, e=entry, n=num: self._fetch_saved_custom(e, n.text().strip()))
            row2.addWidget(b1)
            b2 = QtWidgets.QPushButton("Fetch Top 8")
            b2.clicked.connect(lambda _=False, e=entry, n=num, lk=link: self._fetch_saved_custom_top8(e, n.text().strip(), lk.text().strip()))
            row2.addWidget(b2)
            b3 = QtWidgets.QPushButton("Delete")
            b3.clicked.connect(lambda _=False, s=slug_tmpl: self._delete_custom_event(s))
            row2.addWidget(b3)
            row2.addStretch(1)
            v.addLayout(row2)
            self._saved_custom_layout.addWidget(box)

    def _fetch_custom_sets(self):
        slug_tmpl = self._custom_slug.text().strip()
        name_tmpl = self._custom_name.text().strip()
        num = self._custom_num.text().strip()
        if not slug_tmpl:
            self._log("[Error: slug is required]\n")
            return
        label = (name_tmpl or slug_tmpl).replace(" {n}", "").replace("{n}", "").strip()
        abbrev = self._custom_abbrev.text().strip()
        slug = slug_tmpl.replace("{n}", num)
        name = (name_tmpl or slug_tmpl).replace("{n}", num)
        out = str(ROOT / "Vod_Names" / f"{name} Names.txt")
        entry = {
            "label": label, "slug_template": slug_tmpl,
            "name_template": name_tmpl or slug_tmpl,
            "abbrev": abbrev,
            "top8_file": f"{label} Top 8 HTML.txt",
            "current_num": num, "top8_link": "",
        }
        idx = next((i for i, e in enumerate(self._custom_events) if e.get("slug_template") == slug_tmpl), None)
        if idx is not None:
            entry["top8_link"] = self._custom_events[idx].get("top8_link", "")
            self._custom_events[idx] = entry
        else:
            self._custom_events.append(entry)
        self._save_custom_events()
        self._build_saved_custom_rows()
        self._refresh_thumbnail_events()
        cmd = [PYTHON, str(ROOT / "Python_Scripts" / "fetch_sets.py"), slug, "--name", name, "--out", out]
        if abbrev:
            cmd += ["--abbrev", f"{abbrev} {num}".strip()]
        self._run(cmd)

    def _fetch_saved_custom(self, entry: dict, num: str):
        slug = entry["slug_template"].replace("{n}", num)
        name = entry["name_template"].replace("{n}", num)
        out = str(ROOT / "Vod_Names" / f"{name} Names.txt")
        cmd = [PYTHON, str(ROOT / "Python_Scripts" / "fetch_sets.py"), slug, "--name", name, "--out", out]
        abbrev = entry.get("abbrev", "").strip()
        if abbrev:
            cmd += ["--abbrev", f"{abbrev} {num}".strip()]
        self._run(cmd)

    def _fetch_saved_custom_top8(self, entry: dict, num: str, link: str):
        slug = entry["slug_template"].replace("{n}", num)
        name = entry["name_template"].replace("{n}", num)
        top8_file = entry.get("top8_file", f"{entry['label']} Top 8 HTML.txt")
        out_path = ROOT / "Top_8_Texts" / top8_file
        if not out_path.exists():
            out_path.touch()
        cmd = [PYTHON, str(ROOT / "Python_Scripts" / "fetch_startgg_top8.py"), slug, "--name", name, "--out", str(out_path)]
        if link:
            cmd += ["--link", link]
        self._run(cmd, on_done=lambda e=entry: self._select_top8_event(e["label"]))

    def _delete_custom_event(self, slug_tmpl: str):
        self._custom_events = [e for e in self._custom_events
                               if e.get("slug_template", e.get("slug")) != slug_tmpl]
        self._save_custom_events()
        self._build_saved_custom_rows()
        self._refresh_thumbnail_events()

    def _fetch_sets(self, cfg: dict, n: str, abbrev: str = ""):
        name = cfg["name_template"].format(n=n)
        slug = cfg["slug_template"].format(n=n)
        out = str(ROOT / "Vod_Names" / f"{name} Names.txt")
        cmd = [PYTHON, str(ROOT / "Python_Scripts" / "fetch_sets.py"), slug, "--name", name, "--out", out]
        if abbrev:
            cmd += ["--abbrev", f"{abbrev} {n}".strip()]
        self._run(cmd)

    def _fetch_top8(self, cfg: dict, n: str, link: str):
        name = cfg["name_template"].format(n=n)
        slug = cfg["slug_template"].format(n=n)
        out = ROOT / "Top_8_Texts" / cfg["top8_file"]
        self._run([PYTHON, str(ROOT / "Python_Scripts" / "fetch_startgg_top8.py"),
                   slug, "--name", name, "--link", link, "--out", str(out)],
                  on_done=lambda c=cfg: self._select_top8_event(c["label"]))

    def _select_top8_event(self, label: str):
        if label in [self._top8_series.itemText(i) for i in range(self._top8_series.count())]:
            self._top8_series.setCurrentText(label)
        self._refresh_top8_files()

    # ================================================================== #
    #  Tab: Generate Thumbnails                                          #
    # ================================================================== #
    def _build_thumbnails_tab(self):
        lay = self._scroll_tab("Generate Thumbnails")

        box = QtWidgets.QGroupBox("Event")
        v = QtWidgets.QVBoxLayout(box)
        row1 = QtWidgets.QHBoxLayout()
        row1.addWidget(QtWidgets.QLabel("Series:"))
        self._thumb_series = QtWidgets.QComboBox()
        self._thumb_series.setMinimumWidth(220)
        row1.addWidget(self._thumb_series)
        refresh = QtWidgets.QPushButton("⟳")
        refresh.setObjectName("tool")
        refresh.setToolTip("Refresh event list")
        refresh.clicked.connect(self._refresh_thumbnail_events)
        row1.addWidget(refresh)
        row1.addSpacing(12)
        row1.addWidget(QtWidgets.QLabel("# / Suffix:"))
        self._thumb_num = _hline("274", 80)
        row1.addWidget(self._thumb_num)
        row1.addStretch(1)
        v.addLayout(row1)

        row2 = QtWidgets.QHBoxLayout()
        row2.addWidget(QtWidgets.QLabel("Event name:"))
        self._thumb_event_name = QtWidgets.QLineEdit()
        self._thumb_event_name.setMinimumWidth(320)
        row2.addWidget(self._thumb_event_name)
        row2.addStretch(1)
        v.addLayout(row2)
        lay.addWidget(box)

        self._thumb_event_map: dict[str, str] = {}
        self._thumb_series.currentTextChanged.connect(self._on_thumb_series_change)
        self._thumb_num.textChanged.connect(self._update_thumb_name)

        # Config section
        self._build_thumbnail_config(lay)

        row_gen = QtWidgets.QHBoxLayout()
        gen = QtWidgets.QPushButton("Generate Thumbnails")
        gen.setObjectName("accent")
        gen.clicked.connect(self._generate_thumbnails)
        row_gen.addWidget(gen)
        self._open_thumb_btn = QtWidgets.QPushButton("Open Output Folder")
        self._open_thumb_btn.clicked.connect(self._open_thumbnail_folder)
        row_gen.addWidget(self._open_thumb_btn)
        row_gen.addStretch(1)
        lay.addLayout(row_gen)
        self._thumb_event_name.textChanged.connect(self._refresh_open_folder_btn)

        self._build_vod_editor(lay)
        lay.addStretch(1)

        self._refresh_thumbnail_events()
        self._refresh_open_folder_btn()

    def _refresh_thumbnail_events(self):
        events = load_thumbnail_events()
        self._thumb_event_map = {name: tmpl for name, tmpl in events}
        names = [name for name, _ in events]
        for entry in self._custom_events:
            label = entry.get("label", "")
            name_tmpl = entry.get("name_template", "")
            if label and name_tmpl and label not in self._thumb_event_map:
                self._thumb_event_map[label] = name_tmpl
                names.append(label)
        cur = self._thumb_series.currentText()
        self._thumb_series.blockSignals(True)
        self._thumb_series.clear()
        self._thumb_series.addItems(names)
        if names:
            last = self._settings.get("last_thumb_series")
            if last in names:
                self._thumb_series.setCurrentText(last)
            elif cur in names:
                self._thumb_series.setCurrentText(cur)
            else:
                self._thumb_series.setCurrentIndex(0)
        self._thumb_series.blockSignals(False)
        self._on_thumb_series_change()
        if hasattr(self, "_top8_series"):
            self._refresh_top8_series()

    def _on_thumb_series_change(self):
        series = self._thumb_series.currentText()
        widgets = self._fetch_widgets.get(series)
        if widgets:
            self._thumb_num.setText(widgets["num"].text())
        else:
            custom = next((e for e in self._custom_events if e.get("label") == series), None)
            if custom:
                self._thumb_num.setText(custom.get("current_num", ""))
            else:
                saved = self._settings.get("last_event_nums", {}).get(series)
                if saved:
                    self._thumb_num.setText(saved)
        self._update_thumb_name()
        self._load_config_into_form(series)
        self._refresh_vod_files()
        self._save_settings()

    def _update_thumb_name(self):
        template = self._thumb_event_map.get(self._thumb_series.currentText(), "{n}")
        self._thumb_event_name.setText(template.format(n=self._thumb_num.text().strip()))
        self._save_settings()

    # --- Thumbnail config (writes melee_event_configs.json, applied by
    #     generate_melee_thumbnails.py as per-event property overrides) ---
    _CFG_FLOAT = ["resize_1", "resize_2", "resize_3"]
    _CFG_INT = ["font_player1_size", "font_player2_size", "font_event_size",
                "font_round_size", "text_angle"]
    _CFG_POS = ["center_shift_1", "center_shift_2_1", "center_shift_2_2",
                "center_shift_3_1", "center_shift_3_2", "center_shift_3_3",
                "text_player1", "text_player2", "text_event", "text_round",
                "char_offset1", "char_offset2", "char_window"]
    _CFG_COLOR = ["font_color1", "font_color2", "font_color3", "font_color4"]

    def _build_thumbnail_config(self, parent_layout):
        cbox = CollapsibleBox("Thumbnail Config", collapsed=True)
        parent_layout.addWidget(cbox)

        self._cfg_series_label = _muted("No series selected")
        cbox.addWidget(self._cfg_series_label)

        self._cfg_line: dict[str, QtWidgets.QLineEdit] = {}
        self._cfg_pos: dict[str, tuple[QtWidgets.QLineEdit, QtWidgets.QLineEdit]] = {}
        self._cfg_color: dict[str, ColorField] = {}

        def grid():
            g = QtWidgets.QGridLayout()
            g.setHorizontalSpacing(6)
            g.setVerticalSpacing(3)
            return g

        g = grid()
        g.addWidget(QtWidgets.QLabel("Background:"), 0, 0)
        self._cfg_background = QtWidgets.QLineEdit()
        g.addWidget(self._cfg_background, 0, 1)
        bg_btn = QtWidgets.QPushButton("Browse…")
        bg_btn.clicked.connect(lambda: self._browse_overlay(self._cfg_background))
        g.addWidget(bg_btn, 0, 2)
        g.addWidget(QtWidgets.QLabel("Foreground:"), 1, 0)
        self._cfg_foreground = QtWidgets.QLineEdit()
        g.addWidget(self._cfg_foreground, 1, 1)
        fg_btn = QtWidgets.QPushButton("Browse…")
        fg_btn.clicked.connect(lambda: self._browse_overlay(self._cfg_foreground))
        g.addWidget(fg_btn, 1, 2)
        g.addWidget(QtWidgets.QLabel("Font:"), 2, 0)
        self._cfg_font = QtWidgets.QComboBox()
        font_files = sorted(f.name for f in (ROOT / "Resources" / "Fonts").glob("*")
                            if f.suffix.lower() in (".ttf", ".otf"))
        self._cfg_font.addItems([""] + font_files)
        g.addWidget(self._cfg_font, 2, 1)
        cbox.addLayout(g)

        rowf = QtWidgets.QHBoxLayout()
        self._cfg_glow = QtWidgets.QCheckBox("Character Glow")
        self._cfg_one_char = QtWidgets.QCheckBox("One Character Per Player")
        rowf.addWidget(self._cfg_glow)
        rowf.addSpacing(20)
        rowf.addWidget(self._cfg_one_char)
        rowf.addStretch(1)
        cbox.addLayout(rowf)

        rs = QtWidgets.QHBoxLayout()
        rs.addWidget(QtWidgets.QLabel("Char Scale:"))
        for lbl, key in [("1-char", "resize_1"), ("2-char", "resize_2"), ("3-char", "resize_3")]:
            rs.addSpacing(8)
            rs.addWidget(QtWidgets.QLabel(lbl))
            e = _hline("", 60)
            self._cfg_line[key] = e
            rs.addWidget(e)
        rs.addStretch(1)
        cbox.addLayout(rs)

        def pos_row(label, *keys):
            r = QtWidgets.QHBoxLayout()
            lab = QtWidgets.QLabel(label)
            lab.setFixedWidth(90)
            r.addWidget(lab)
            for k in keys:
                xe, ye = _hline("", 60), _hline("", 60)
                self._cfg_pos[k] = (xe, ye)
                r.addWidget(QtWidgets.QLabel("x"))
                r.addWidget(xe)
                r.addWidget(QtWidgets.QLabel("y"))
                r.addWidget(ye)
                r.addSpacing(8)
            r.addStretch(1)
            cbox.addLayout(r)

        cbox.addWidget(_muted("Character Positions  (x, y — normalized -1 to 1):"))
        pos_row("1-char:", "center_shift_1")
        pos_row("2-char:", "center_shift_2_1", "center_shift_2_2")
        pos_row("3-char:", "center_shift_3_1", "center_shift_3_2", "center_shift_3_3")

        rsz = QtWidgets.QHBoxLayout()
        rsz.addWidget(QtWidgets.QLabel("Font Sizes:"))
        for lbl, key in [("P1", "font_player1_size"), ("P2", "font_player2_size"),
                         ("Event", "font_event_size"), ("Round", "font_round_size")]:
            rsz.addSpacing(8)
            rsz.addWidget(QtWidgets.QLabel(lbl))
            e = _hline("", 50)
            self._cfg_line[key] = e
            rsz.addWidget(e)
        rsz.addSpacing(16)
        rsz.addWidget(QtWidgets.QLabel("Angle°"))
        e = _hline("", 45)
        self._cfg_line["text_angle"] = e
        rsz.addWidget(e)
        rsz.addStretch(1)
        cbox.addLayout(rsz)

        cbox.addWidget(_muted("Font Colors  (P1, P2, Event, Round):"))
        rc = QtWidgets.QHBoxLayout()
        for lbl, key in [("P1:", "font_color1"), ("P2:", "font_color2"),
                         ("Event:", "font_color3"), ("Round:", "font_color4")]:
            rc.addWidget(QtWidgets.QLabel(lbl))
            cf = ColorField("#FFFFFF")
            self._cfg_color[key] = cf
            rc.addWidget(cf)
            rc.addSpacing(12)
        rc.addStretch(1)
        cbox.addLayout(rc)

        cbox.addWidget(_muted("Text Label Positions  (x, y — normalized 0 to 1):"))
        pos_row("Player 1:", "text_player1")
        pos_row("Player 2:", "text_player2")
        pos_row("Event:", "text_event")
        pos_row("Round:", "text_round")

        rcw = QtWidgets.QHBoxLayout()
        lab = QtWidgets.QLabel("Char Window:")
        lab.setFixedWidth(90)
        rcw.addWidget(lab)
        rcw.addWidget(QtWidgets.QLabel("w"))
        cw_w = _hline("", 60)
        rcw.addWidget(cw_w)
        rcw.addWidget(QtWidgets.QLabel("h"))
        cw_h = _hline("", 60)
        rcw.addWidget(cw_h)
        rcw.addStretch(1)
        self._cfg_pos["char_window"] = (cw_w, cw_h)
        cbox.addLayout(rcw)

        cbox.addWidget(_muted("Character Offsets  (x, y — normalized):"))
        pos_row("P1 Offset:", "char_offset1")
        pos_row("P2 Offset:", "char_offset2")

        rer = QtWidgets.QHBoxLayout()
        self._cfg_single_text = QtWidgets.QCheckBox("Single Text Block")
        rer.addWidget(self._cfg_single_text)
        rer.addSpacing(20)
        rer.addWidget(QtWidgets.QLabel("Separator:"))
        self._cfg_text_split = _hline("", 110)
        rer.addWidget(self._cfg_text_split)
        rer.addStretch(1)
        cbox.addLayout(rer)
        cbox.addWidget(_muted(
            "Single Text Block: renders the event name and round as one combined label.\n"
            "Separator: the string placed between them, e.g. \" — \"."))

        rcb = QtWidgets.QHBoxLayout()
        save = QtWidgets.QPushButton("Save Config")
        save.clicked.connect(self._save_thumbnail_config)
        rcb.addWidget(save)
        clear = QtWidgets.QPushButton("Clear Config")
        clear.clicked.connect(self._clear_thumbnail_config)
        rcb.addWidget(clear)
        rcb.addStretch(1)
        cbox.addLayout(rcb)

    def _load_config_into_form(self, series: str):
        if not hasattr(self, "_cfg_series_label"):
            return
        self._cfg_series_label.setText(f"Editing: {series}" if series else "No series selected")
        saved = self._event_configs.get(series, {})
        base = _base_event_props(series)
        cfg = {**base, **saved}

        self._cfg_background.setText(cfg.get("background_file", ""))
        self._cfg_foreground.setText(cfg.get("foreground_file", ""))
        font_path = cfg.get("font_location", "")
        self._cfg_font.setCurrentText(Path(font_path).name if font_path else "")
        self._cfg_glow.setChecked(bool(cfg.get("char_glow_bool", False)))
        self._cfg_one_char.setChecked(bool(cfg.get("one_char_flag", False)))

        for key in self._CFG_FLOAT + self._CFG_INT:
            self._cfg_line[key].setText(str(cfg[key]) if key in cfg else "")

        for key in self._CFG_POS:
            xe, ye = self._cfg_pos[key]
            val = cfg.get(key)
            if isinstance(val, (list, tuple)) and len(val) >= 2:
                xe.setText(str(val[0]))
                ye.setText(str(val[1]))
            else:
                xe.setText("")
                ye.setText("")

        for key in self._CFG_COLOR:
            self._cfg_color[key].setValue(cfg.get(key, "#FFFFFF"))

        self._cfg_single_text.setChecked(bool(cfg.get("event_round_single_text", False)))
        self._cfg_text_split.setText(cfg.get("event_round_text_split", ""))

    def _save_thumbnail_config(self):
        series = self._thumb_series.currentText().strip()
        if not series:
            self._log("[Error: no series selected]\n")
            return
        cfg: dict = {}
        bg = self._cfg_background.text().strip()
        fg = self._cfg_foreground.text().strip()
        font_name = self._cfg_font.currentText().strip()
        if bg:
            cfg["background_file"] = bg
        if fg:
            cfg["foreground_file"] = fg
        if font_name:
            cfg["font_location"] = str(Path("Resources") / "Fonts" / font_name)
        cfg["char_glow_bool"] = self._cfg_glow.isChecked()
        cfg["one_char_flag"] = self._cfg_one_char.isChecked()

        for key in self._CFG_FLOAT:
            val = self._cfg_line[key].text().strip()
            if val:
                try:
                    cfg[key] = float(val)
                except ValueError:
                    pass
        for key in self._CFG_INT:
            val = self._cfg_line[key].text().strip()
            if val:
                try:
                    cfg[key] = int(val)
                except ValueError:
                    pass
        for key in self._CFG_POS:
            xe, ye = self._cfg_pos[key]
            x, y = xe.text().strip(), ye.text().strip()
            if x and y:
                try:
                    cfg[key] = [float(x), float(y)]
                except ValueError:
                    pass
        for key in self._CFG_COLOR:
            c = self._cfg_color[key].value()
            if c:
                cfg[key] = c

        cfg["event_round_single_text"] = self._cfg_single_text.isChecked()
        split = self._cfg_text_split.text()
        if split:
            cfg["event_round_text_split"] = split

        self._event_configs[series] = cfg
        self._save_event_configs()
        self._log(f"[Config saved for \"{series}\"]\n")

    def _clear_thumbnail_config(self):
        series = self._thumb_series.currentText().strip()
        if series in self._event_configs:
            del self._event_configs[series]
            self._save_event_configs()
        self._cfg_background.clear()
        self._cfg_foreground.clear()
        self._cfg_font.setCurrentText("")
        self._cfg_glow.setChecked(False)
        self._cfg_one_char.setChecked(False)
        for e in self._cfg_line.values():
            e.clear()
        for xe, ye in self._cfg_pos.values():
            xe.clear()
            ye.clear()
        for cf in self._cfg_color.values():
            cf.setValue("#FFFFFF")
        self._cfg_single_text.setChecked(False)
        self._cfg_text_split.clear()
        self._log(f"[Config cleared for \"{series}\"]\n")

    def _browse_overlay(self, target: QtWidgets.QLineEdit):
        path, _ = QtWidgets.QFileDialog.getOpenFileName(
            self, "Select overlay image", "",
            "Images (*.png *.jpg *.jpeg);;All files (*.*)")
        if not path:
            return
        dest_dir = ROOT / "Resources" / "Overlays"
        dest_dir.mkdir(parents=True, exist_ok=True)
        dest = dest_dir / Path(path).name
        if Path(path).resolve() != dest.resolve():
            shutil.copy2(path, dest)
        target.setText(str(Path("Resources") / "Overlays" / Path(path).name))

    def _generate_thumbnails(self):
        event_name = self._thumb_event_name.text().strip()
        if not event_name:
            self._log("[Error: event name is empty]\n")
            return
        self._run([PYTHON, str(ROOT / "Python_Scripts" / "generate_melee_thumbnails.py"),
                   "-e", event_name, "-o", str(ROOT / "Vod_Names" / "missing.log")],
                  on_done=self._refresh_open_folder_btn)

    def _refresh_open_folder_btn(self):
        event_name = self._thumb_event_name.text().strip()
        folder = ROOT / "Youtube_Thumbnails" / event_name
        self._open_thumb_btn.setEnabled(bool(event_name) and folder.is_dir())

    def _open_thumbnail_folder(self):
        folder = ROOT / "Youtube_Thumbnails" / self._thumb_event_name.text().strip()
        if not folder.is_dir():
            self._log(f"[Error: output folder not found: {folder}]\n")
            return
        try:
            os.startfile(str(folder))
        except Exception as exc:
            self._log(f"[Error opening folder: {exc}]\n")

    # --- VOD editor (virtualized table) ---
    def _build_vod_editor(self, parent_layout):
        cbox = CollapsibleBox("VOD Names", collapsed=False)
        parent_layout.addWidget(cbox)

        row = QtWidgets.QHBoxLayout()
        row.addWidget(QtWidgets.QLabel("File:"))
        self._vod_file = QtWidgets.QComboBox()
        self._vod_file.setMinimumWidth(360)
        row.addWidget(self._vod_file)
        rb = QtWidgets.QPushButton("⟳")
        rb.setObjectName("tool")
        rb.setToolTip("Refresh VOD file list")
        rb.clicked.connect(self._refresh_vod_files)
        row.addWidget(rb)
        row.addSpacing(20)
        row.addWidget(QtWidgets.QLabel("Character:"))
        self._vod_char_picker = QtWidgets.QComboBox()
        self._vod_char_picker.setMinimumWidth(160)
        self._vod_char_picker.setToolTip(
            "Pick a character, then Copy to paste the exact spelling into a VOD line")
        self._refresh_vod_char_picker()
        row.addWidget(self._vod_char_picker)
        crb = QtWidgets.QPushButton("⟳")
        crb.setObjectName("tool")
        crb.setToolTip("Refresh character list")
        crb.clicked.connect(self._refresh_vod_char_picker)
        row.addWidget(crb)
        cc = QtWidgets.QPushButton("Copy")
        cc.setToolTip("Copy the selected character name to the clipboard")
        cc.clicked.connect(self._copy_vod_char)
        row.addWidget(cc)
        row.addStretch(1)
        cbox.addLayout(row)

        self._vod_model = VodModel()
        self._vod_view = QtWidgets.QTableView()
        self._vod_view.setModel(self._vod_model)
        self._vod_view.setMinimumHeight(330)
        self._vod_view.verticalHeader().setVisible(False)
        self._vod_view.horizontalHeader().setSectionResizeMode(
            2, QtWidgets.QHeaderView.ResizeMode.Stretch)
        self._vod_view.setColumnWidth(0, 30)
        self._vod_view.setColumnWidth(1, 34)
        self._vod_view.setColumnWidth(3, 64)
        self._vod_view.setMouseTracking(True)
        self._vod_copy_delegate = CopyButtonDelegate(self._vod_view)
        self._vod_copy_delegate.copyRequested.connect(self._vod_copy_row)
        self._vod_view.setItemDelegateForColumn(1, self._vod_copy_delegate)
        self._vod_view.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self._vod_view.customContextMenuRequested.connect(self._vod_context_menu)
        self._vod_model.dataChanged.connect(lambda *_: self._vod_update_delete_btn())
        self._vod_model.modelReset.connect(self._vod_update_delete_btn)
        cbox.addWidget(self._vod_view)

        rb2 = QtWidgets.QHBoxLayout()
        save = QtWidgets.QPushButton("Save")
        save.clicked.connect(self._save_vod_file)
        rb2.addWidget(save)
        addr = QtWidgets.QPushButton("Add Row")
        addr.clicked.connect(self._vod_add_new_row)
        rb2.addWidget(addr)
        self._vod_delete_btn = QtWidgets.QPushButton("Delete Marked")
        self._vod_delete_btn.setEnabled(False)
        self._vod_delete_btn.clicked.connect(self._vod_delete_marked)
        rb2.addWidget(self._vod_delete_btn)
        ca = QtWidgets.QPushButton("Check All")
        ca.clicked.connect(lambda: self._vod_model.set_all(True))
        rb2.addWidget(ca)
        ua = QtWidgets.QPushButton("Uncheck All")
        ua.clicked.connect(lambda: self._vod_model.set_all(False))
        rb2.addWidget(ua)
        rb2.addStretch(1)
        cbox.addLayout(rb2)

        self._vod_file.currentTextChanged.connect(self._load_vod_file)

    def _refresh_vod_char_picker(self):
        cur = self._vod_char_picker.currentText()
        chars = sorted(get_characters_from_renders(), key=str.casefold)
        self._vod_char_picker.blockSignals(True)
        self._vod_char_picker.clear()
        self._vod_char_picker.addItems(chars)
        if cur in chars:
            self._vod_char_picker.setCurrentText(cur)
        self._vod_char_picker.blockSignals(False)

    def _copy_vod_char(self):
        name = self._vod_char_picker.currentText().strip()
        if not name:
            return
        QtWidgets.QApplication.clipboard().setText(name)
        self._log(f"[Copied character to clipboard: {name}]\n")

    def _vod_context_menu(self, pos):
        idx = self._vod_view.indexAt(pos)
        if not idx.isValid():
            return
        menu = QtWidgets.QMenu(self)
        copy_act = menu.addAction("Copy line")
        del_act = menu.addAction("Delete line")
        act = menu.exec(self._vod_view.viewport().mapToGlobal(pos))
        if act == copy_act:
            QtWidgets.QApplication.clipboard().setText(self._vod_model.text_at(idx.row()))
            self._log(f"[Copied to clipboard: {self._vod_model.text_at(idx.row())}]\n")
        elif act == del_act:
            self._vod_model.delete_row(idx.row())
            self._vod_update_delete_btn()

    def _refresh_vod_files(self):
        vod_dir = ROOT / "Vod_Names"
        series = self._thumb_series.currentText()
        files = []
        if vod_dir.exists():
            for f in vod_dir.glob("*.txt"):
                if not series or f.name.startswith(series):
                    files.append(f)

        def _key(p):
            nums = re.findall(r"\d+", p.stem)
            return (-int(nums[-1]) if nums else 0, p.stem)

        files.sort(key=_key)
        names = [f.name for f in files]
        cur = self._vod_file.currentText()
        self._vod_file.blockSignals(True)
        self._vod_file.clear()
        self._vod_file.addItems(names)
        if names:
            self._vod_file.setCurrentText(cur if cur in names else names[0])
        self._vod_file.blockSignals(False)
        if names:
            self._load_vod_file()
        else:
            self._vod_model.load([])

    def _load_vod_file(self):
        name = self._vod_file.currentText()
        if not name:
            self._vod_model.load([])
            return
        try:
            content = (ROOT / "Vod_Names" / name).read_text(encoding="utf-8")
        except Exception:
            content = ""
        lines = [l for l in content.splitlines() if l.strip()]
        self._vod_model.load(lines)
        self._vod_update_delete_btn()

    def _vod_add_new_row(self):
        pos = self._vod_model.add_blank()
        idx = self._vod_model.index(pos, 2)
        self._vod_view.scrollTo(idx)
        self._vod_view.setCurrentIndex(idx)
        self._vod_view.edit(idx)

    def _vod_copy_row(self, r: int):
        text = self._vod_model.text_at(r)
        if text:
            QtWidgets.QApplication.clipboard().setText(text)
            self._log(f"[Copied to clipboard: {text}]\n")

    def _vod_delete_marked(self):
        removed = self._vod_model.delete_marked()
        if removed:
            self._log(f"[Deleted {removed} marked row(s)]\n")
        else:
            self._log("[No rows marked to delete]\n")
        self._vod_update_delete_btn()

    def _vod_update_delete_btn(self):
        if hasattr(self, "_vod_delete_btn"):
            self._vod_delete_btn.setEnabled(self._vod_model.any_checked())

    def _save_vod_file(self):
        name = self._vod_file.currentText()
        if not name:
            self._log("[Error: no VOD names file selected]\n")
            return
        (ROOT / "Vod_Names" / name).write_text(self._vod_model.to_text(), encoding="utf-8")
        self._log(f"[Saved {name}]\n")

    # ================================================================== #
    #  Tab: Generate Top 8s                                             #
    # ================================================================== #
    def _build_top8_tab(self):
        lay = self._scroll_tab("Generate Top 8s")

        box = QtWidgets.QGroupBox("Event")
        v = QtWidgets.QVBoxLayout(box)
        row1 = QtWidgets.QHBoxLayout()
        row1.addWidget(QtWidgets.QLabel("Series:"))
        self._top8_series = QtWidgets.QComboBox()
        self._top8_series.setMinimumWidth(220)
        row1.addWidget(self._top8_series)
        rb = QtWidgets.QPushButton("⟳")
        rb.setObjectName("tool")
        rb.setToolTip("Refresh series list")
        rb.clicked.connect(self._refresh_top8_series)
        row1.addWidget(rb)
        row1.addStretch(1)
        v.addLayout(row1)
        row2 = QtWidgets.QHBoxLayout()
        row2.addWidget(QtWidgets.QLabel("Event name:"))
        self._top8_event_name = _muted("")
        row2.addWidget(self._top8_event_name)
        row2.addStretch(1)
        v.addLayout(row2)
        lay.addWidget(box)

        self._top8_series.currentTextChanged.connect(self._on_top8_change)

        ctxt = CollapsibleBox("Top 8 Text Data", collapsed=False)
        lay.addWidget(ctxt)
        self._top8_text_path_label = _muted("")
        ctxt.addWidget(self._top8_text_path_label)
        self._top8_text = QtWidgets.QPlainTextEdit()
        self._top8_text.setLineWrapMode(QtWidgets.QPlainTextEdit.LineWrapMode.NoWrap)
        self._top8_text.setMinimumHeight(320)
        Top8DataHighlighter(self._top8_text.document())
        ctxt.addWidget(self._top8_text)
        save_txt = QtWidgets.QPushButton("Save")
        save_txt.clicked.connect(self._save_top8_text)
        ctxt.addWidget(save_txt)

        chtml = CollapsibleBox("Top 8 HTML Result", collapsed=False)
        lay.addWidget(chtml)
        rowh = QtWidgets.QHBoxLayout()
        rowh.addWidget(QtWidgets.QLabel("File:"))
        self._top8_html_file = QtWidgets.QComboBox()
        self._top8_html_file.setMinimumWidth(320)
        rowh.addWidget(self._top8_html_file)
        rbh = QtWidgets.QPushButton("⟳")
        rbh.setObjectName("tool")
        rbh.setToolTip("Refresh HTML file list")
        rbh.clicked.connect(self._refresh_top8_html_files)
        rowh.addWidget(rbh)
        openb = QtWidgets.QPushButton("Open in Browser")
        openb.clicked.connect(self._open_top8_html_in_browser)
        rowh.addWidget(openb)
        rowh.addStretch(1)
        chtml.addLayout(rowh)

        self._top8_html_warning = QtWidgets.QLabel("")
        self._top8_html_warning.setObjectName("warning")
        self._top8_html_warning.setWordWrap(True)
        chtml.addWidget(self._top8_html_warning)
        chtml.addWidget(_muted(
            "The HTML files are designed for OBS's fixed canvas, not for interactive browser viewing. "
            "The browser preview is for spot-checking data (names, placements), not pixel-perfect layout. "
            "Use Ctrl + + to zoom in, Ctrl+0 to reset."))

        self._build_top8_layout_config(chtml)

        chtml_src = CollapsibleBox("HTML Source", collapsed=True)
        chtml.addWidget(chtml_src)
        self._top8_html_text = QtWidgets.QPlainTextEdit()
        self._top8_html_text.setLineWrapMode(QtWidgets.QPlainTextEdit.LineWrapMode.NoWrap)
        self._top8_html_text.setMinimumHeight(360)
        HtmlHighlighter(self._top8_html_text.document())
        chtml_src.addWidget(self._top8_html_text)
        save_html = QtWidgets.QPushButton("Save")
        save_html.clicked.connect(self._save_top8_html)
        chtml_src.addWidget(save_html)

        self._top8_html_file.currentTextChanged.connect(self._load_top8_html)
        self._d8_last_html_file = None
        lay.addStretch(1)

        self._refresh_top8_series()

    def _refresh_top8_series(self):
        names = list(getattr(self, "_thumb_event_map", {}).keys())
        cur = self._top8_series.currentText()
        self._top8_series.blockSignals(True)
        self._top8_series.clear()
        self._top8_series.addItems(names)
        if names:
            self._top8_series.setCurrentText(cur if cur in names else names[0])
        self._top8_series.blockSignals(False)
        self._on_top8_change()

    def _on_top8_change(self):
        self._refresh_top8_files()

    def _get_top8_text_path(self) -> Path:
        series = self._top8_series.currentText()
        for cfg in FETCH_EVENTS:
            if cfg["label"] == series:
                return ROOT / "Top_8_Texts" / cfg["top8_file"]
        for entry in self._custom_events:
            if entry.get("label") == series:
                return ROOT / "Top_8_Texts" / entry.get("top8_file", f"{series} Top 8 HTML.txt")
        return ROOT / "Top_8_Texts" / f"{series} Top 8 HTML.txt"

    def _refresh_top8_files(self):
        self._load_top8_text()
        self._refresh_top8_html_files()

    def _load_top8_text(self):
        path = self._get_top8_text_path()
        try:
            rel = str(path.relative_to(ROOT))
        except ValueError:
            rel = str(path)
        self._top8_text_path_label.setText(rel)
        if not path.exists():
            series = self._top8_series.currentText()
            template = self._thumb_event_map.get(series, series)
            event_name = template.format(n="").strip()
            content = (
                "# Top 8 Graphic\n# All information is tab deliminated\n\n"
                "#Graphic Information\n"
                f"Event name:\t{event_name}\n"
                "Event link:\t\nEvent entrants:\t Competitors\nEvent date:\t\n\n"
                "# Placements\n# place, name, sponsor, characters\n"
                "1,,,\n2,,,\n3,,,\n4,,,\n5,,,\n5,,,\n7,,,\n7,,,"
            )
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content, encoding="utf-8")
            self._log(f"[Auto-created {path.name}]\n")
        content = path.read_text(encoding="utf-8")
        self._top8_text.setPlainText(content)
        m = re.search(r'(?m)^Event name:\t*(.*)$', content)
        self._top8_event_name.setText(
            m.group(1).strip() if m and m.group(1).strip()
            else self._top8_series.currentText())

    def _save_top8_text(self):
        path = self._get_top8_text_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(self._top8_text.toPlainText(), encoding="utf-8")
        self._log(f"[Saved {path.name}]\n")

    def _refresh_top8_html_files(self):
        results_dir = ROOT / "Top_8_Results"
        series = self._top8_series.currentText()
        all_files = sorted(f.name for f in results_dir.glob("*.html")) if results_dir.exists() else []
        series_files = [f for f in all_files if f.startswith(series)]
        files = series_files or all_files
        cur = self._top8_html_file.currentText()
        self._top8_html_file.blockSignals(True)
        self._top8_html_file.clear()
        self._top8_html_file.addItems(files)
        self._top8_html_file.blockSignals(False)
        if files:
            self._top8_html_warning.setText("")
            if cur in files:
                sel = cur
            elif series_files:
                top8 = [f for f in series_files if "Top 8" in f]
                sel = top8[-1] if top8 else series_files[-1]
            else:
                sel = files[0]
            self._top8_html_file.setCurrentText(sel)
            self._load_top8_html()
        else:
            self._top8_html_text.clear()
            self._top8_html_warning.setText(
                "⚠ No Top 8 HTML file found in Top_8_Results/. "
                "Create one by copying an existing template.")

    def _load_top8_html(self):
        name = self._top8_html_file.currentText()
        if not name:
            return
        path = ROOT / "Top_8_Results" / name
        if not path.exists():
            return
        self._top8_html_text.setPlainText(path.read_text(encoding="utf-8"))
        if name != self._d8_last_html_file:
            self._d8_last_html_file = name
            self._load_top8_layout_config()
            self._load_top8_text()

    def _save_top8_html(self):
        name = self._top8_html_file.currentText()
        if not name:
            self._log("[Error: no HTML file selected]\n")
            return
        path = ROOT / "Top_8_Results" / name
        path.write_text(self._top8_html_text.toPlainText(), encoding="utf-8")
        self._log(f"[Saved {name}]\n")

    # --- Top 8 layout config (edits CSS in the selected HTML by element id) ---
    def _build_top8_layout_config(self, parent_box):
        cbox = CollapsibleBox("Layout Config", collapsed=True)
        parent_box.addWidget(cbox)

        self._d8_label_color = ColorField("#ffffff")
        self._d8_sponsor_color = ColorField("#FFD700")
        self._d8_event = []
        for i in range(4):
            d = {"top": _hline("", 60), "left": _hline("", 60), "size": _hline("", 60)}
            if i == 0:
                d["color"] = ColorField("#ffffff")
            self._d8_event.append(d)
        self._d8_renders = [{"top": _hline("", 60), "left": _hline("", 60), "height": _hline("", 60)} for _ in range(8)]
        self._d8_nums = [{"top": _hline("", 60), "left": _hline("", 60), "size": _hline("", 60)} for _ in range(8)]
        self._d8_names = [{"top": _hline("", 60), "left": _hline("", 60), "size": _hline("", 60)} for _ in range(8)]
        self._d8_sponsors = [{"top": _hline("", 60), "left": _hline("", 60), "size": _hline("", 60)} for _ in range(8)]

        colbox = QtWidgets.QGroupBox("Colors")
        ch = QtWidgets.QHBoxLayout(colbox)
        ch.addWidget(QtWidgets.QLabel("Label:"))
        ch.addWidget(self._d8_label_color)
        ch.addSpacing(20)
        ch.addWidget(QtWidgets.QLabel("Sponsor:"))
        ch.addWidget(self._d8_sponsor_color)
        ch.addStretch(1)
        cbox.addWidget(colbox)

        evbox = QtWidgets.QGroupBox("Event Info")
        eg = QtWidgets.QGridLayout(evbox)
        for ci, txt in enumerate(["", "Top %", "Left %", "Size px", "Color"]):
            eg.addWidget(_muted(txt), 0, ci)
        for i, lbl in enumerate(["Name", "Link", "Entrants", "Date"]):
            f = self._d8_event[i]
            eg.addWidget(QtWidgets.QLabel(lbl + ":"), i + 1, 0)
            eg.addWidget(f["top"], i + 1, 1)
            eg.addWidget(f["left"], i + 1, 2)
            eg.addWidget(f["size"], i + 1, 3)
            if "color" in f:
                eg.addWidget(f["color"], i + 1, 4)
        eg.setColumnStretch(5, 1)
        cbox.addWidget(evbox)

        def slot_section(title, vars_list, col3_lbl):
            gb = QtWidgets.QGroupBox(title)
            g = QtWidgets.QGridLayout(gb)
            for ci, txt in enumerate(["Place", "Top %", "Left %", col3_lbl]):
                g.addWidget(_muted(txt), 0, ci)
            for i, f in enumerate(vars_list):
                g.addWidget(QtWidgets.QLabel(str(i + 1)), i + 1, 0)
                g.addWidget(f["top"], i + 1, 1)
                g.addWidget(f["left"], i + 1, 2)
                third = "height" if "height" in f else "size"
                g.addWidget(f[third], i + 1, 3)
            g.setColumnStretch(4, 1)
            cbox.addWidget(gb)

        slot_section("Character Renders", self._d8_renders, "Height %")
        slot_section("Placement Numbers", self._d8_nums, "Size px")
        slot_section("Player Names", self._d8_names, "Size px")
        slot_section("Sponsors", self._d8_sponsors, "Size px")

        apply_btn = QtWidgets.QPushButton("Apply Config && Save")
        apply_btn.setObjectName("accent")
        apply_btn.clicked.connect(self._apply_top8_layout_config)
        cbox.addWidget(apply_btn)

    def _load_top8_layout_config(self):
        html = self._top8_html_text.toPlainText()

        def get_style(elem_id):
            m = re.search(rf'id="{re.escape(elem_id)}"[^>]*?style="([^"]*)"', html)
            return m.group(1) if m else ""

        def num_prop(style, name):
            m = re.search(rf'{re.escape(name)}:\s*([\d.]+)', style)
            return m.group(1) if m else ""

        def color_prop(style):
            m = re.search(r'color:\s*(#[0-9a-fA-F]+)', style)
            return m.group(1) if m else ""

        m = re.search(r'#canvas \.label \{[^}]*color:\s*(#[0-9a-fA-F]+)', html, re.DOTALL)
        self._d8_label_color.setValue(m.group(1) if m else "#ffffff")
        m = re.search(r'#canvas \.sponsor \{[^}]*color:\s*(#[0-9a-fA-F]+)', html, re.DOTALL)
        self._d8_sponsor_color.setValue(m.group(1) if m else "#FFD700")

        for i, eid in enumerate(["event-name", "event-link", "event-entrants", "event-date"]):
            s = get_style(eid)
            f = self._d8_event[i]
            f["top"].setText(num_prop(s, "top"))
            f["left"].setText(num_prop(s, "left"))
            f["size"].setText(num_prop(s, "font-size"))
            if "color" in f:
                f["color"].setValue(color_prop(s) or "#ffffff")

        for i in range(8):
            n = i + 1
            s = get_style(f"place-{n}-render")
            self._d8_renders[i]["top"].setText(num_prop(s, "top"))
            self._d8_renders[i]["left"].setText(num_prop(s, "left"))
            self._d8_renders[i]["height"].setText(num_prop(s, "height"))
            s = get_style(f"place-{n}-num")
            self._d8_nums[i]["top"].setText(num_prop(s, "top"))
            self._d8_nums[i]["left"].setText(num_prop(s, "left"))
            self._d8_nums[i]["size"].setText(num_prop(s, "font-size"))
            s = get_style(f"place-{n}-name")
            self._d8_names[i]["top"].setText(num_prop(s, "top"))
            self._d8_names[i]["left"].setText(num_prop(s, "left"))
            self._d8_names[i]["size"].setText(num_prop(s, "font-size"))
            s = get_style(f"place-{n}-sponsor")
            self._d8_sponsors[i]["top"].setText(num_prop(s, "top"))
            self._d8_sponsors[i]["left"].setText(num_prop(s, "left"))
            self._d8_sponsors[i]["size"].setText(num_prop(s, "font-size"))

    def _apply_top8_layout_config(self):
        html = self._top8_html_text.toPlainText()

        def patch_style(h, elem_id, props):
            def repl(m):
                style = m.group(2)
                for prop, val, unit in props:
                    if unit == "color":
                        style = re.sub(r'(color:\s*)#[0-9a-fA-F]+', rf'\g<1>{val}', style)
                    elif unit in ("%", "px"):
                        style = re.sub(rf'({re.escape(prop)}:\s*)[\d.]+({re.escape(unit)})', rf'\g<1>{val}\2', style)
                return m.group(1) + style + '"'
            return re.sub(rf'(id="{re.escape(elem_id)}"[^>]*?style=")([^"]*)"', repl, h)

        label_color = self._d8_label_color.value()
        sponsor_color = self._d8_sponsor_color.value()
        html = re.sub(r'(#canvas \.label \{[^}]*color:\s*)#[0-9a-fA-F]+',
                      rf'\g<1>{label_color}', html, flags=re.DOTALL)
        html = re.sub(r'(#canvas \.sponsor \{[^}]*color:\s*)#[0-9a-fA-F]+',
                      rf'\g<1>{sponsor_color}', html, flags=re.DOTALL)

        for i, eid in enumerate(["event-name", "event-link", "event-entrants", "event-date"]):
            f = self._d8_event[i]
            props = [("top", f["top"].text(), "%"), ("left", f["left"].text(), "%"),
                     ("font-size", f["size"].text(), "px")]
            if "color" in f:
                props.append(("color", f["color"].value(), "color"))
            html = patch_style(html, eid, props)

        for i in range(8):
            n = i + 1
            f = self._d8_renders[i]
            html = patch_style(html, f"place-{n}-render", [
                ("top", f["top"].text(), "%"), ("left", f["left"].text(), "%"),
                ("height", f["height"].text(), "%")])
            f = self._d8_nums[i]
            html = patch_style(html, f"place-{n}-num", [
                ("top", f["top"].text(), "%"), ("left", f["left"].text(), "%"),
                ("font-size", f["size"].text(), "px")])
            f = self._d8_names[i]
            html = patch_style(html, f"place-{n}-name", [
                ("top", f["top"].text(), "%"), ("left", f["left"].text(), "%"),
                ("font-size", f["size"].text(), "px")])
            f = self._d8_sponsors[i]
            html = patch_style(html, f"place-{n}-sponsor", [
                ("top", f["top"].text(), "%"), ("left", f["left"].text(), "%"),
                ("font-size", f["size"].text(), "px")])

        self._top8_html_text.setPlainText(html)
        self._save_top8_html()

    def _open_top8_html_in_browser(self):
        name = self._top8_html_file.currentText()
        if not name:
            self._log("[Error: no HTML file selected]\n")
            return
        if not self._http_server:
            with socket.socket() as s:
                s.bind(("", 0))
                port = s.getsockname()[1]
            handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=str(ROOT))
            server = socketserver.TCPServer(("", port), handler)
            server.allow_reuse_address = True
            threading.Thread(target=server.serve_forever, daemon=True, name="top8-http-server").start()
            self._http_server = server
            self._http_server_port = port
            self._log(f"[Local server started on port {port}]\n")
        url = f"http://localhost:{self._http_server_port}/Top_8_Results/{name}"
        webbrowser.open(url)
        self._log(f"[Opened {url}]\n")

    # ================================================================== #
    #  Tab: Generate Posts                                              #
    # ================================================================== #
    def _build_posts_tab(self):
        lay = self._scroll_tab("Generate Posts")

        box = QtWidgets.QGroupBox("Event")
        v = QtWidgets.QVBoxLayout(box)
        row1 = QtWidgets.QHBoxLayout()
        row1.addWidget(QtWidgets.QLabel("Series:"))
        self._posts_series = QtWidgets.QComboBox()
        self._posts_series.setMinimumWidth(220)
        row1.addWidget(self._posts_series)
        rb = QtWidgets.QPushButton("⟳")
        rb.setObjectName("tool")
        rb.setToolTip("Refresh event list")
        rb.clicked.connect(self._refresh_posts_events)
        row1.addWidget(rb)
        row1.addSpacing(12)
        row1.addWidget(QtWidgets.QLabel("# / Suffix:"))
        self._posts_num = _hline("", 80)
        row1.addWidget(self._posts_num)
        row1.addStretch(1)
        v.addLayout(row1)
        row2 = QtWidgets.QHBoxLayout()
        row2.addWidget(QtWidgets.QLabel("Event name:"))
        self._posts_event_name = QtWidgets.QLineEdit()
        self._posts_event_name.setReadOnly(True)
        self._posts_event_name.setMinimumWidth(320)
        row2.addWidget(self._posts_event_name)
        row2.addStretch(1)
        v.addLayout(row2)
        lay.addWidget(box)

        cfgbox = QtWidgets.QGroupBox("Post Settings")
        cv = QtWidgets.QVBoxLayout(cfgbox)
        rn = QtWidgets.QHBoxLayout()
        self._posts_has_next = QtWidgets.QCheckBox("Next Event")
        self._posts_has_next.setChecked(True)
        self._posts_has_next.toggled.connect(self._update_posts_next_state)
        rn.addWidget(self._posts_has_next)
        rn.addSpacing(8)
        rn.addWidget(QtWidgets.QLabel("Date:"))
        self._posts_date = QtWidgets.QDateEdit()
        self._posts_date.setCalendarPopup(True)
        self._posts_date.setDisplayFormat("yyyy-MM-dd")
        self._posts_date.setDate(QtCore.QDate.currentDate())
        rn.addWidget(self._posts_date)
        rn.addSpacing(16)
        rn.addWidget(QtWidgets.QLabel("Link:"))
        self._posts_next_link = QtWidgets.QLineEdit()
        self._posts_next_link.setMinimumWidth(260)
        rn.addWidget(self._posts_next_link)
        rn.addStretch(1)
        cv.addLayout(rn)

        rv = QtWidgets.QHBoxLayout()
        rv.addWidget(QtWidgets.QLabel("Vods link:"))
        self._posts_vods = QtWidgets.QLineEdit()
        self._posts_vods.setMinimumWidth(420)
        rv.addWidget(self._posts_vods)
        rv.addStretch(1)
        cv.addLayout(rv)

        rb2 = QtWidgets.QHBoxLayout()
        ft = QtWidgets.QPushButton("Fetch Twitter")
        ft.clicked.connect(lambda: self._run_fetch_post("twitter"))
        rb2.addWidget(ft)
        fd = QtWidgets.QPushButton("Fetch Discord")
        fd.clicked.connect(lambda: self._run_fetch_post("discord"))
        rb2.addWidget(fd)
        rb2.addSpacing(16)
        sv = QtWidgets.QPushButton("Save")
        sv.clicked.connect(self._save_post_file)
        rb2.addWidget(sv)
        cp = QtWidgets.QPushButton("Copy")
        cp.clicked.connect(self._copy_post_text)
        rb2.addWidget(cp)
        rb2.addStretch(1)
        cv.addLayout(rb2)
        lay.addWidget(cfgbox)

        ctext = CollapsibleBox("Post Text", collapsed=False)
        lay.addWidget(ctext)
        self._posts_text = QtWidgets.QPlainTextEdit()
        self._posts_text.setMinimumHeight(300)
        ctext.addWidget(self._posts_text)
        lay.addStretch(1)

        self._posts_active_file = None
        self._posts_event_map = {}
        self._posts_series.currentTextChanged.connect(self._on_posts_series_change)
        self._posts_num.textChanged.connect(self._update_posts_name)
        self._posts_next_link.textChanged.connect(self._save_settings)
        self._posts_vods.textChanged.connect(self._save_settings)
        self._posts_has_next.toggled.connect(self._save_settings)
        self._refresh_posts_events()

    def _update_posts_next_state(self):
        en = self._posts_has_next.isChecked()
        self._posts_date.setEnabled(en)
        self._posts_next_link.setEnabled(en)

    def _refresh_posts_events(self):
        events = load_thumbnail_events()
        self._posts_event_map = {name: tmpl for name, tmpl in events}
        names = [name for name, _ in events]
        for entry in self._custom_events:
            label = entry.get("label", "")
            name_tmpl = entry.get("name_template", "")
            if label and name_tmpl and label not in self._posts_event_map:
                self._posts_event_map[label] = name_tmpl
                names.append(label)
        cur = self._posts_series.currentText()
        self._posts_series.blockSignals(True)
        self._posts_series.clear()
        self._posts_series.addItems(names)
        if names:
            last = self._settings.get("last_posts_series")
            if last in names:
                self._posts_series.setCurrentText(last)
            elif cur in names:
                self._posts_series.setCurrentText(cur)
            else:
                self._posts_series.setCurrentIndex(0)
        self._posts_series.blockSignals(False)
        self._on_posts_series_change()

    def _on_posts_series_change(self):
        self._loading = True
        series = self._posts_series.currentText()
        widgets = self._fetch_widgets.get(series)
        if widgets:
            self._posts_num.setText(widgets["num"].text())
        else:
            custom = next((e for e in self._custom_events if e.get("label") == series), None)
            if custom:
                self._posts_num.setText(custom.get("current_num", ""))
            else:
                saved = self._settings.get("last_event_nums", {}).get(series)
                if saved:
                    self._posts_num.setText(saved)
        saved_cfg = self._settings.get("posts_cfg", {}).get(series, {})
        saved_date = saved_cfg.get("next_date", "")
        if saved_date:
            qd = QtCore.QDate.fromString(saved_date, "yyyy-MM-dd")
            if qd.isValid():
                self._posts_date.setDate(qd)
        default_link = next((c.get("tweet_link", "") for c in FETCH_EVENTS if c["label"] == series), "")
        self._posts_next_link.setText(saved_cfg.get("next_link", default_link))
        self._posts_vods.setText(saved_cfg.get("vods", ""))
        self._posts_has_next.setChecked(saved_cfg.get("has_next", True))
        self._update_posts_next_state()
        self._loading = False
        self._update_posts_name()
        self._save_settings()

    def _update_posts_name(self):
        template = self._posts_event_map.get(self._posts_series.currentText(), "{n}")
        self._posts_event_name.setText(template.format(n=self._posts_num.text().strip()))
        self._posts_load_file()

    def _posts_load_file(self):
        event_name = self._posts_event_name.text().strip()
        if not event_name:
            return
        folder = ROOT / "Results_Posts"
        for platform in ("twitter", "discord"):
            path = folder / f"{event_name} {platform.capitalize()} Post.txt"
            if path.exists():
                self._posts_active_file = path
                self._posts_text.setPlainText(path.read_text(encoding="utf-8").rstrip())
                return
        self._posts_active_file = None
        self._posts_text.clear()

    def _run_fetch_post(self, platform: str):
        series = self._posts_series.currentText()
        n = self._posts_num.text().strip()
        event_name = self._posts_event_name.text().strip()
        if not event_name:
            self._log("[Error: no event selected]\n")
            return
        cfg = next((c for c in FETCH_EVENTS if c["label"] == series), None)
        if cfg:
            slug = cfg["slug_template"].format(n=n)
        else:
            custom = next((e for e in self._custom_events if e.get("label") == series), None)
            if not custom:
                self._log("[Error: no slug found for this event series]\n")
                return
            slug = custom["slug_template"].replace("{n}", n)
        out_path = ROOT / "Results_Posts" / f"{event_name} {platform.capitalize()} Post.txt"
        self._posts_active_file = out_path
        cmd = [PYTHON, str(ROOT / "Python_Scripts" / "fetch_results_tweet.py"),
               slug, "--name", event_name, "--platform", platform, "--out", str(out_path)]
        if self._posts_has_next.isChecked():
            next_link = self._posts_next_link.text().strip()
            if next_link:
                cmd += ["--link", next_link]
            next_date = _ordinal_date(self._posts_date.date().toPython())
            if next_date:
                cmd += ["--next", next_date]
        vods = self._posts_vods.text().strip()
        if vods:
            cmd += ["--vods", vods]

        def _done():
            if out_path.exists():
                self._posts_text.setPlainText(out_path.read_text(encoding="utf-8").rstrip())
        self._run(cmd, on_done=_done)

    def _save_post_file(self):
        if not self._posts_active_file:
            event_name = self._posts_event_name.text().strip()
            if not event_name:
                self._log("[Error: no event selected]\n")
                return
            self._posts_active_file = ROOT / "Results_Posts" / f"{event_name} Post.txt"
        self._posts_active_file.parent.mkdir(parents=True, exist_ok=True)
        self._posts_active_file.write_text(self._posts_text.toPlainText() + "\n", encoding="utf-8")
        self._log(f"[Saved {self._posts_active_file.name}]\n")

    def _copy_post_text(self):
        content = self._posts_text.toPlainText()
        if content.strip():
            QtWidgets.QApplication.clipboard().setText(content)
            self._log("[Copied post to clipboard]\n")
        else:
            self._log("[Nothing to copy — fetch a post first]\n")

    # ================================================================== #
    #  Tab: Character Renders                                           #
    # ================================================================== #
    def _build_renders_tab(self):
        tab = QtWidgets.QWidget()
        outer = QtWidgets.QVBoxLayout(tab)
        outer.setContentsMargins(12, 12, 12, 12)

        box = QtWidgets.QGroupBox("Character Renders")
        v = QtWidgets.QVBoxLayout(box)
        v.addWidget(_muted("Open the full character render folder in File Explorer."))
        open_full = QtWidgets.QPushButton("Open Full Renders")
        open_full.setMaximumWidth(220)
        open_full.clicked.connect(
            lambda: self._open_dir(FULL_RENDERS_DIR, "Full Renders"))
        v.addWidget(open_full)
        outer.addWidget(box)
        outer.addStretch(1)
        self.tabs.addTab(tab, "Character Renders")

    def _open_dir(self, folder, label: str):
        if not folder.is_dir():
            self._log(f"[Error: {label} folder not found: {folder}]\n")
            return
        try:
            os.startfile(str(folder))
        except Exception as exc:
            self._log(f"[Error opening folder: {exc}]\n")

    # ================================================================== #
    #  Tab: Player Database                                             #
    # ================================================================== #
    def _build_player_db_tab(self):
        tab = QtWidgets.QWidget()
        outer = QtWidgets.QHBoxLayout(tab)
        outer.setContentsMargins(12, 12, 12, 12)

        self._db_header: list[str] = []
        self._db_players: dict[str, list[tuple[str, str]]] = {}
        self._db_selected_player: str | None = None
        self._db_selected_char_idx: int | None = None
        self._char_suggestions = get_characters_from_renders()

        splitter = QtWidgets.QSplitter(Qt.Orientation.Horizontal)
        outer.addWidget(splitter)

        left = QtWidgets.QWidget()
        lv = QtWidgets.QVBoxLayout(left)
        lv.setContentsMargins(0, 0, 0, 0)
        hl = QtWidgets.QLabel("Players")
        hl.setObjectName("heading")
        lv.addWidget(hl)
        self._player_search = QtWidgets.QLineEdit()
        self._player_search.setPlaceholderText("Search players...")
        self._search_timer = QtCore.QTimer(self)
        self._search_timer.setSingleShot(True)
        self._search_timer.setInterval(200)
        self._search_timer.timeout.connect(self._refresh_player_list)
        self._player_search.textChanged.connect(lambda: self._search_timer.start())
        lv.addWidget(self._player_search)
        self._player_list = QtWidgets.QListWidget()
        self._player_list.currentItemChanged.connect(self._on_player_select)
        lv.addWidget(self._player_list)
        np_row = QtWidgets.QHBoxLayout()
        np_row.addWidget(QtWidgets.QLabel("Name:"))
        self._new_player = QtWidgets.QLineEdit()
        self._new_player.setPlaceholderText("Player name...")
        self._new_player.returnPressed.connect(self._confirm_add_player)
        np_row.addWidget(self._new_player)
        lv.addLayout(np_row)
        pb_row = QtWidgets.QHBoxLayout()
        addb = QtWidgets.QPushButton("+ Add")
        addb.clicked.connect(self._confirm_add_player)
        pb_row.addWidget(addb)
        remb = QtWidgets.QPushButton("- Remove")
        remb.clicked.connect(self._remove_player)
        pb_row.addWidget(remb)
        lv.addLayout(pb_row)
        splitter.addWidget(left)

        right = QtWidgets.QWidget()
        rv = QtWidgets.QVBoxLayout(right)
        rv.setContentsMargins(8, 0, 0, 0)
        self._editing_label = QtWidgets.QLabel("Select a player")
        self._editing_label.setObjectName("heading")
        rv.addWidget(self._editing_label)

        self._char_tree = QtWidgets.QTreeWidget()
        self._char_tree.setColumnCount(2)
        self._char_tree.setHeaderLabels(["Character", "Alt #"])
        self._char_tree.setColumnWidth(0, 180)
        self._char_tree.setRootIsDecorated(False)
        self._char_tree.currentItemChanged.connect(self._on_char_tree_select)
        rv.addWidget(self._char_tree)

        tb = QtWidgets.QHBoxLayout()
        eb = QtWidgets.QPushButton("Edit Selected")
        eb.clicked.connect(self._edit_char_entry)
        tb.addWidget(eb)
        rmb = QtWidgets.QPushButton("Remove Selected")
        rmb.clicked.connect(self._remove_char_entry)
        tb.addWidget(rmb)
        tb.addStretch(1)
        up = QtWidgets.QPushButton("Move Up")
        up.clicked.connect(lambda: self._move_char_entry(-1))
        tb.addWidget(up)
        dn = QtWidgets.QPushButton("Move Down")
        dn.clicked.connect(lambda: self._move_char_entry(1))
        tb.addWidget(dn)
        rv.addLayout(tb)

        sep = QtWidgets.QFrame()
        sep.setFrameShape(QtWidgets.QFrame.Shape.HLine)
        sep.setStyleSheet(f"color: {_BG3};")
        rv.addWidget(sep)

        ael = QtWidgets.QLabel("Add / Edit Entry")
        ael.setStyleSheet("font-weight: 600;")
        rv.addWidget(ael)

        form_section = QtWidgets.QHBoxLayout()
        form_left = QtWidgets.QVBoxLayout()
        form_row = QtWidgets.QHBoxLayout()
        form_row.addWidget(QtWidgets.QLabel("Character:"))
        self._form_char = QtWidgets.QComboBox()
        self._form_char.setEditable(True)
        self._form_char.setMinimumWidth(200)
        self._form_char.addItems([""] + self._char_suggestions)
        self._form_char.currentTextChanged.connect(self._on_form_char_change)
        form_row.addWidget(self._form_char)
        form_row.addSpacing(12)
        form_row.addWidget(QtWidgets.QLabel("Alt #:"))
        self._form_alt = QtWidgets.QComboBox()
        self._form_alt.setMinimumWidth(70)
        self._form_alt.currentTextChanged.connect(self._on_form_alt_change)
        form_row.addWidget(self._form_alt)
        form_left.addLayout(form_row)
        fb = QtWidgets.QHBoxLayout()
        self._form_add_btn = QtWidgets.QPushButton("Add Entry")
        self._form_add_btn.clicked.connect(self._add_char_entry)
        fb.addWidget(self._form_add_btn)
        self._form_edit_btn = QtWidgets.QPushButton("Update Entry")
        self._form_edit_btn.setEnabled(False)
        self._form_edit_btn.clicked.connect(self._update_char_entry)
        fb.addWidget(self._form_edit_btn)
        clf = QtWidgets.QPushButton("Clear Form")
        clf.clicked.connect(self._clear_form)
        fb.addWidget(clf)
        fb.addStretch(1)
        form_left.addLayout(fb)
        form_left.addStretch(1)

        self._preview_label = QtWidgets.QLabel()
        self._preview_label.setFixedSize(220, 220)
        self._preview_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._preview_label.setStyleSheet(f"background-color: {_BG3}; border-radius: 4px;")
        form_section.addWidget(self._preview_label, 0, Qt.AlignmentFlag.AlignTop)
        form_section.addSpacing(16)
        form_section.addLayout(form_left, 0)
        form_section.addStretch(1)
        rv.addLayout(form_section)

        save_row = QtWidgets.QHBoxLayout()
        sb = QtWidgets.QPushButton("Save Player Database")
        sb.setObjectName("accent")
        sb.clicked.connect(self._save_player_db)
        save_row.addWidget(sb)
        rl = QtWidgets.QPushButton("Reload from File")
        rl.clicked.connect(self._reload_player_db)
        save_row.addWidget(rl)
        save_row.addStretch(1)
        rv.addLayout(save_row)

        splitter.addWidget(right)
        splitter.setSizes([220, 760])
        self.tabs.addTab(tab, "Player Database")
        self._reload_player_db()

    def _reload_player_db(self):
        self._db_header, self._db_players = load_player_db()
        self._refresh_player_list()
        self._char_tree.clear()
        self._editing_label.setText("Select a player")
        self._db_selected_player = None

    def _refresh_player_list(self):
        query = self._player_search.text().lower()
        self._player_list.blockSignals(True)
        self._player_list.clear()
        for name in sorted(self._db_players, key=str.casefold):
            if query in name.lower():
                self._player_list.addItem(name)
        self._player_list.blockSignals(False)

    def _on_player_select(self, current, _prev=None):
        if current is None:
            return
        name = current.text()
        self._db_selected_player = name
        self._editing_label.setText(f"Editing: {name}")
        self._populate_char_tree(name)
        self._clear_form()

    def _populate_char_tree(self, name: str):
        self._char_tree.clear()
        for char, alt in self._db_players.get(name, []):
            QtWidgets.QTreeWidgetItem(self._char_tree, [char, alt or "(none)"])

    def _confirm_add_player(self):
        name = self._new_player.text().strip()
        if not name:
            return
        if name in self._db_players:
            self._log(f"[Player '{name}' already exists]\n")
            self._new_player.clear()
            return
        self._db_players[name] = []
        self._new_player.clear()
        self._player_search.clear()
        self._refresh_player_list()
        items = self._player_list.findItems(name, Qt.MatchFlag.MatchExactly)
        if items:
            self._player_list.setCurrentItem(items[0])
        self._autosave_player_db()

    def _remove_player(self):
        if not self._db_selected_player or self._db_selected_player not in self._db_players:
            return
        del self._db_players[self._db_selected_player]
        self._db_selected_player = None
        self._refresh_player_list()
        self._char_tree.clear()
        self._editing_label.setText("Select a player")
        self._autosave_player_db()

    def _on_form_char_change(self, *_):
        char = self._form_char.currentText().strip()
        alts = get_alts_for_char(char)
        self._form_alt.blockSignals(True)
        self._form_alt.clear()
        self._form_alt.addItems(alts)
        self._form_alt.blockSignals(False)
        if alts:
            self._form_alt.setCurrentIndex(0)
        self._on_form_alt_change()

    def _on_form_alt_change(self, *_):
        self._show_preview(self._form_char.currentText().strip(),
                           self._form_alt.currentText().strip())

    def _on_char_tree_select(self, current, _prev=None):
        if current is None:
            return
        char = current.text(0)
        alt = current.text(1)
        if alt == "(none)":
            alt = ""
        self._show_preview(char, alt)

    def _show_preview(self, char: str, alt: str):
        if not char or not alt:
            self._preview_label.clear()
            return
        key = f"{char} ({alt})"
        if key in self._preview_cache:
            self._preview_label.setPixmap(self._preview_cache[key])
            return
        path = RENDERS_DIR / f"{key}.png"
        if not path.exists():
            self._preview_label.clear()
            return
        pix = QtGui.QPixmap(str(path))
        if pix.isNull():
            self._preview_label.clear()
            return
        scaled = pix.scaled(self._preview_label.size(), Qt.AspectRatioMode.KeepAspectRatio,
                            Qt.TransformationMode.SmoothTransformation)
        self._preview_cache[key] = scaled
        self._preview_label.setPixmap(scaled)

    def _add_char_entry(self):
        if not self._db_selected_player:
            self._log("[Select a player first]\n")
            return
        char = self._form_char.currentText().strip()
        if not char:
            self._log("[Select a character]\n")
            return
        alt = self._form_alt.currentText().strip()
        self._db_players[self._db_selected_player].append((char, alt))
        self._populate_char_tree(self._db_selected_player)
        self._autosave_player_db()

    def _edit_char_entry(self):
        idx = self._char_tree.indexOfTopLevelItem(self._char_tree.currentItem())
        if idx < 0 or not self._db_selected_player:
            return
        chars = self._db_players[self._db_selected_player]
        if idx >= len(chars):
            return
        char, alt = chars[idx]
        self._form_char.setCurrentText(char)
        self._form_alt.setCurrentText(alt)
        self._db_selected_char_idx = idx
        self._form_add_btn.setEnabled(False)
        self._form_edit_btn.setEnabled(True)

    def _update_char_entry(self):
        if self._db_selected_char_idx is None or not self._db_selected_player:
            return
        char = self._form_char.currentText().strip()
        alt = self._form_alt.currentText().strip()
        chars = self._db_players[self._db_selected_player]
        if self._db_selected_char_idx < len(chars):
            chars[self._db_selected_char_idx] = (char, alt)
        self._populate_char_tree(self._db_selected_player)
        self._clear_form()
        self._autosave_player_db()

    def _remove_char_entry(self):
        idx = self._char_tree.indexOfTopLevelItem(self._char_tree.currentItem())
        if idx < 0 or not self._db_selected_player:
            return
        chars = self._db_players[self._db_selected_player]
        if idx < len(chars):
            chars.pop(idx)
        self._populate_char_tree(self._db_selected_player)
        self._autosave_player_db()

    def _move_char_entry(self, direction: int):
        idx = self._char_tree.indexOfTopLevelItem(self._char_tree.currentItem())
        if idx < 0 or not self._db_selected_player:
            return
        chars = self._db_players[self._db_selected_player]
        new_idx = idx + direction
        if 0 <= new_idx < len(chars):
            chars[idx], chars[new_idx] = chars[new_idx], chars[idx]
            self._populate_char_tree(self._db_selected_player)
            self._char_tree.setCurrentItem(self._char_tree.topLevelItem(new_idx))
            self._autosave_player_db()

    def _clear_form(self):
        self._form_char.setCurrentText("")
        self._form_alt.clear()
        self._form_add_btn.setEnabled(True)
        self._form_edit_btn.setEnabled(False)
        self._db_selected_char_idx = None
        self._preview_label.clear()

    def _save_player_db(self):
        try:
            save_player_db(self._db_header, self._db_players)
            self._log("[Player database saved]\n")
        except Exception as exc:
            self._log(f"[Error saving player database: {exc}]\n")

    def _autosave_player_db(self):
        try:
            save_player_db(self._db_header, self._db_players)
        except Exception as exc:
            self._log(f"[Error auto-saving player database: {exc}]\n")

    # ================================================================== #
    #  Tab: Character Database (two-column alias -> filename)           #
    # ================================================================== #
    def _build_char_db_tab(self):
        tab = QtWidgets.QWidget()
        outer = QtWidgets.QVBoxLayout(tab)
        outer.setContentsMargins(12, 12, 12, 12)

        self._cdb_headers: list[str] = []
        self._cdb_sel_idx: int | None = None

        hl = QtWidgets.QLabel("Characters")
        hl.setObjectName("heading")
        outer.addWidget(hl)
        outer.addWidget(_muted(
            "Maps an alias used in VOD names to the character's render filename "
            "(without the ' (N)' costume suffix)."))

        self._cdb_tree = QtWidgets.QTreeWidget()
        self._cdb_tree.setColumnCount(2)
        self._cdb_tree.setHeaderLabels(["Alias (in VOD names)", "Filename (in renders folder)"])
        self._cdb_tree.setColumnWidth(0, 220)
        self._cdb_tree.setRootIsDecorated(False)
        self._cdb_tree.currentItemChanged.connect(self._cdb_on_select)
        outer.addWidget(self._cdb_tree)

        form = QtWidgets.QGroupBox("Add / Edit Entry")
        fr = QtWidgets.QHBoxLayout(form)
        fr.addWidget(QtWidgets.QLabel("Alias:"))
        self._cdb_alias = QtWidgets.QLineEdit()
        self._cdb_alias.setMinimumWidth(160)
        fr.addWidget(self._cdb_alias)
        fr.addSpacing(10)
        fr.addWidget(QtWidgets.QLabel("Filename:"))
        self._cdb_filename = QtWidgets.QLineEdit()
        self._cdb_filename.setMinimumWidth(220)
        fr.addWidget(self._cdb_filename)
        fr.addStretch(1)
        outer.addWidget(form)

        br = QtWidgets.QHBoxLayout()
        self._cdb_add_btn = QtWidgets.QPushButton("Add Entry")
        self._cdb_add_btn.clicked.connect(self._cdb_add)
        br.addWidget(self._cdb_add_btn)
        self._cdb_update_btn = QtWidgets.QPushButton("Update Entry")
        self._cdb_update_btn.setEnabled(False)
        self._cdb_update_btn.clicked.connect(self._cdb_update)
        br.addWidget(self._cdb_update_btn)
        rmb = QtWidgets.QPushButton("Remove Selected")
        rmb.clicked.connect(self._cdb_remove)
        br.addWidget(rmb)
        clf = QtWidgets.QPushButton("Clear Form")
        clf.clicked.connect(self._cdb_clear_form)
        br.addWidget(clf)
        br.addStretch(1)
        outer.addLayout(br)

        sr = QtWidgets.QHBoxLayout()
        sb = QtWidgets.QPushButton("Save Character Database")
        sb.setObjectName("accent")
        sb.clicked.connect(self._cdb_save)
        sr.addWidget(sb)
        rl = QtWidgets.QPushButton("Reload from File")
        rl.clicked.connect(self._cdb_reload)
        sr.addWidget(rl)
        sr.addStretch(1)
        outer.addLayout(sr)

        self.tabs.addTab(tab, "Character Database")
        self._cdb_reload()

    def _cdb_reload(self):
        self._cdb_headers, entries = load_char_db()
        self._cdb_tree.clear()
        for alias, filename in entries:
            QtWidgets.QTreeWidgetItem(self._cdb_tree, [alias, filename])
        self._cdb_clear_form()

    def _cdb_entries(self) -> list[tuple[str, str]]:
        out = []
        for i in range(self._cdb_tree.topLevelItemCount()):
            it = self._cdb_tree.topLevelItem(i)
            out.append((it.text(0), it.text(1)))
        return out

    def _cdb_on_select(self, current, _prev=None):
        if current is None:
            return
        self._cdb_sel_idx = self._cdb_tree.indexOfTopLevelItem(current)
        self._cdb_alias.setText(current.text(0))
        self._cdb_filename.setText(current.text(1))
        self._cdb_add_btn.setEnabled(False)
        self._cdb_update_btn.setEnabled(True)

    def _cdb_add(self):
        alias = self._cdb_alias.text().strip()
        filename = self._cdb_filename.text().strip()
        if not alias or not filename:
            self._log("[Alias and filename are required]\n")
            return
        item = QtWidgets.QTreeWidgetItem(self._cdb_tree, [alias, filename])
        self._cdb_tree.setCurrentItem(item)
        self._cdb_tree.scrollToItem(item)

    def _cdb_update(self):
        if self._cdb_sel_idx is None:
            return
        alias = self._cdb_alias.text().strip()
        filename = self._cdb_filename.text().strip()
        if not alias or not filename:
            self._log("[Alias and filename are required]\n")
            return
        it = self._cdb_tree.topLevelItem(self._cdb_sel_idx)
        if it:
            it.setText(0, alias)
            it.setText(1, filename)
        self._cdb_clear_form()

    def _cdb_remove(self):
        idx = self._cdb_tree.indexOfTopLevelItem(self._cdb_tree.currentItem())
        if idx < 0:
            return
        self._cdb_tree.takeTopLevelItem(idx)
        self._cdb_clear_form()

    def _cdb_clear_form(self):
        self._cdb_alias.clear()
        self._cdb_filename.clear()
        self._cdb_sel_idx = None
        self._cdb_add_btn.setEnabled(True)
        self._cdb_update_btn.setEnabled(False)

    def _cdb_save(self):
        try:
            save_char_db(self._cdb_headers, self._cdb_entries())
            self._log("[Character database saved]\n")
        except Exception as exc:
            self._log(f"[Error saving character database: {exc}]\n")

    # ================================================================== #
    #  Tab: Update                                                      #
    # ================================================================== #
    def _build_update_tab(self):
        tab = QtWidgets.QWidget()
        outer = QtWidgets.QVBoxLayout(tab)
        outer.setContentsMargins(12, 12, 12, 12)

        box = QtWidgets.QGroupBox("Update Melee Generator")
        v = QtWidgets.QVBoxLayout(box)
        v.addWidget(_muted(
            "Check GitHub for a newer version of this generator and apply it. "
            "Only the Melee_Generator folder is updated — your player "
            "database and settings are preserved. Restart the app after updating "
            "to load the new version."))

        self._update_status = QtWidgets.QLabel("Status: not checked yet.")
        self._update_status.setObjectName("heading")
        v.addWidget(self._update_status)

        row = QtWidgets.QHBoxLayout()
        self._check_update_btn = QtWidgets.QPushButton("Check for Updates")
        self._check_update_btn.clicked.connect(self._on_check_updates)
        row.addWidget(self._check_update_btn)
        self._do_update_btn = QtWidgets.QPushButton("Update Now")
        self._do_update_btn.setObjectName("accent")
        self._do_update_btn.clicked.connect(self._on_do_update)
        row.addWidget(self._do_update_btn)
        row.addStretch(1)
        v.addLayout(row)

        outer.addWidget(box)
        outer.addStretch(1)
        self.tabs.addTab(tab, "Update")

    def _run_git(self, args: list, echo: bool = True):
        cmd = ["git"] + args
        if echo:
            self._log("> " + " ".join(cmd) + "\n")
        try:
            proc = subprocess.run(
                cmd, cwd=str(REPO_ROOT), capture_output=True,
                text=True, encoding="utf-8", errors="replace")
        except FileNotFoundError:
            self._log("[Error: git not found. Install Git for Windows to enable updates.]\n")
            return 1, ""
        out = (proc.stdout or "") + (proc.stderr or "")
        if echo and out.strip():
            self._log(out if out.endswith("\n") else out + "\n")
        return proc.returncode, (proc.stdout or "")

    def _on_check_updates(self):
        if getattr(self, "_update_running", False):
            return
        self._update_running = True
        self.update_status_signal.emit("Checking…", "busy")
        threading.Thread(target=self._check_updates_worker, daemon=True).start()

    def _on_do_update(self):
        if getattr(self, "_update_running", False):
            return
        resp = QtWidgets.QMessageBox.question(
            self, "Update Generator",
            "Update this generator to the latest version from GitHub?\n\n"
            "Your player database and settings will be preserved. "
            "Restart the app afterwards to load the new version.",
            QtWidgets.QMessageBox.StandardButton.Yes
            | QtWidgets.QMessageBox.StandardButton.No)
        if resp != QtWidgets.QMessageBox.StandardButton.Yes:
            return
        self._update_running = True
        self.update_status_signal.emit("Updating…", "busy")
        threading.Thread(target=self._apply_update_worker, daemon=True).start()

    def _check_updates_worker(self):
        try:
            if self._run_git(["rev-parse", "--is-inside-work-tree"], echo=False)[0] != 0:
                self.update_status_signal.emit(
                    "Not a git checkout — updates unavailable. "
                    "Re-clone from GitHub to enable updating.", "err")
                return
            if self._run_git(["fetch", "origin", "main"])[0] != 0:
                self.update_status_signal.emit(
                    "Could not reach GitHub. Check your internet connection.", "err")
                return
            remote = self._run_git(
                ["rev-parse", "FETCH_HEAD:" + GENERATOR_DIR], echo=False)[1].strip()
            head = self._run_git(
                ["rev-parse", "HEAD:" + GENERATOR_DIR], echo=False)[1].strip()
            marker = self._settings.get("last_update_tree", "")
            if not remote:
                self.update_status_signal.emit(
                    "Could not determine update status.", "err")
            elif remote == head or remote == marker:
                self.update_status_signal.emit("Up to date.", "ok")
            else:
                self.update_status_signal.emit(
                    "Update available! Click “Update Now” to install.", "avail")
        finally:
            self._update_running = False

    def _apply_update_worker(self):
        try:
            self._log("\n=== Updating " + GENERATOR_DIR + " ===\n")
            if self._run_git(["rev-parse", "--is-inside-work-tree"], echo=False)[0] != 0:
                self._log("[Not a git checkout — cannot update.]\n\n")
                self.update_done_signal.emit(False, "")
                return

            dirty = bool(self._run_git(
                ["status", "--porcelain", "--", GENERATOR_DIR], echo=False)[1].strip())
            stashed = False
            if dirty:
                self._log("Stashing your local changes…\n")
                stashed = self._run_git(
                    ["stash", "push", "--include-untracked",
                     "-m", "pre-update (GUI)", "--", GENERATOR_DIR])[0] == 0

            if self._run_git(["fetch", "origin", "main"])[0] != 0:
                if stashed:
                    self._run_git(["stash", "pop"])
                self.update_done_signal.emit(False, "")
                return

            ok = self._run_git(
                ["checkout", "FETCH_HEAD", "--", GENERATOR_DIR])[0] == 0

            if stashed:
                self._log("Restoring your local changes…\n")
                if self._run_git(["stash", "pop"])[0] != 0:
                    self._log("[Warning: could not auto-restore local changes due to a "
                              "conflict. Run 'git stash pop' manually to resolve.]\n")

            if ok:
                sha = self._run_git(
                    ["rev-parse", "FETCH_HEAD:" + GENERATOR_DIR], echo=False)[1].strip()
                self.update_done_signal.emit(True, sha)
            else:
                self.update_done_signal.emit(False, "")
        finally:
            self._update_running = False

    def _on_update_status(self, msg: str, level: str):
        colors = {"ok": "#3FB950", "avail": "#E08000",
                  "err": "#E5534B", "busy": _MUTED}
        self._update_status.setText("Status: " + msg)
        self._update_status.setStyleSheet(
            "font-weight: 600; font-size: 11pt; color: %s;"
            % colors.get(level, _FG))
        busy = (level == "busy")
        self._check_update_btn.setEnabled(not busy)
        self._do_update_btn.setEnabled(not busy)

    def _on_update_done(self, success: bool, sha: str):
        if success:
            if sha:
                self._settings["last_update_tree"] = sha
                self._save_settings()
            self._log("[Update complete. Restart the generator to load the new version.]\n\n")
            self.update_status_signal.emit(
                "Updated! Restart the app to load the new version.", "ok")
            box = QtWidgets.QMessageBox(self)
            box.setIcon(QtWidgets.QMessageBox.Icon.Information)
            box.setWindowTitle("Update Complete")
            box.setText("The generator was updated successfully.\n\n"
                        "Restart the app now to load the new version.")
            restart_btn = box.addButton("Restart Now",
                                        QtWidgets.QMessageBox.ButtonRole.AcceptRole)
            box.addButton("Later", QtWidgets.QMessageBox.ButtonRole.RejectRole)
            box.exec()
            if box.clickedButton() is restart_btn:
                self._restart_app()
        else:
            self._log("[Update failed. See messages above.]\n\n")
            self.update_status_signal.emit(
                "Update failed. See the console for details.", "err")

    def _restart_app(self):
        """Relaunch this app with the same interpreter/arguments, then quit."""
        self._log("[Restarting…]\n")
        QProcess.startDetached(sys.executable, sys.argv[:])
        QtWidgets.QApplication.quit()

    # ================================================================== #
    #  Process runners (QProcess; streams output to the console)        #
    # ================================================================== #
    def _run(self, cmd: list, on_done=None):
        proc = QProcess(self)
        proc.setWorkingDirectory(str(ROOT))
        proc.setProcessChannelMode(QProcess.ProcessChannelMode.MergedChannels)
        self._log("> " + " ".join(str(c) for c in cmd) + "\n")
        proc.readyReadStandardOutput.connect(lambda p=proc: self._read_proc(p))

        def _fin(code, _status, p=proc, cb=on_done):
            self._read_proc(p)
            self._log(f"[Done — exit {code}]\n\n")
            if code == 0 and cb:
                cb()
            self._procs.discard(p)
        proc.finished.connect(_fin)
        proc.errorOccurred.connect(
            lambda _e, p=proc: self._log(f"[Error: {p.errorString()}]\n\n"))
        self._procs.add(proc)
        proc.start(str(cmd[0]), [str(c) for c in cmd[1:]])

    def _read_proc(self, proc: QProcess):
        data = bytes(proc.readAllStandardOutput()).decode("utf-8", "replace")
        if data:
            self._log(data)

    # ------------------------------------------------------------------ #
    #  Console                                                           #
    # ------------------------------------------------------------------ #
    def _log(self, text: str):
        self.log_signal.emit(text)

    def _append_console(self, text: str):
        self.console.moveCursor(QtGui.QTextCursor.MoveOperation.End)
        self.console.insertPlainText(text)
        self.console.moveCursor(QtGui.QTextCursor.MoveOperation.End)

    def _clear_console(self):
        self.console.clear()


def main():
    app = QtWidgets.QApplication(sys.argv)
    app.setStyle("Fusion")
    app.setStyleSheet(STYLESHEET)
    win = MeleeWindow()
    win.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
