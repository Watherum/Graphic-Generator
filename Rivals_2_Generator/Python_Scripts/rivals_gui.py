#!/usr/bin/env python3
"""GUI launcher for the Rivals_2_Generator toolset."""
import tkinter as tk
from tkinter import ttk
import os
import subprocess
import threading
import sys
import re
from pathlib import Path

try:
    from PIL import Image, ImageTk
    _PIL_AVAILABLE = True
except ImportError:
    _PIL_AVAILABLE = False

try:
    import sv_ttk
    _SV_TTK_AVAILABLE = True
except ImportError:
    _SV_TTK_AVAILABLE = False

try:
    from tkcalendar import DateEntry as _DateEntry
    _TKCALENDAR_AVAILABLE = True
except ImportError:
    _TKCALENDAR_AVAILABLE = False

import json

try:
    import populate_rivals_globals as _pg
except ImportError:
    _pg = None

ROOT = Path(__file__).parent.parent
PYTHON = sys.executable
THUMBNAIL_SCRIPT = ROOT / "Python_Scripts" / "generate_rivals_thumbnail.py"
RENDERS_DIR = ROOT / "Resources" / "Character_Renders" / "Rivals_2_Full_Renders"
PLAYER_DB_PATH = ROOT / "Resources" / "Player_database.csv"
CHAR_DB_PATH   = ROOT / "Resources" / "Character_database.csv"
SETTINGS_PATH        = ROOT / "rivals_gui_settings.json"
CUSTOM_EVENTS_PATH   = ROOT / "rivals_custom_events.json"
EVENT_CONFIGS_PATH   = ROOT / "rivals_event_configs.json"

CHARACTERS = [
    "Absa", "Armando", "Clairen", "Etalus", "Fleet", "Forsburn",
    "Galvan", "Kragg", "La Reina", "Loxodont", "Maypul", "Olympia",
    "Orcane", "Ranno", "Random", "Slade", "Wrastor", "Zetterburn",
]

CHAR_ABBREVS = {
    "Absa": "Abs", "Armando": "Arm", "Clairen": "Cla", "Etalus": "Eta",
    "Fleet": "Fle", "Forsburn": "For", "Galvan": "Gal", "Kragg": "Kra",
    "La Reina": "Lar", "Loxodont": "Lox", "Maypul": "May", "Olympia": "Oly",
    "Orcane": "Orc", "Ranno": "Ran", "Slade": "Sla", "Wrastor": "Wra",
    "Zetterburn": "Zet",
}

# sv_ttk dark palette (used for classic tk widgets that sv_ttk doesn't reach)
_BG    = "#1c1c1c"
_BG2   = "#2b2b2b"
_BG3   = "#3b3b3b"
_FG    = "#ffffff"
_MUTED = "#999999"
_SEL   = "#0078d4"
_GREEN = "#1e7a1e"

# Syntax highlighting palette (VS Code "Dark+" inspired)
_SYN_COMMENT = "#6a9955"   # green   – comment lines / <!-- -->
_SYN_KEY     = "#9cdcfe"   # l. blue – field keys / HTML attribute names
_SYN_STRING  = "#ce9178"   # orange  – quoted strings
_SYN_TAG     = "#569cd6"   # blue    – HTML tag names
_SYN_NUMBER  = "#b5cea8"   # l. green – placement row numbers


def _add_placeholder(entry: ttk.Entry, text: str, muted: str = _MUTED, normal: str = _FG) -> None:
    """Show grey hint text in an Entry when it is empty and unfocused."""
    def _show():
        if not entry.get():
            entry.config(foreground=muted)
            entry.insert(0, text)

    def _hide(_=None):
        if entry.get() == text:
            entry.delete(0, "end")
            entry.config(foreground=normal)

    def _on_focus_out(_=None):
        _show()

    entry.bind("<FocusIn>", _hide)
    entry.bind("<FocusOut>", _on_focus_out)
    _show()


def _apply_theme(root: tk.Tk) -> None:
    if _SV_TTK_AVAILABLE:
        sv_ttk.set_theme("dark")
    else:
        style = ttk.Style(root)
        style.theme_use("clam")
        style.configure(".", background=_BG2, foreground=_FG)

    # sv_ttk only themes ttk widgets; patch classic tk widgets to match
    for key, val in {
        "*Background":              _BG2,
        "*Foreground":              _FG,
        "*activeBackground":        _BG3,
        "*activeForeground":        _FG,
        "*selectBackground":        _SEL,
        "*selectForeground":        _FG,
        "*disabledForeground":      _MUTED,
        "*highlightBackground":     _BG2,
        "*highlightColor":          _SEL,
        "*highlightThickness":      "0",
        "*Font":                    ("Segoe UI", 9),
        "*Button.Relief":           "flat",
        "*Button.BorderWidth":      "0",
        "*Button.Cursor":           "hand2",
        "*Button.PadX":             "10",
        "*Button.PadY":             "5",
        "*Listbox.Background":      _BG3,
        "*Listbox.Relief":          "flat",
        "*Listbox.BorderWidth":     "0",
        "*Entry.Background":        _BG3,
        "*Entry.Foreground":        _FG,
        "*Entry.insertBackground":  _FG,
        "*Entry.Relief":            "flat",
        "*Entry.BorderWidth":       "1",
    }.items():
        root.option_add(key, val, priority=80)

    root.configure(bg=_BG, highlightthickness=0, bd=0)

    style = ttk.Style()
    style.configure("Muted.TLabel", foreground=_MUTED)
    style.configure("TLabelframe", borderwidth=0, relief="flat")
    style.configure("TLabelframe.Label", foreground=_MUTED)
    style.configure("TNotebook", borderwidth=0)
    style.configure("TNotebook.Tab", focuscolor="")


def get_skins_for_char(char_name: str) -> list[str]:
    if not RENDERS_DIR.exists():
        return []
    if char_name == "Random":
        # Random has no CSP renders; it uses placeholder files named
        # T_Ran_<Color>.png (no _CSP suffix). These share Ranno's "Ran" prefix,
        # so exclude the _CSP files to keep the two rosters from mixing.
        return sorted(
            f.stem for f in RENDERS_DIR.glob("T_Ran_*.png")
            if not f.stem.endswith("_CSP")
        )
    abbrev = CHAR_ABBREVS.get(char_name)
    if not abbrev:
        return []
    return sorted(f.stem for f in RENDERS_DIR.glob(f"T_{abbrev}_*_CSP.png"))


def skin_label(stem: str) -> str:
    """T_Abs_Default_Blue_CSP → Default Blue"""
    parts = stem.split("_", 2)
    if len(parts) < 3:
        return stem
    inner = parts[2]
    if inner.endswith("_CSP"):
        inner = inner[:-4]
    return inner.replace("_", " ")


def _ordinal_date(date) -> str:
    """Format a datetime.date as 'June 17th', 'July 1st', etc."""
    import datetime as _dt
    if not isinstance(date, _dt.date):
        return ""
    day = date.day
    suffix = "th" if 11 <= day <= 13 else {1: "st", 2: "nd", 3: "rd"}.get(day % 10, "th")
    return date.strftime(f"%B {day}{suffix}")


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
            skin = result[i + 1] if i + 1 < len(result) else ""
            if char:
                chars.append((char, skin))
        players[name] = chars
    return header_comments, players


def save_player_db(header_comments: list[str], players: dict[str, list[tuple[str, str]]]) -> None:
    lines = list(header_comments)
    for name, chars in players.items():
        parts = [name]
        for char, skin in chars:
            parts += [char, skin]
        lines.append(",".join(parts))
    PLAYER_DB_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")


def load_char_db() -> tuple[list[str], list[str]]:
    """Returns (header_lines, character_names)."""
    headers: list[str] = []
    chars: list[str] = []
    try:
        lines = CHAR_DB_PATH.read_text(encoding="utf-8").splitlines()
    except FileNotFoundError:
        return [], []
    for line in lines:
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            headers.append(line)
        else:
            chars.append(stripped)
    return headers, chars


def save_char_db(headers: list[str], chars: list[str]) -> None:
    lines = list(headers) + chars
    CHAR_DB_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")


def load_thumbnail_events() -> list[tuple[str, str]]:
    """Parse startswith() calls from the dispatcher in generate_rivals_thumbnail.py."""
    try:
        source = THUMBNAIL_SCRIPT.read_text(encoding="utf-8")
        names = re.findall(r"weekly_event\.startswith\('([^']+)'\)", source)
        return [(name, f"{name} {{n}}") for name in names]
    except Exception:
        return []

# Events that support start.gg fetching
FETCH_EVENTS = [
    {
        "label": "Immortal Fight Night",
        "slug_template": "tournament/ultimate-immortal-fight-night-{n}/event/rivals-2-singles",
        "name_template": "Immortal Fight Night {n}",
        "default_num": "274",
        "default_link": "https://start.gg/UIFN{n}",
        "top8_file": "Immortal Fight Night Top 8 HTML.txt",
        "tweet_link": "https://start.gg/UIFN",
    },
    {
        "label": "Straight Into The Abyss",
        "slug_template": "tournament/straight-into-the-abyss-{n}/event/rivals-2-singles",
        "name_template": "Straight Into The Abyss {n}",
        "default_num": "47",
        "default_link": "https://start.gg/SITA{n}",
        "top8_file": "Straight Into The Abyss Top 8 HTML.txt",
        "tweet_link": "https://start.gg/SITA",
    },
]



_OUTPUT_FOLDERS = [
    "Vod_Names",
    "Youtube_Thumbnails",
    "Top_8_Texts",
    "Results_Posts",
]


class RivalsGUI:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title("Rivals_2_Generator")
        self.root.resizable(True, True)
        for folder in _OUTPUT_FOLDERS:
            (ROOT / folder).mkdir(exist_ok=True)
        self.root.state("zoomed")

        _apply_theme(self.root)
        self._settings = self._load_settings()

        notebook = ttk.Notebook(root)

        # Pack footer and console from the bottom first so they're always visible,
        # then let the notebook fill remaining space above them.
        footer = ttk.Frame(root)
        footer.pack(side="bottom", fill="x", padx=8, pady=(4, 8))
        ttk.Button(footer, text="Clear Console", command=self._clear_console).pack(side="right")

        console_frame = ttk.LabelFrame(root, text="Console Output")
        console_frame.pack(side="bottom", fill="x", padx=0, pady=0)

        console_inner = ttk.Frame(console_frame)
        console_inner.pack(fill="both", expand=True, padx=5, pady=5)
        console_sb = ttk.Scrollbar(console_inner)
        console_sb.pack(side="right", fill="y")
        self.console = tk.Text(
            console_inner, height=10, state="disabled",
            bg=_BG, fg=_FG, insertbackground=_FG,
            font=("Consolas", 9), wrap="word",
            relief="flat", highlightthickness=0,
            yscrollcommand=console_sb.set,
        )
        self.console.pack(side="left", fill="both", expand=True)
        console_sb.config(command=self.console.yview)

        notebook.pack(fill="both", expand=True, padx=0, pady=0)

        self._build_fetch_tab(notebook)
        self._build_thumbnails_tab(notebook)
        self._build_top8_tab(notebook)
        self._build_posts_tab(notebook)
        self._build_renders_tab(notebook)
        self._build_player_db_tab(notebook)
        self._build_char_db_tab(notebook)

        def _on_tab_changed(_event=None):
            tab = notebook.tab(notebook.select(), "text")
            if tab == "Player Database":
                self._player_listbox.focus_set()
            self.console.config(height=40 if tab == "Character Renders" else 10)

        notebook.bind("<<NotebookTabChanged>>", _on_tab_changed)

    # ------------------------------------------------------------------ #
    #  Settings persistence                                               #
    # ------------------------------------------------------------------ #
    def _load_settings(self) -> dict:
        try:
            settings = json.loads(SETTINGS_PATH.read_text(encoding="utf-8"))
        except Exception:
            settings = {}
        try:
            self._custom_events: list[dict] = json.loads(CUSTOM_EVENTS_PATH.read_text(encoding="utf-8"))
        except Exception:
            self._custom_events = []
        try:
            self._event_configs: dict = json.loads(EVENT_CONFIGS_PATH.read_text(encoding="utf-8"))
        except Exception:
            self._event_configs = {}
        # StringVar references for saved custom rows (keyed by slug_template)
        self._custom_event_widgets: dict[str, dict] = {}
        return settings

    def _save_settings(self):
        series = self._posts_series.get() if hasattr(self, "_posts_series") else ""
        posts_cfg = dict(self._settings.get("posts_cfg", {}))
        if series and hasattr(self, "_posts_has_next"):
            if _TKCALENDAR_AVAILABLE and hasattr(self, "_posts_date_picker") and self._posts_date_picker:
                next_date_save = self._posts_date_picker.get_date().isoformat()
            else:
                next_date_save = self._posts_next_date.get() if hasattr(self, "_posts_next_date") else ""
            posts_cfg[series] = {
                "next_date": next_date_save,
                "next_link": self._posts_next_link.get(),
                "vods": self._posts_vods.get(),
                "has_next": self._posts_has_next.get(),
            }
        data = {
            "last_event_nums": {
                label: w["num"].get()
                for label, w in self._fetch_widgets.items()
            },
            "last_thumb_series": self._thumb_series.get(),
            "last_posts_series": series,
            "posts_cfg": posts_cfg,
        }
        self._settings = data
        SETTINGS_PATH.write_text(json.dumps(data, indent=2), encoding="utf-8")

    def _setup_scrollable_canvas(self, canvas, inner, inner_win):
        """Wire up a scrollable canvas with debounced scrollregion updates."""
        _job = [None]
        def _update_scroll():
            canvas.configure(scrollregion=canvas.bbox("all"))
            _job[0] = None
        def _on_inner_configure(e):
            if _job[0]:
                canvas.after_cancel(_job[0])
            _job[0] = canvas.after(50, _update_scroll)
        def _on_canvas_configure(e):
            canvas.itemconfigure(inner_win, width=e.width)
        inner.bind("<Configure>", _on_inner_configure)
        canvas.bind("<Configure>", _on_canvas_configure)

    # ------------------------------------------------------------------ #
    #  Tab: Fetch from start.gg                                           #
    # ------------------------------------------------------------------ #
    def _build_fetch_tab(self, notebook: ttk.Notebook):
        tab = ttk.Frame(notebook)
        notebook.add(tab, text="Fetch From Start.gg")

        # Scrollable container
        _canvas = tk.Canvas(tab, bg=_BG, highlightthickness=0)
        _vsb = ttk.Scrollbar(tab, orient="vertical", command=_canvas.yview)
        _canvas.configure(yscrollcommand=_vsb.set)
        _vsb.pack(side="right", fill="y")
        _canvas.pack(side="left", fill="both", expand=True)

        inner = ttk.Frame(_canvas)
        _inner_win = _canvas.create_window((0, 0), window=inner, anchor="nw")
        self._setup_scrollable_canvas(_canvas, inner, _inner_win)

        def _on_mousewheel(event):
            _canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")
        _canvas.bind("<Enter>", lambda e: _canvas.bind_all("<MouseWheel>", _on_mousewheel))
        _canvas.bind("<Leave>", lambda e: _canvas.unbind_all("<MouseWheel>"))

        self._fetch_widgets = {}

        for cfg in FETCH_EVENTS:
            lf = ttk.LabelFrame(inner, text=cfg["label"], padding=(8, 6))
            lf.pack(fill="x", padx=10, pady=8)

            row1 = ttk.Frame(lf)
            row1.pack(fill="x", pady=(0, 4))

            ttk.Label(row1, text="Event #:").pack(side="left")
            saved_num = self._settings.get("last_event_nums", {}).get(cfg["label"], cfg["default_num"])
            num_var = tk.StringVar(value=saved_num)
            ttk.Entry(row1, textvariable=num_var, width=6).pack(side="left", padx=(4, 16))

            ttk.Label(row1, text="Top 8 Link:").pack(side="left")
            link_var = tk.StringVar(value=cfg["default_link"].replace("{n}", saved_num))
            ttk.Entry(row1, textvariable=link_var, width=32).pack(side="left", padx=4)

            # Auto-fill link when number changes, sync to Generate/Posts tabs, and persist
            def _on_num_change(name, index, mode, nv=num_var, lv=link_var, t=cfg["default_link"], lbl=cfg["label"]):
                n = nv.get().strip()
                lv.set(t.replace("{n}", n))
                if hasattr(self, "_thumb_series") and self._thumb_series.get() == lbl:
                    self._thumb_num.set(n)
                if hasattr(self, "_posts_series") and self._posts_series.get() == lbl:
                    self._posts_num.set(n)
                self._save_settings()
            num_var.trace_add("write", _on_num_change)

            row2 = ttk.Frame(lf)
            row2.pack(fill="x")

            ttk.Button(
                row2, text="Fetch VOD Names",
                command=lambda c=cfg, nv=num_var: self._fetch_sets(c, nv.get().strip()),
            ).pack(side="left", padx=(0, 6))

            ttk.Button(
                row2, text="Fetch Top 8",
                command=lambda c=cfg, nv=num_var, lv=link_var: self._fetch_top8(
                    c, nv.get().strip(), lv.get().strip()
                ),
            ).pack(side="left")

            self._fetch_widgets[cfg["label"]] = {"num": num_var, "link": link_var}

        # Saved custom tournaments section
        self._saved_custom_lf = ttk.LabelFrame(inner, text="Saved Custom Tournaments", padding=(8, 6))
        self._saved_custom_lf.pack(fill="x", padx=10, pady=(0, 4))
        self._saved_custom_frame = ttk.Frame(self._saved_custom_lf)
        self._saved_custom_frame.pack(fill="x", expand=True)
        self._build_saved_custom_rows()

        # Add new custom tournament section
        lf_custom = ttk.LabelFrame(inner, text="Add New Custom Tournament", padding=(8, 6))
        lf_custom.pack(fill="x", padx=10, pady=(0, 8))

        row_slug = ttk.Frame(lf_custom)
        row_slug.pack(fill="x", pady=(0, 4))
        ttk.Label(row_slug, text="Slug:", width=10, anchor="w").pack(side="left")
        self._custom_slug = tk.StringVar()
        ttk.Entry(row_slug, textvariable=self._custom_slug, width=52).pack(side="left", padx=4)
        ttk.Label(row_slug, text="e.g. tournament/{event}-{n}/event/rivals-2-singles",
                  style="Muted.TLabel").pack(side="left", padx=(4, 0))

        row_name = ttk.Frame(lf_custom)
        row_name.pack(fill="x", pady=(0, 4))
        ttk.Label(row_name, text="Name:", width=10, anchor="w").pack(side="left")
        self._custom_name = tk.StringVar()
        ttk.Entry(row_name, textvariable=self._custom_name, width=36).pack(side="left", padx=4)
        ttk.Label(row_name, text="e.g. Immortal Fight Night",
                  style="Muted.TLabel").pack(side="left", padx=(4, 0))

        row_num = ttk.Frame(lf_custom)
        row_num.pack(fill="x", pady=(0, 4))
        ttk.Label(row_num, text="Event #:", width=10, anchor="w").pack(side="left")
        self._custom_num = tk.StringVar()
        ttk.Entry(row_num, textvariable=self._custom_num, width=6).pack(side="left", padx=4)

        ttk.Button(lf_custom, text="Save & Fetch VOD Names",
                   command=self._fetch_custom_sets).pack(anchor="w")

    def _fetch_custom_sets(self):
        slug_tmpl = self._custom_slug.get().strip()
        name_tmpl = self._custom_name.get().strip()
        num = self._custom_num.get().strip()
        if not slug_tmpl:
            self._log("[Error: slug is required]\n")
            return
        label = (name_tmpl or slug_tmpl).replace(" {n}", "").replace("{n}", "").strip()
        slug = slug_tmpl.replace("{n}", num)
        name = (name_tmpl or slug_tmpl).replace("{n}", num)
        out  = str(ROOT / "Vod_Names" / f"{name} Names.txt")
        entry = {
            "label": label,
            "slug_template": slug_tmpl,
            "name_template": name_tmpl or slug_tmpl,
            "top8_file": f"{label} Top 8 HTML.txt",
            "current_num": num,
            "top8_link": "",
        }
        idx = next((i for i, e in enumerate(self._custom_events) if e.get("slug_template") == slug_tmpl), None)
        if idx is not None:
            entry["top8_link"] = self._custom_events[idx].get("top8_link", "")
            self._custom_events[idx] = entry
            self._custom_event_widgets.pop(slug_tmpl, None)
        else:
            self._custom_events.append(entry)
        self._save_custom_events()
        self._build_saved_custom_rows()
        if hasattr(self, "_thumb_series_box"):
            self._refresh_thumbnail_events()
        cmd = [PYTHON, str(ROOT / "Python_Scripts" / "fetch_sets.py"), slug,
               "--name", name, "--out", out]
        self._run(cmd)

    def _fetch_saved_custom(self, entry: dict, num: str):
        slug = entry["slug_template"].replace("{n}", num)
        name = entry["name_template"].replace("{n}", num)
        out  = str(ROOT / "Vod_Names" / f"{name} Names.txt")
        cmd = [PYTHON, str(ROOT / "Python_Scripts" / "fetch_sets.py"), slug,
               "--name", name, "--out", out]
        self._run(cmd)

    def _fetch_saved_custom_top8(self, entry: dict, num: str, link: str):
        import shutil
        slug = entry["slug_template"].replace("{n}", num)
        name = entry["name_template"].replace("{n}", num)
        top8_file = entry.get("top8_file", f"{entry['label']} Top 8 HTML.txt")
        out_path = ROOT / "Top_8_Texts" / top8_file
        if not out_path.exists():
            out_path.touch()
        cmd = [PYTHON, str(ROOT / "Python_Scripts" / "fetch_startgg_top8.py"),
               slug, "--name", name, "--out", str(out_path)]
        if link:
            cmd += ["--link", link]
        def _on_done():
            try:
                shutil.copy2(out_path, ROOT / "Top_8_Texts" / "Default Top 8 HTML.txt")
            except Exception:
                pass
            self._select_top8_event(entry["label"], num)
        self._run(cmd, on_done=_on_done)

    def _schedule_custom_save(self):
        if hasattr(self, "_custom_save_job") and self._custom_save_job:
            self.root.after_cancel(self._custom_save_job)
        self._custom_save_job = self.root.after(500, self._save_custom_events)

    def _save_custom_events(self):
        self._custom_save_job = None
        CUSTOM_EVENTS_PATH.write_text(json.dumps(self._custom_events, indent=2), encoding="utf-8")

    def _delete_custom_event(self, slug_tmpl: str):
        self._custom_events = [
            e for e in self._custom_events
            if e.get("slug_template", e.get("slug")) != slug_tmpl
        ]
        self._custom_event_widgets.pop(slug_tmpl, None)
        self._save_custom_events()
        self._build_saved_custom_rows()
        if hasattr(self, "_thumb_series_box"):
            self._refresh_thumbnail_events()

    def _build_saved_custom_rows(self):
        self._saved_custom_frame.destroy()
        self._saved_custom_frame = ttk.Frame(self._saved_custom_lf)
        self._saved_custom_frame.pack(fill="x", expand=True)
        if not self._custom_events:
            ttk.Label(self._saved_custom_frame, text="No saved custom tournaments",
                      style="Muted.TLabel").pack(padx=4, pady=4)
            return
        for entry in self._custom_events:
            slug_tmpl = entry.get("slug_template", entry.get("slug", ""))
            if not slug_tmpl:
                continue
            # Create StringVars once; reuse on subsequent rebuilds to keep traces alive
            if slug_tmpl not in self._custom_event_widgets:
                num_var  = tk.StringVar(value=entry.get("current_num", ""))
                link_var = tk.StringVar(value=entry.get("top8_link", ""))
                def _on_num(*_, e=entry, nv=num_var):
                    e["current_num"] = nv.get()
                    self._schedule_custom_save()
                def _on_link(*_, e=entry, lv=link_var):
                    e["top8_link"] = lv.get()
                    self._schedule_custom_save()
                num_var.trace_add("write", _on_num)
                link_var.trace_add("write", _on_link)
                self._custom_event_widgets[slug_tmpl] = {"num": num_var, "link": link_var}
            else:
                num_var  = self._custom_event_widgets[slug_tmpl]["num"]
                link_var = self._custom_event_widgets[slug_tmpl]["link"]

            lf = ttk.LabelFrame(self._saved_custom_frame, text=entry["label"], padding=(8, 6))
            lf.pack(fill="x", padx=0, pady=(0, 4))

            row1 = ttk.Frame(lf)
            row1.pack(fill="x", pady=(0, 4))
            ttk.Label(row1, text="Event #:").pack(side="left")
            ttk.Entry(row1, textvariable=num_var, width=6).pack(side="left", padx=(4, 16))
            ttk.Label(row1, text="Top 8 Link:").pack(side="left")
            ttk.Entry(row1, textvariable=link_var, width=32).pack(side="left", padx=4)

            row2 = ttk.Frame(lf)
            row2.pack(fill="x")
            ttk.Button(row2, text="Fetch VOD Names",
                       command=lambda e=entry, nv=num_var: self._fetch_saved_custom(e, nv.get().strip())
                       ).pack(side="left", padx=(0, 6))
            ttk.Button(row2, text="Fetch Top 8",
                       command=lambda e=entry, nv=num_var, lv=link_var: self._fetch_saved_custom_top8(
                           e, nv.get().strip(), lv.get().strip())
                       ).pack(side="left", padx=(0, 6))
            ttk.Button(row2, text="Delete",
                       command=lambda s=slug_tmpl: self._delete_custom_event(s)
                       ).pack(side="left")

    def _fetch_sets(self, cfg: dict, n: str):
        name = cfg["name_template"].format(n=n)
        slug = cfg["slug_template"].format(n=n)
        out  = str(ROOT / "Vod_Names" / f"{name} Names.txt")
        self._run([
            PYTHON, str(ROOT / "Python_Scripts" / "fetch_sets.py"),
            slug, "--name", name, "--out", out,
        ])

    def _fetch_top8(self, cfg: dict, n: str, link: str):
        import shutil
        name = cfg["name_template"].format(n=n)
        slug = cfg["slug_template"].format(n=n)
        out  = ROOT / "Top_8_Texts" / cfg["top8_file"]
        def _on_done():
            try:
                shutil.copy2(out, ROOT / "Top_8_Texts" / "Default Top 8 HTML.txt")
            except Exception:
                pass
            self._select_top8_event(cfg["label"], n)
        self._run([
            PYTHON, str(ROOT / "Python_Scripts" / "fetch_startgg_top8.py"),
            slug, "--name", name, "--link", link, "--out", str(out),
        ], on_done=_on_done)

    def _select_top8_event(self, label: str, num: str):
        """Point the Top 8 tab at the given event and reload its text editor.

        Called after a start.gg Top 8 fetch completes so the freshly written
        Top_8_Texts file is shown without the user having to switch tabs/reselect.
        """
        self._top8_series.set(label)
        self._top8_num.set(str(num))
        # Series/num traces also trigger a refresh, but call explicitly so the
        # reload still happens when the values were already current (trace no-op).
        self._refresh_top8_files()

    # ------------------------------------------------------------------ #
    #  Tab: Generate Thumbnails                                           #
    # ------------------------------------------------------------------ #
    def _build_thumbnails_tab(self, notebook: ttk.Notebook):
        tab = ttk.Frame(notebook)
        notebook.add(tab, text="Generate Thumbnails")

        # Scrollable container
        _canvas = tk.Canvas(tab, bg=_BG, highlightthickness=0)
        _vsb = ttk.Scrollbar(tab, orient="vertical", command=_canvas.yview)
        _canvas.configure(yscrollcommand=_vsb.set)
        _vsb.pack(side="right", fill="y")
        _canvas.pack(side="left", fill="both", expand=True)

        inner = ttk.Frame(_canvas)
        _inner_win = _canvas.create_window((0, 0), window=inner, anchor="nw")
        self._setup_scrollable_canvas(_canvas, inner, _inner_win)

        def _on_mousewheel(event):
            _canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")
        _canvas.bind("<Enter>", lambda e: _canvas.bind_all("<MouseWheel>", _on_mousewheel))
        _canvas.bind("<Leave>", lambda e: _canvas.unbind_all("<MouseWheel>"))

        lf = ttk.LabelFrame(inner, text="Event", padding=(8, 8))
        lf.pack(fill="x", padx=10, pady=10)

        row1 = ttk.Frame(lf)
        row1.pack(fill="x", pady=(0, 6))

        ttk.Label(row1, text="Series:").pack(side="left")
        self._thumb_series = tk.StringVar()
        self._thumb_series_box = ttk.Combobox(
            row1, textvariable=self._thumb_series,
            state="readonly", width=26,
        )
        self._thumb_series_box.pack(side="left", padx=(4, 4))
        ttk.Button(row1, text="↺",
                   command=self._refresh_thumbnail_events).pack(side="left", padx=(0, 12))

        ttk.Label(row1, text="# / Suffix:").pack(side="left")
        self._thumb_num = tk.StringVar(value="274")
        ttk.Entry(row1, textvariable=self._thumb_num, width=8).pack(side="left", padx=4)

        row2 = ttk.Frame(lf)
        row2.pack(fill="x", pady=(0, 6))

        ttk.Label(row2, text="Event name:").pack(side="left")
        self._thumb_event_name = tk.StringVar()
        ttk.Entry(row2, textvariable=self._thumb_event_name, width=40).pack(side="left", padx=4)

        def _update_name(*_):
            template = self._thumb_event_map.get(self._thumb_series.get(), "{n}")
            self._thumb_event_name.set(template.format(n=self._thumb_num.get().strip()))

        def _on_series_change(*_):
            series = self._thumb_series.get()
            widgets = self._fetch_widgets.get(series)
            if widgets:
                self._thumb_num.set(widgets["num"].get())
            else:
                custom = next((e for e in self._custom_events if e.get("label") == series), None)
                if custom:
                    slug_tmpl = custom.get("slug_template", custom.get("slug", ""))
                    cw = self._custom_event_widgets.get(slug_tmpl)
                    num = cw["num"].get() if cw else custom.get("current_num", "")
                    self._thumb_num.set(num)
                else:
                    saved = self._settings.get("last_event_nums", {}).get(series)
                    if saved:
                        self._thumb_num.set(saved)
            self._save_settings()

        def _on_num_change_thumb(*_):
            self._save_settings()

        self._thumb_series.trace_add("write", _on_series_change)
        self._thumb_series.trace_add("write", _update_name)
        self._thumb_num.trace_add("write", _update_name)
        self._thumb_num.trace_add("write", _on_num_change_thumb)
        self._thumb_update_name = _update_name

        self._refresh_thumbnail_events()

        # Thumbnail Config section
        lf_cfg = self._make_collapsible_section(inner, "Thumbnail Config", collapsed=True)

        self._cfg_series_label = ttk.Label(lf_cfg, text="", style="Muted.TLabel")
        self._cfg_series_label.pack(anchor="w", pady=(0, 6))

        row_bg = ttk.Frame(lf_cfg)
        row_bg.pack(fill="x", pady=(0, 4))
        ttk.Label(row_bg, text="Background:", width=12, anchor="w").pack(side="left")
        self._cfg_background = tk.StringVar()
        ttk.Entry(row_bg, textvariable=self._cfg_background, width=40).pack(side="left", padx=4)
        ttk.Button(row_bg, text="Browse…", command=lambda: self._browse_overlay(self._cfg_background)).pack(side="left")

        row_fg = ttk.Frame(lf_cfg)
        row_fg.pack(fill="x", pady=(0, 4))
        ttk.Label(row_fg, text="Foreground:", width=12, anchor="w").pack(side="left")
        self._cfg_foreground = tk.StringVar()
        ttk.Entry(row_fg, textvariable=self._cfg_foreground, width=40).pack(side="left", padx=4)
        ttk.Button(row_fg, text="Browse…", command=lambda: self._browse_overlay(self._cfg_foreground)).pack(side="left")

        row_font = ttk.Frame(lf_cfg)
        row_font.pack(fill="x", pady=(0, 4))
        ttk.Label(row_font, text="Font:", width=12, anchor="w").pack(side="left")
        _font_files = sorted(
            f.name for f in (ROOT / "Resources" / "Fonts").glob("*")
            if f.suffix.lower() in (".ttf", ".otf")
        )
        self._cfg_font = tk.StringVar()
        ttk.Combobox(row_font, textvariable=self._cfg_font, values=_font_files,
                     state="readonly", width=30).pack(side="left", padx=4)

        row_flags = ttk.Frame(lf_cfg)
        row_flags.pack(fill="x", pady=(0, 4))
        self._cfg_glow = tk.BooleanVar()
        ttk.Checkbutton(row_flags, text="Character Glow",
                        variable=self._cfg_glow).pack(side="left", padx=(0, 20))
        self._cfg_one_char = tk.BooleanVar()
        ttk.Checkbutton(row_flags, text="One Character Per Player",
                        variable=self._cfg_one_char).pack(side="left")

        row_resize = ttk.Frame(lf_cfg)
        row_resize.pack(fill="x", pady=(0, 4))
        ttk.Label(row_resize, text="Char Scale:", width=12, anchor="w").pack(side="left")
        for _lbl, _attr in [("1-char", "_cfg_resize_1"), ("2-char", "_cfg_resize_2"), ("3-char", "_cfg_resize_3")]:
            ttk.Label(row_resize, text=_lbl).pack(side="left", padx=(8, 2))
            _var = tk.StringVar()
            setattr(self, _attr, _var)
            ttk.Entry(row_resize, textvariable=_var, width=6).pack(side="left")

        ttk.Label(lf_cfg, text="Character Positions  (x, y — normalized −1 to 1):",
                  style="Muted.TLabel").pack(anchor="w", pady=(4, 2))

        def _pos_row(label, *xy_attrs):
            row = ttk.Frame(lf_cfg)
            row.pack(fill="x", pady=1)
            ttk.Label(row, text=label, width=12, anchor="w").pack(side="left")
            for i in range(0, len(xy_attrs), 2):
                if i > 0:
                    ttk.Label(row, text="").pack(side="left", padx=6)
                xv = tk.StringVar(); setattr(self, xy_attrs[i],   xv)
                yv = tk.StringVar(); setattr(self, xy_attrs[i+1], yv)
                ttk.Label(row, text="x").pack(side="left", padx=(0, 2))
                ttk.Entry(row, textvariable=xv, width=6).pack(side="left", padx=(0, 6))
                ttk.Label(row, text="y").pack(side="left", padx=(0, 2))
                ttk.Entry(row, textvariable=yv, width=6).pack(side="left")

        _pos_row("1-char:",
                 "_cfg_shift_1_x",   "_cfg_shift_1_y")
        _pos_row("2-char:",
                 "_cfg_shift_2_1_x", "_cfg_shift_2_1_y",
                 "_cfg_shift_2_2_x", "_cfg_shift_2_2_y")
        _pos_row("3-char:",
                 "_cfg_shift_3_1_x", "_cfg_shift_3_1_y",
                 "_cfg_shift_3_2_x", "_cfg_shift_3_2_y",
                 "_cfg_shift_3_3_x", "_cfg_shift_3_3_y")

        row_sizes = ttk.Frame(lf_cfg)
        row_sizes.pack(fill="x", pady=(0, 4))
        ttk.Label(row_sizes, text="Font Sizes:", width=12, anchor="w").pack(side="left")
        for _lbl, _attr in [("P1", "_cfg_font_p1"), ("P2", "_cfg_font_p2"),
                             ("Event", "_cfg_font_event"), ("Round", "_cfg_font_round")]:
            ttk.Label(row_sizes, text=_lbl).pack(side="left", padx=(8, 2))
            _var = tk.StringVar()
            setattr(self, _attr, _var)
            ttk.Entry(row_sizes, textvariable=_var, width=5).pack(side="left")
        ttk.Label(row_sizes, text="Angle°").pack(side="left", padx=(16, 2))
        self._cfg_text_angle = tk.StringVar()
        ttk.Entry(row_sizes, textvariable=self._cfg_text_angle, width=4).pack(side="left")

        # Font colors — one picker per text element
        ttk.Label(lf_cfg, text="Font Colors  (P1, P2, Event, Round):",
                  style="Muted.TLabel").pack(anchor="w", pady=(4, 2))

        def _make_color_picker(parent, label, var_attr, btn_attr):
            ttk.Label(parent, text=label, width=7, anchor="w").pack(side="left")
            var = tk.StringVar(value="#FFFFFF")
            setattr(self, var_attr, var)
            ttk.Entry(parent, textvariable=var, width=9).pack(side="left", padx=(0, 2))
            btn = tk.Button(parent, text="  ", width=2, relief="flat",
                            bg="#FFFFFF", activebackground="#FFFFFF", cursor="hand2")
            setattr(self, btn_attr, btn)
            btn.config(command=lambda v=var, b=btn: self._pick_color(v, b))
            btn.pack(side="left", padx=(0, 16))
            def _sync(*_, v=var, b=btn):
                c = v.get().strip()
                try: b.config(bg=c, activebackground=c)
                except Exception: pass
            var.trace_add("write", _sync)

        row_colors1 = ttk.Frame(lf_cfg)
        row_colors1.pack(fill="x", pady=1)
        _make_color_picker(row_colors1, "P1:",    "_cfg_font_color1", "_cfg_color_btn1")
        _make_color_picker(row_colors1, "P2:",    "_cfg_font_color2", "_cfg_color_btn2")

        row_colors2 = ttk.Frame(lf_cfg)
        row_colors2.pack(fill="x", pady=1)
        _make_color_picker(row_colors2, "Event:", "_cfg_font_color3", "_cfg_color_btn3")
        _make_color_picker(row_colors2, "Round:", "_cfg_font_color4", "_cfg_color_btn4")

        # Text label positions
        ttk.Label(lf_cfg, text="Text Label Positions  (x, y — normalized 0 to 1):",
                  style="Muted.TLabel").pack(anchor="w", pady=(4, 2))
        _pos_row("Player 1:", "_cfg_text_p1_x", "_cfg_text_p1_y")
        _pos_row("Player 2:", "_cfg_text_p2_x", "_cfg_text_p2_y")
        _pos_row("Event:",    "_cfg_text_ev_x", "_cfg_text_ev_y")
        _pos_row("Round:",    "_cfg_text_rd_x", "_cfg_text_rd_y")

        # Character window and offsets
        row_charwin = ttk.Frame(lf_cfg)
        row_charwin.pack(fill="x", pady=(4, 2))
        ttk.Label(row_charwin, text="Char Window:", width=12, anchor="w").pack(side="left")
        ttk.Label(row_charwin, text="w").pack(side="left", padx=(0, 2))
        self._cfg_char_win_w = tk.StringVar()
        ttk.Entry(row_charwin, textvariable=self._cfg_char_win_w, width=6).pack(side="left", padx=(0, 8))
        ttk.Label(row_charwin, text="h").pack(side="left", padx=(0, 2))
        self._cfg_char_win_h = tk.StringVar()
        ttk.Entry(row_charwin, textvariable=self._cfg_char_win_h, width=6).pack(side="left")

        ttk.Label(lf_cfg, text="Character Offsets  (x, y — normalized):",
                  style="Muted.TLabel").pack(anchor="w", pady=(4, 2))
        _pos_row("P1 Offset:", "_cfg_offset1_x", "_cfg_offset1_y")
        _pos_row("P2 Offset:", "_cfg_offset2_x", "_cfg_offset2_y")

        # Event/Round text options
        row_er = ttk.Frame(lf_cfg)
        row_er.pack(fill="x", pady=(4, 2))
        self._cfg_single_text = tk.BooleanVar()
        ttk.Checkbutton(row_er, text="Single Text Block",
                        variable=self._cfg_single_text).pack(side="left", padx=(0, 20))
        ttk.Label(row_er, text="Separator:").pack(side="left")
        self._cfg_text_split = tk.StringVar()
        ttk.Entry(row_er, textvariable=self._cfg_text_split, width=10).pack(side="left", padx=4)
        ttk.Label(lf_cfg,
                  text="Single Text Block: renders the event name and round as one combined label.\n"
                       "Separator: the string placed between them, e.g. \" — \" → \"Immortal Fight Night 274 — Grand Finals\".",
                  style="Muted.TLabel", wraplength=560, justify="left").pack(anchor="w", pady=(2, 4))

        row_cfg_btns = ttk.Frame(lf_cfg)
        row_cfg_btns.pack(fill="x", pady=(4, 0))
        ttk.Button(row_cfg_btns, text="Save Config",
                   command=self._save_thumbnail_config).pack(side="left", padx=(0, 6))
        ttk.Button(row_cfg_btns, text="Clear Config",
                   command=self._clear_thumbnail_config).pack(side="left")

        self._thumb_series.trace_add("write", lambda *_: self._load_config_into_form(self._thumb_series.get()))
        self._load_config_into_form(self._thumb_series.get())

        row_gen = ttk.Frame(inner)
        row_gen.pack(padx=10, pady=8, anchor="w", fill="x")
        ttk.Button(row_gen, text="Generate Thumbnails", command=self._generate_thumbnails,
                   style="Accent.TButton").pack(side="left")
        self._open_thumb_folder_btn = ttk.Button(
            row_gen, text="Open Output Folder",
            command=self._open_thumbnail_folder, state="disabled")
        self._open_thumb_folder_btn.pack(side="left", padx=(6, 0))
        self._thumb_event_name.trace_add("write", lambda *_: self._refresh_open_folder_btn())
        self._refresh_open_folder_btn()

        # VOD Names editor
        lf_vod = self._make_collapsible_section(inner, "VOD Names")

        row_vod = ttk.Frame(lf_vod)
        row_vod.pack(fill="x", pady=(0, 6))
        ttk.Label(row_vod, text="File:").pack(side="left")
        self._vod_file_var = tk.StringVar()
        self._vod_file_box = ttk.Combobox(row_vod, textvariable=self._vod_file_var,
                                           state="readonly", width=44)
        self._vod_file_box.pack(side="left", padx=4)
        ttk.Button(row_vod, text="↺", command=self._refresh_vod_files).pack(side="left")

        vod_list_frame = ttk.Frame(lf_vod)
        vod_list_frame.pack(fill="both", expand=True)
        vod_vsb = ttk.Scrollbar(vod_list_frame)
        vod_vsb.pack(side="right", fill="y")
        self._vod_canvas = tk.Canvas(vod_list_frame, bg=_BG, highlightthickness=0, height=330)
        self._vod_canvas.pack(fill="both", expand=True)
        self._vod_canvas.configure(yscrollcommand=vod_vsb.set)
        vod_vsb.config(command=self._vod_canvas.yview)

        self._vod_row_frame = tk.Frame(self._vod_canvas, bg=_BG)
        _vod_win = self._vod_canvas.create_window((0, 0), window=self._vod_row_frame, anchor="nw")
        self._setup_scrollable_canvas(self._vod_canvas, self._vod_row_frame, _vod_win)
        self._vod_canvas.bind("<MouseWheel>",
            lambda e: self._vod_canvas.yview_scroll(int(-1 * (e.delta / 120)), "units"))

        self._vod_rows = []

        vod_grip = tk.Frame(lf_vod, height=7, bg=_BG3, cursor="sb_v_double_arrow")
        vod_grip.pack(fill="x", pady=(2, 0))
        tk.Frame(vod_grip, height=2, bg=_FG).place(relx=0.5, rely=0.5, relwidth=0.08, anchor="center")
        _vg = {"y": 0, "h": 0}
        def _vg_start(e): _vg["y"] = e.y_root; _vg["h"] = self._vod_canvas.winfo_height()
        def _vg_drag(e): self._vod_canvas.config(height=max(80, _vg["h"] + e.y_root - _vg["y"]))
        vod_grip.bind("<Button-1>", _vg_start)
        vod_grip.bind("<B1-Motion>", _vg_drag)

        vod_btn_row = ttk.Frame(lf_vod)
        vod_btn_row.pack(fill="x", pady=(6, 0))
        ttk.Button(vod_btn_row, text="Save", command=self._save_vod_file).pack(side="left")
        ttk.Button(vod_btn_row, text="Add Row", command=self._vod_add_new_row).pack(side="left", padx=(6, 0))
        self._vod_delete_btn = ttk.Button(vod_btn_row, text="Delete Marked",
                                           command=self._vod_delete_marked, state="disabled")
        self._vod_delete_btn.pack(side="left", padx=(6, 0))
        ttk.Button(vod_btn_row, text="Check All",
                   command=lambda: self._vod_set_all(True)).pack(side="left", padx=(6, 0))
        ttk.Button(vod_btn_row, text="Uncheck All",
                   command=lambda: self._vod_set_all(False)).pack(side="left", padx=(6, 0))

        self._vod_file_var.trace_add("write", lambda *_: self._load_vod_file())
        self._thumb_series.trace_add("write", lambda *_: self._refresh_vod_files())
        self._refresh_vod_files()

    def _refresh_vod_files(self):
        vod_dir = ROOT / "Vod_Names"
        series = self._thumb_series.get()
        files = []
        if vod_dir.exists():
            for f in vod_dir.glob("*.txt"):
                if not series or f.name.startswith(series):
                    files.append(f)

        def _sort_key(p):
            nums = re.findall(r'\d+', p.stem)
            return (-int(nums[-1]) if nums else 0, p.stem)

        files.sort(key=_sort_key)
        names = [f.name for f in files]
        current = self._vod_file_var.get()
        self._vod_file_box["values"] = names
        if names:
            self._vod_file_var.set(current if current in names else names[0])
        else:
            self._vod_file_var.set("")
            self._vod_clear_rows()

    def _vod_clear_rows(self):
        if hasattr(self, "_vod_load_job") and self._vod_load_job:
            self.root.after_cancel(self._vod_load_job)
            self._vod_load_job = None
        for w in self._vod_row_frame.winfo_children():
            w.destroy()
        self._vod_rows.clear()
        self._vod_update_delete_btn()

    def _vod_add_row(self, line_text: str):
        row = tk.Frame(self._vod_row_frame, bg=_BG)
        row.pack(fill="x")

        check_var = tk.IntVar(value=0)
        text_var = tk.StringVar(value=line_text)

        cb = tk.Checkbutton(row, variable=check_var,
                            bg=_BG, activebackground=_BG, selectcolor=_BG2,
                            relief="flat", bd=0, cursor="hand2")
        cb.pack(side="left", padx=(4, 0))

        copy_btn = ttk.Button(row, text="⎘", width=2,
                              command=lambda v=text_var: self._vod_copy_text(v.get()))
        copy_btn.pack(side="left", padx=(2, 2))

        del_btn = ttk.Button(row, text="✕", width=2,
                             command=lambda v=text_var: self._vod_delete_row(v))
        del_btn.pack(side="left", padx=(0, 4))

        entry = tk.Entry(row, textvariable=text_var, bg=_BG, fg=_FG,
                         insertbackground=_FG, font=("Consolas", 9),
                         relief="flat", highlightthickness=0, bd=0)
        entry.pack(side="left", fill="x", expand=True, pady=1)

        colored = [row, cb, entry]

        def _on_check():
            color = "#1e3a5f" if check_var.get() else _BG
            for w in colored:
                w.config(bg=color)
            cb.config(activebackground=color)
            self._vod_update_delete_btn()

        cb.config(command=_on_check)

        def _wheel(e):
            self._vod_canvas.yview_scroll(int(-1 * (e.delta / 120)), "units")
        row.bind("<MouseWheel>", _wheel)
        cb.bind("<MouseWheel>", _wheel)

        self._vod_rows.append({"check_var": check_var, "text_var": text_var,
                               "row_frame": row, "recolor": _on_check, "entry": entry})

    def _vod_copy_text(self, text: str):
        self.root.clipboard_clear()
        self.root.clipboard_append(text)
        self._log(f"[Copied to clipboard: {text}]\n")

    def _vod_delete_row(self, text_var: tk.StringVar):
        row = next((r for r in self._vod_rows if r["text_var"] is text_var), None)
        if row:
            deleted = text_var.get()
            row["row_frame"].destroy()
            self._vod_rows.remove(row)
            self._vod_canvas.configure(scrollregion=self._vod_canvas.bbox("all"))
            self._vod_update_delete_btn()
            self._log(f"[Deleted row: {deleted}]\n")

    def _vod_delete_marked(self):
        to_delete = [r for r in self._vod_rows if r["check_var"].get()]
        for r in to_delete:
            r["row_frame"].destroy()
        self._vod_rows = [r for r in self._vod_rows if not r["check_var"].get()]
        self._vod_canvas.configure(scrollregion=self._vod_canvas.bbox("all"))
        self._vod_update_delete_btn()
        if to_delete:
            self._log(f"[Deleted {len(to_delete)} marked row(s)]\n")
        else:
            self._log("[No rows marked to delete]\n")

    def _vod_add_new_row(self):
        self._vod_add_row("")
        self._vod_canvas.configure(scrollregion=self._vod_canvas.bbox("all"))
        self._vod_canvas.yview_moveto(1.0)
        new_row = self._vod_rows[-1]
        new_row["entry"].focus_set()

    def _vod_update_delete_btn(self):
        btn = getattr(self, "_vod_delete_btn", None)
        if btn is None:
            return
        any_checked = any(r["check_var"].get() for r in self._vod_rows)
        btn.config(state="normal" if any_checked else "disabled")

    def _vod_set_all(self, checked: bool):
        for r in self._vod_rows:
            r["check_var"].set(1 if checked else 0)
            r["recolor"]()
        self._vod_update_delete_btn()

    def _load_vod_file(self):
        self._vod_clear_rows()
        # Cancel any in-progress batch load from a previous file selection
        if hasattr(self, "_vod_load_job") and self._vod_load_job:
            self.root.after_cancel(self._vod_load_job)
            self._vod_load_job = None

        name = self._vod_file_var.get()
        if not name:
            return
        try:
            content = (ROOT / "Vod_Names" / name).read_text(encoding="utf-8")
        except Exception:
            content = ""

        lines = [l for l in content.splitlines() if l.strip()]
        if not lines:
            return

        self._vod_loading_label = tk.Label(
            self._vod_row_frame, text=f"Loading 0 / {len(lines)}…",
            bg=_BG, fg=_MUTED, font=("Consolas", 9))
        self._vod_loading_label.pack(anchor="w", padx=6)

        self._vod_load_job = None
        self._vod_canvas.yview_moveto(0)
        self._vod_load_batch(lines, 0)

    _VOD_BATCH = 20

    def _vod_load_batch(self, lines: list, offset: int):
        batch = lines[offset:offset + self._VOD_BATCH]
        for line in batch:
            self._vod_add_row(line)

        done = offset + len(batch)
        if hasattr(self, "_vod_loading_label") and self._vod_loading_label.winfo_exists():
            if done < len(lines):
                self._vod_loading_label.config(text=f"Loading {done} / {len(lines)}…")
                self._vod_loading_label.lift()
            else:
                self._vod_loading_label.destroy()

        if done < len(lines):
            self._vod_load_job = self.root.after(0, self._vod_load_batch, lines, done)
        else:
            self._vod_load_job = None

    def _save_vod_file(self):
        name = self._vod_file_var.get()
        if not name:
            self._log("[Error: no VOD names file selected]\n")
            return
        content = "\n".join(r["text_var"].get() for r in self._vod_rows)
        (ROOT / "Vod_Names" / name).write_text(content, encoding="utf-8")
        self._log(f"[Saved {name}]\n")

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
        self._thumb_series_box["values"] = names
        if names:
            last_series = self._settings.get("last_thumb_series")
            if last_series in names:
                self._thumb_series.set(last_series)
            elif self._thumb_series.get() not in names:
                self._thumb_series.set(names[0])
        self._thumb_update_name()

    def _generate_thumbnails(self):
        event_name = self._thumb_event_name.get().strip()
        if not event_name:
            self._log("[Error: event name is empty]\n")
            return
        self._run([
            PYTHON, str(ROOT / "Python_Scripts" / "generate_rivals_thumbnail.py"),
            "-e", event_name, "-o", str(ROOT / "Vod_Names" / "missing.log"),
        ], on_done=self._refresh_open_folder_btn)

    def _refresh_open_folder_btn(self):
        """Enable the Open Output Folder button only if the folder exists."""
        btn = getattr(self, "_open_thumb_folder_btn", None)
        if btn is None:
            return
        event_name = self._thumb_event_name.get().strip()
        folder = ROOT / "Youtube_Thumbnails" / event_name
        btn.config(state="normal" if event_name and folder.is_dir() else "disabled")

    def _open_thumbnail_folder(self):
        folder = ROOT / "Youtube_Thumbnails" / self._thumb_event_name.get().strip()
        if not folder.is_dir():
            self._log(f"[Error: output folder not found: {folder}]\n")
            return
        try:
            os.startfile(str(folder))
        except Exception as exc:
            self._log(f"[Error opening folder: {exc}]\n")

    def _browse_overlay(self, path_var: tk.StringVar):
        from tkinter import filedialog
        import shutil
        path = filedialog.askopenfilename(
            title="Select overlay image",
            filetypes=[("PNG files", "*.png"), ("Image files", "*.png *.jpg *.jpeg"), ("All files", "*.*")],
        )
        if not path:
            return
        dest_dir = ROOT / "Resources" / "Overlays"
        dest_dir.mkdir(parents=True, exist_ok=True)
        dest = dest_dir / Path(path).name
        if Path(path).resolve() != dest.resolve():
            shutil.copy2(path, dest)
        path_var.set(str(Path("Resources") / "Overlays" / Path(path).name))

    def _pick_color(self, color_var: tk.StringVar, btn: tk.Button):
        from tkinter import colorchooser
        current = color_var.get().strip()
        result = colorchooser.askcolor(color=current or "#FFFFFF", title="Pick color")
        if result and result[1]:
            color_var.set(result[1])
            try:
                btn.config(bg=result[1], activebackground=result[1])
            except Exception:
                pass

    def _get_base_event_props(self, series: str) -> dict:
        if _pg is None:
            return {}
        try:
            if series.startswith('Straight Into The Abyss'):
                return _pg.setGlobalsStraightIntoTheAbyss(series)
            elif series.startswith('Immortal Fight Night'):
                return _pg.setGlobalsIFN(series)
            elif series.startswith('Super Fusion'):
                return _pg.setGlobalsSuperFusion(series)
            elif series.startswith('Twist of Fate'):
                return _pg.setGlobalsTwistOfFate(series)
            elif series.startswith('Clip It'):
                return _pg.setGlobalsClipIt(series)
            elif series.startswith('CR Clash'):
                return _pg.setGlobalsCRClash(series)
            elif series.startswith('CR Arcadian'):
                return _pg.setGlobalsCRArcadian(series)
            elif series.startswith('Quarantainment'):
                return _pg.setGlobalsQuarantainment(series)
            else:
                return _pg.set_default_properties(series)
        except Exception:
            return {}

    def _load_config_into_form(self, series: str):
        self._cfg_series_label.config(text=f"Editing: {series}" if series else "No series selected")
        saved = self._event_configs.get(series, {})
        base  = self._get_base_event_props(series)
        # Saved config overrides base defaults; base fills in anything not yet saved
        cfg = {**base, **saved}
        self._cfg_background.set(cfg.get("background_file", ""))
        self._cfg_foreground.set(cfg.get("foreground_file", ""))
        font_path = cfg.get("font_location", "")
        self._cfg_font.set(Path(font_path).name if font_path else "")
        self._cfg_glow.set(bool(cfg.get("char_glow_bool", False)))
        self._cfg_one_char.set(bool(cfg.get("one_char_flag", False)))
        self._cfg_resize_1.set(str(cfg["resize_1"]) if "resize_1" in cfg else "")
        self._cfg_resize_2.set(str(cfg["resize_2"]) if "resize_2" in cfg else "")
        self._cfg_resize_3.set(str(cfg["resize_3"]) if "resize_3" in cfg else "")

        def _load_shift(x_attr, y_attr, key):
            val = cfg.get(key)
            if val is not None:
                getattr(self, x_attr).set(str(val[0]))
                getattr(self, y_attr).set(str(val[1]))
            else:
                getattr(self, x_attr).set("")
                getattr(self, y_attr).set("")

        _load_shift("_cfg_shift_1_x",   "_cfg_shift_1_y",   "center_shift_1")
        _load_shift("_cfg_shift_2_1_x", "_cfg_shift_2_1_y", "center_shift_2_1")
        _load_shift("_cfg_shift_2_2_x", "_cfg_shift_2_2_y", "center_shift_2_2")
        _load_shift("_cfg_shift_3_1_x", "_cfg_shift_3_1_y", "center_shift_3_1")
        _load_shift("_cfg_shift_3_2_x", "_cfg_shift_3_2_y", "center_shift_3_2")
        _load_shift("_cfg_shift_3_3_x", "_cfg_shift_3_3_y", "center_shift_3_3")

        self._cfg_font_p1.set(str(cfg["font_player1_size"]) if "font_player1_size" in cfg else "")
        self._cfg_font_p2.set(str(cfg["font_player2_size"]) if "font_player2_size" in cfg else "")
        self._cfg_font_event.set(str(cfg["font_event_size"]) if "font_event_size" in cfg else "")
        self._cfg_font_round.set(str(cfg["font_round_size"]) if "font_round_size" in cfg else "")
        self._cfg_text_angle.set(str(cfg["text_angle"]) if "text_angle" in cfg else "")
        for attr, btn_attr, key in [
            ("_cfg_font_color1", "_cfg_color_btn1", "font_color1"),
            ("_cfg_font_color2", "_cfg_color_btn2", "font_color2"),
            ("_cfg_font_color3", "_cfg_color_btn3", "font_color3"),
            ("_cfg_font_color4", "_cfg_color_btn4", "font_color4"),
        ]:
            c = cfg.get(key, "#FFFFFF")
            getattr(self, attr).set(c)
            try:
                getattr(self, btn_attr).config(bg=c, activebackground=c)
            except Exception:
                pass

        _load_shift("_cfg_text_p1_x", "_cfg_text_p1_y", "text_player1")
        _load_shift("_cfg_text_p2_x", "_cfg_text_p2_y", "text_player2")
        _load_shift("_cfg_text_ev_x", "_cfg_text_ev_y", "text_event")
        _load_shift("_cfg_text_rd_x", "_cfg_text_rd_y", "text_round")

        char_win = cfg.get("char_window")
        if isinstance(char_win, (list, tuple)) and len(char_win) >= 2:
            self._cfg_char_win_w.set(str(char_win[0]))
            self._cfg_char_win_h.set(str(char_win[1]))
        else:
            self._cfg_char_win_w.set("")
            self._cfg_char_win_h.set("")

        _load_shift("_cfg_offset1_x", "_cfg_offset1_y", "char_offset1")
        _load_shift("_cfg_offset2_x", "_cfg_offset2_y", "char_offset2")

        self._cfg_single_text.set(bool(cfg.get("event_round_single_text", False)))
        self._cfg_text_split.set(cfg.get("event_round_text_split", ""))

    def _save_thumbnail_config(self):
        series = self._thumb_series.get().strip()
        if not series:
            self._log("[Error: no series selected]\n")
            return
        cfg: dict = {}
        bg = self._cfg_background.get().strip()
        fg = self._cfg_foreground.get().strip()
        font_name = self._cfg_font.get().strip()
        if bg:
            cfg["background_file"] = bg
        if fg:
            cfg["foreground_file"] = fg
        if font_name:
            cfg["font_location"] = str(Path("Resources") / "Fonts" / font_name)
        cfg["char_glow_bool"] = self._cfg_glow.get()
        cfg["one_char_flag"]  = self._cfg_one_char.get()
        for attr, key in [
            ("_cfg_resize_1", "resize_1"),
            ("_cfg_resize_2", "resize_2"),
            ("_cfg_resize_3", "resize_3"),
        ]:
            val = getattr(self, attr).get().strip()
            if val:
                try:
                    cfg[key] = float(val)
                except ValueError:
                    pass

        def _save_shift(x_attr, y_attr, key):
            x = getattr(self, x_attr).get().strip()
            y = getattr(self, y_attr).get().strip()
            if x and y:
                try:
                    cfg[key] = [float(x), float(y)]
                except ValueError:
                    pass

        _save_shift("_cfg_shift_1_x",   "_cfg_shift_1_y",   "center_shift_1")
        _save_shift("_cfg_shift_2_1_x", "_cfg_shift_2_1_y", "center_shift_2_1")
        _save_shift("_cfg_shift_2_2_x", "_cfg_shift_2_2_y", "center_shift_2_2")
        _save_shift("_cfg_shift_3_1_x", "_cfg_shift_3_1_y", "center_shift_3_1")
        _save_shift("_cfg_shift_3_2_x", "_cfg_shift_3_2_y", "center_shift_3_2")
        _save_shift("_cfg_shift_3_3_x", "_cfg_shift_3_3_y", "center_shift_3_3")

        for attr, key in [
            ("_cfg_font_p1",    "font_player1_size"),
            ("_cfg_font_p2",    "font_player2_size"),
            ("_cfg_font_event", "font_event_size"),
            ("_cfg_font_round", "font_round_size"),
        ]:
            val = getattr(self, attr).get().strip()
            if val:
                try:
                    cfg[key] = int(val)
                except ValueError:
                    pass
        angle = self._cfg_text_angle.get().strip()
        if angle:
            try:
                cfg["text_angle"] = int(angle)
            except ValueError:
                pass
        for attr, key in [
            ("_cfg_font_color1", "font_color1"),
            ("_cfg_font_color2", "font_color2"),
            ("_cfg_font_color3", "font_color3"),
            ("_cfg_font_color4", "font_color4"),
        ]:
            c = getattr(self, attr).get().strip()
            if c:
                cfg[key] = c

        _save_shift("_cfg_text_p1_x", "_cfg_text_p1_y", "text_player1")
        _save_shift("_cfg_text_p2_x", "_cfg_text_p2_y", "text_player2")
        _save_shift("_cfg_text_ev_x", "_cfg_text_ev_y", "text_event")
        _save_shift("_cfg_text_rd_x", "_cfg_text_rd_y", "text_round")

        w = self._cfg_char_win_w.get().strip()
        h = self._cfg_char_win_h.get().strip()
        if w and h:
            try:
                cfg["char_window"] = [float(w), float(h)]
            except ValueError:
                pass

        _save_shift("_cfg_offset1_x", "_cfg_offset1_y", "char_offset1")
        _save_shift("_cfg_offset2_x", "_cfg_offset2_y", "char_offset2")

        cfg["event_round_single_text"] = self._cfg_single_text.get()
        split = self._cfg_text_split.get()
        if split:
            cfg["event_round_text_split"] = split

        self._event_configs[series] = cfg
        self._save_event_configs()
        self._log(f"[Config saved for \"{series}\"]\n")

    def _clear_thumbnail_config(self):
        series = self._thumb_series.get().strip()
        if series in self._event_configs:
            del self._event_configs[series]
            self._save_event_configs()
        self._cfg_background.set("")
        self._cfg_foreground.set("")
        self._cfg_font.set("")
        self._cfg_glow.set(False)
        self._cfg_one_char.set(False)
        for attr in ("_cfg_resize_1", "_cfg_resize_2", "_cfg_resize_3",
                     "_cfg_shift_1_x",   "_cfg_shift_1_y",
                     "_cfg_shift_2_1_x", "_cfg_shift_2_1_y",
                     "_cfg_shift_2_2_x", "_cfg_shift_2_2_y",
                     "_cfg_shift_3_1_x", "_cfg_shift_3_1_y",
                     "_cfg_shift_3_2_x", "_cfg_shift_3_2_y",
                     "_cfg_shift_3_3_x", "_cfg_shift_3_3_y",
                     "_cfg_font_p1", "_cfg_font_p2", "_cfg_font_event", "_cfg_font_round",
                     "_cfg_text_angle"):
            getattr(self, attr).set("")
        for attr, btn_attr in [
            ("_cfg_font_color1", "_cfg_color_btn1"),
            ("_cfg_font_color2", "_cfg_color_btn2"),
            ("_cfg_font_color3", "_cfg_color_btn3"),
            ("_cfg_font_color4", "_cfg_color_btn4"),
        ]:
            getattr(self, attr).set("#FFFFFF")
            try:
                getattr(self, btn_attr).config(bg="#FFFFFF", activebackground="#FFFFFF")
            except Exception:
                pass
        for attr in ("_cfg_text_p1_x", "_cfg_text_p1_y",
                     "_cfg_text_p2_x", "_cfg_text_p2_y",
                     "_cfg_text_ev_x", "_cfg_text_ev_y",
                     "_cfg_text_rd_x", "_cfg_text_rd_y",
                     "_cfg_char_win_w", "_cfg_char_win_h",
                     "_cfg_offset1_x", "_cfg_offset1_y",
                     "_cfg_offset2_x", "_cfg_offset2_y",
                     "_cfg_text_split"):
            getattr(self, attr).set("")
        self._cfg_single_text.set(False)
        self._log(f"[Config cleared for \"{series}\"]\n")

    def _save_event_configs(self):
        EVENT_CONFIGS_PATH.write_text(json.dumps(self._event_configs, indent=2), encoding="utf-8")

    def _make_collapsible_section(self, parent, title, fill="x", expand=False, pady=(0, 6), collapsed=False):
        wrapper = ttk.Frame(parent)
        wrapper.pack(fill=fill if not collapsed else "x",
                     expand=expand if not collapsed else False,
                     padx=10, pady=pady)

        header = ttk.Frame(wrapper)
        header.pack(fill="x")

        btn = ttk.Button(header, text="▼" if not collapsed else "▶", width=2)
        btn.pack(side="left", padx=(0, 4))
        ttk.Label(header, text=title, style="TLabelframe.Label").pack(side="left")
        ttk.Separator(header, orient="horizontal").pack(side="left", fill="x", expand=True, padx=(8, 0))

        content = ttk.Frame(wrapper, padding=(0, 6, 0, 0))
        if not collapsed:
            content.pack(fill=fill, expand=expand)

        def _toggle():
            if content.winfo_ismapped():
                content.pack_forget()
                btn.config(text="▶")
                wrapper.pack_configure(fill="x", expand=False)
            else:
                content.pack(fill=fill, expand=expand)
                btn.config(text="▼")
                wrapper.pack_configure(fill=fill, expand=expand)

        btn.config(command=_toggle)

        return content

    def _add_resize_grip(self, parent, text_widget, min_rows=4):
        """Add a draggable grip below a Text widget so the user can resize its height.

        Dragging the grip up/down changes the widget's `height` (in rows). Used to make
        the text-editing sections scalable inside the vertically-scrolling tab, where
        `expand=True` alone can't grow a fixed-height Text widget.
        """
        grip = tk.Frame(parent, height=7, bg=_BG3, cursor="sb_v_double_arrow")
        grip.pack(fill="x", pady=(2, 0))
        # Visual affordance: a centered handle line so it reads as draggable.
        tk.Frame(grip, height=2, bg=_FG).place(relx=0.5, rely=0.5, relwidth=0.08, anchor="center")

        state = {"y": 0, "rows": 0, "line_px": 16}

        def _start(event):
            state["y"] = event.y_root
            state["rows"] = int(text_widget.cget("height"))
            try:
                import tkinter.font as tkfont
                state["line_px"] = max(1, tkfont.Font(font=text_widget.cget("font")).metrics("linespace"))
            except Exception:
                state["line_px"] = 16

        def _drag(event):
            delta_rows = (event.y_root - state["y"]) // state["line_px"]
            new_rows = max(min_rows, state["rows"] + int(delta_rows))
            if new_rows != int(text_widget.cget("height")):
                text_widget.config(height=new_rows)

        grip.bind("<Button-1>", _start)
        grip.bind("<B1-Motion>", _drag)
        return grip

    # ------------------------------------------------------------------ #
    #  Tab: Generate Top 8s                                              #
    # ------------------------------------------------------------------ #
    def _build_top8_tab(self, notebook: ttk.Notebook):
        tab = ttk.Frame(notebook)
        notebook.add(tab, text="Generate Top 8s")

        # Scrollable container
        _canvas = tk.Canvas(tab, bg=_BG, highlightthickness=0)
        _vsb = ttk.Scrollbar(tab, orient="vertical", command=_canvas.yview)
        _canvas.configure(yscrollcommand=_vsb.set)
        _vsb.pack(side="right", fill="y")
        _canvas.pack(side="left", fill="both", expand=True)

        inner = ttk.Frame(_canvas)
        _inner_win = _canvas.create_window((0, 0), window=inner, anchor="nw")
        self._setup_scrollable_canvas(_canvas, inner, _inner_win)

        def _on_mousewheel(event):
            _canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")
        _canvas.bind("<Enter>", lambda e: _canvas.bind_all("<MouseWheel>", _on_mousewheel))
        _canvas.bind("<Leave>", lambda e: _canvas.unbind_all("<MouseWheel>"))

        # Event selection
        lf = ttk.LabelFrame(inner, text="Event", padding=(8, 8))
        lf.pack(fill="x", padx=10, pady=10)

        row1 = ttk.Frame(lf)
        row1.pack(fill="x", pady=(0, 6))
        ttk.Label(row1, text="Series:").pack(side="left")
        self._top8_series = tk.StringVar()
        self._top8_series_box = ttk.Combobox(
            row1, textvariable=self._top8_series, state="readonly", width=26,
        )
        self._top8_series_box.pack(side="left", padx=(4, 4))
        ttk.Button(row1, text="↺", command=self._refresh_top8_series).pack(side="left", padx=(0, 12))
        ttk.Label(row1, text="# / Suffix:").pack(side="left")
        self._top8_num = tk.StringVar()
        ttk.Entry(row1, textvariable=self._top8_num, width=8).pack(side="left", padx=4)

        row2 = ttk.Frame(lf)
        row2.pack(fill="x")
        ttk.Label(row2, text="Event name:").pack(side="left")
        self._top8_event_name_label = ttk.Label(row2, text="", style="Muted.TLabel")
        self._top8_event_name_label.pack(side="left", padx=4)

        def _update_top8_name(*_):
            template = self._thumb_event_map.get(self._top8_series.get(), self._top8_series.get())
            name = template.format(n=self._top8_num.get().strip())
            self._top8_event_name_label.config(text=name)

        def _on_top8_event_change(*_):
            _update_top8_name()
            self._refresh_top8_files()

        self._top8_series.trace_add("write", _on_top8_event_change)
        self._top8_num.trace_add("write", _on_top8_event_change)

        # Top 8 Text editor
        lf_txt = self._make_collapsible_section(inner, "Top 8 Text Data")
        self._top8_text_path_label = ttk.Label(lf_txt, text="", style="Muted.TLabel")
        self._top8_text_path_label.pack(anchor="w", pady=(0, 4))

        txt_inner = ttk.Frame(lf_txt)
        txt_inner.pack(fill="both", expand=True)
        txt_ysb = ttk.Scrollbar(txt_inner)
        txt_ysb.pack(side="right", fill="y")
        txt_xsb = ttk.Scrollbar(txt_inner, orient="horizontal")
        txt_xsb.pack(side="bottom", fill="x")
        self._top8_text = tk.Text(
            txt_inner, height=22,
            bg=_BG, fg=_FG, insertbackground=_FG,
            font=("Consolas", 9), wrap="none",
            relief="flat", highlightthickness=0,
            yscrollcommand=txt_ysb.set,
            xscrollcommand=txt_xsb.set,
        )
        self._top8_text.pack(side="left", fill="both", expand=True)
        txt_ysb.config(command=self._top8_text.yview)
        txt_xsb.config(command=self._top8_text.xview)
        self._add_resize_grip(lf_txt, self._top8_text)
        self._setup_text_data_highlighting(self._top8_text)
        ttk.Button(lf_txt, text="Save", command=self._save_top8_text).pack(anchor="w", pady=(6, 0))

        # Top 8 HTML editor
        lf_html = self._make_collapsible_section(inner, "Top 8 HTML Result")
        row_html = ttk.Frame(lf_html)
        row_html.pack(fill="x", pady=(0, 6))
        ttk.Label(row_html, text="File:").pack(side="left")
        self._top8_html_file_var = tk.StringVar()
        self._top8_html_file_box = ttk.Combobox(
            row_html, textvariable=self._top8_html_file_var, state="readonly", width=40,
        )
        self._top8_html_file_box.pack(side="left", padx=4)
        ttk.Button(row_html, text="↺", command=self._refresh_top8_html_files).pack(side="left", padx=(0, 6))
        ttk.Button(row_html, text="Open in Browser", command=self._open_top8_html_in_browser).pack(side="left")

        # Warning packed between file row and editor; use text="" to hide visually
        self._top8_html_warning = ttk.Label(
            lf_html, text="", foreground="#E08000",
            wraplength=560, justify="left",
        )
        self._top8_html_warning.pack(anchor="w")

        ttk.Label(
            lf_html,
            text=(
                "The HTML files are designed for OBS's fixed canvas, not for interactive browser viewing. "
                "The browser preview is really just for spot-checking the data (player names, placements, etc.) "
                "rather than pixel-perfect layout review.\n\n"
                "To see it closer to actual size in the browser you can hit Ctrl + + to zoom in, or Ctrl+0 to reset. "
                "If you want a quick way to get back to ~actual size, you could also set the browser zoom to something "
                "like 150–200% depending on your monitor scaling."
            ),
            style="Muted.TLabel", wraplength=620, justify="left",
        ).pack(anchor="w", pady=(0, 6))

        self._build_default_top8_config(lf_html)

        lf_html_src = self._make_collapsible_section(lf_html, "HTML Source", collapsed=True)

        html_inner = ttk.Frame(lf_html_src)
        html_inner.pack(fill="both", expand=True)
        html_ysb = ttk.Scrollbar(html_inner)
        html_ysb.pack(side="right", fill="y")
        html_xsb = ttk.Scrollbar(html_inner, orient="horizontal")
        html_xsb.pack(side="bottom", fill="x")
        self._top8_html_text = tk.Text(
            html_inner, height=30,
            bg=_BG, fg=_FG, insertbackground=_FG,
            font=("Consolas", 9), wrap="none",
            relief="flat", highlightthickness=0,
            yscrollcommand=html_ysb.set,
            xscrollcommand=html_xsb.set,
        )
        self._top8_html_text.pack(side="left", fill="both", expand=True)
        html_ysb.config(command=self._top8_html_text.yview)
        html_xsb.config(command=self._top8_html_text.xview)
        self._add_resize_grip(lf_html_src, self._top8_html_text)
        self._setup_html_highlighting(self._top8_html_text)
        ttk.Button(lf_html_src, text="Save", command=self._save_top8_html).pack(anchor="w", pady=(6, 0))

        self._top8_html_file_var.trace_add("write", lambda *_: self._schedule_load_top8_html())

        # Populate series dropdown using the same event map as thumbnails tab
        self._refresh_top8_series()

    def _refresh_top8_series(self):
        names = list(getattr(self, "_thumb_event_map", {}).keys())
        self._top8_series_box["values"] = names
        if names and self._top8_series.get() not in names:
            self._top8_series.set(names[0])
        self._refresh_top8_files()

    def _get_top8_text_path(self) -> "Path":
        if getattr(self, "_top8_html_file_var", None) and self._top8_html_file_var.get() == "Default Top 8.html":
            return ROOT / "Top_8_Texts" / "Default Top 8 HTML.txt"
        series = self._top8_series.get()
        for cfg in FETCH_EVENTS:
            if cfg["label"] == series:
                return ROOT / "Top_8_Texts" / cfg["top8_file"]
        for entry in self._custom_events:
            if entry.get("label") == series:
                fname = entry.get("top8_file", f"{series} Top 8 HTML.txt")
                return ROOT / "Top_8_Texts" / fname
        return ROOT / "Top_8_Texts" / f"{series} Top 8 HTML.txt"

    def _refresh_top8_files(self):
        self._load_top8_text()
        self._refresh_top8_html_files()

    def _load_top8_text(self):
        path = self._get_top8_text_path()
        self._top8_text_path_label.config(text=str(path.relative_to(ROOT)) if path.is_absolute() else str(path))
        if not path.exists():
            series = self._top8_series.get()
            template = self._thumb_event_map.get(series, series)
            event_name = template.format(n=self._top8_num.get().strip())
            content = (
                "# Top 8 Graphic\n"
                "# All information is tab deliminated\n\n"
                "#Graphic Information\n"
                f"Event name:\t{event_name}\n"
                "Event link:\t\n"
                "Event entrants:\t Competitors\n"
                "Event date:\t\n\n"
                "# Placements\n"
                "# place, name, sponsor, characters\n"
                "1,,,\n2,,,\n3,,,\n4,,,\n5,,,\n5,,,\n7,,,\n7,,,"
            )
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content, encoding="utf-8")
            self._log(f"[Auto-created {path.name}]\n")
        self._top8_text.config(state="normal")
        self._top8_text.delete("1.0", "end")
        self._top8_text.insert("end", path.read_text(encoding="utf-8"))
        self._top8_text.config(state="normal")
        self._highlight_text_data(self._top8_text)

    def _save_top8_text(self):
        path = self._get_top8_text_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(self._top8_text.get("1.0", "end-1c"), encoding="utf-8")
        self._log(f"[Saved {path.name}]\n")

    def _refresh_top8_html_files(self):
        results_dir = ROOT / "Top_8_Results"
        series = self._top8_series.get()
        all_files = sorted(f.name for f in results_dir.glob("*.html")) if results_dir.exists() else []
        files = [f for f in all_files if f.startswith(series) or f == "Default Top 8.html"]
        self._top8_html_file_box["values"] = files
        if files:
            self._top8_html_warning.config(text="")
            if self._top8_html_file_var.get() not in files:
                self._top8_html_file_var.set(files[0])
            else:
                self._load_top8_html()
        else:
            self._top8_html_file_var.set("")
            self._top8_html_text.config(state="normal")
            self._top8_html_text.delete("1.0", "end")
            self._top8_html_warning.config(
                text="⚠ No Top 8 HTML file found in Top_8_Results/. "
                     "Create one by copying an existing template."
            )

    def _schedule_load_top8_html(self):
        if hasattr(self, "_top8_html_load_job") and self._top8_html_load_job:
            self.root.after_cancel(self._top8_html_load_job)
        self._top8_html_load_job = self.root.after(80, self._load_top8_html)

    def _load_top8_html(self):
        self._top8_html_load_job = None
        name = self._top8_html_file_var.get()
        if not name:
            return
        path = ROOT / "Top_8_Results" / name
        if not path.exists():
            return

        self._top8_html_text.config(state="normal")
        self._top8_html_text.delete("1.0", "end")
        self._top8_html_text.insert("end", path.read_text(encoding="utf-8"))
        self._schedule_highlight(self._top8_html_text, self._highlight_html)

        if name != getattr(self, "_d8_last_html_file", None):
            self._d8_last_html_file = name
            self._load_default_top8_config()
            self._load_top8_text()

    def _save_top8_html(self):
        name = self._top8_html_file_var.get()
        if not name:
            self._log("[Error: no HTML file selected]\n")
            return
        path = ROOT / "Top_8_Results" / name
        path.write_text(self._top8_html_text.get("1.0", "end-1c"), encoding="utf-8")
        self._log(f"[Saved {name}]\n")

    # ------------------------------------------------------------------ #
    #  Default Top 8 layout config form                                    #
    # ------------------------------------------------------------------ #
    def _build_default_top8_config(self, parent):
        import re as _re
        frame = self._make_collapsible_section(parent, "Layout Config", collapsed=True)

        self._d8_label_color   = tk.StringVar()
        self._d8_sponsor_color = tk.StringVar()
        self._d8_event = [
            {"top": tk.StringVar(), "left": tk.StringVar(), "size": tk.StringVar(), "color": tk.StringVar()}
            if i == 0 else
            {"top": tk.StringVar(), "left": tk.StringVar(), "size": tk.StringVar()}
            for i in range(4)
        ]
        self._d8_renders  = [{"top": tk.StringVar(), "left": tk.StringVar(), "height": tk.StringVar()} for _ in range(8)]
        self._d8_nums     = [{"top": tk.StringVar(), "left": tk.StringVar(), "size": tk.StringVar()} for _ in range(8)]
        self._d8_names    = [{"top": tk.StringVar(), "left": tk.StringVar(), "size": tk.StringVar()} for _ in range(8)]
        self._d8_sponsors = [{"top": tk.StringVar(), "left": tk.StringVar(), "size": tk.StringVar()} for _ in range(8)]

        def _color_btn(p, var):
            btn = tk.Button(p, text="  ", width=2, relief="flat", cursor="hand2", bg=_BG3)
            def _pick():
                from tkinter import colorchooser
                c = colorchooser.askcolor(color=var.get() or None, parent=p)
                if c and c[1]:
                    var.set(c[1])
            def _sync(*_):
                try:
                    btn.config(bg=var.get())
                except Exception:
                    pass
            btn.config(command=_pick)
            var.trace_add("write", _sync)
            return btn

        def _entry(p, var, w=6):
            return ttk.Entry(p, textvariable=var, width=w)

        # Colors
        lf_col = ttk.LabelFrame(frame, text="Colors", padding=(6, 4))
        lf_col.pack(fill="x", pady=(0, 6))
        row = ttk.Frame(lf_col)
        row.pack(anchor="w")
        ttk.Label(row, text="Label:").pack(side="left")
        _entry(row, self._d8_label_color, 8).pack(side="left", padx=(4, 2))
        _color_btn(row, self._d8_label_color).pack(side="left", padx=(0, 20))
        ttk.Label(row, text="Sponsor:").pack(side="left")
        _entry(row, self._d8_sponsor_color, 8).pack(side="left", padx=(4, 2))
        _color_btn(row, self._d8_sponsor_color).pack(side="left")

        # Event Info
        lf_evt = ttk.LabelFrame(frame, text="Event Info", padding=(6, 4))
        lf_evt.pack(fill="x", pady=(0, 6))
        hdr = ttk.Frame(lf_evt)
        hdr.pack(fill="x")
        for ci, (txt, w) in enumerate([("", 9), ("Top %", 6), ("Left %", 6), ("Size px", 7), ("Color", 9)]):
            ttk.Label(hdr, text=txt, style="Muted.TLabel", width=w).grid(row=0, column=ci, padx=2, sticky="w")
        for i, lbl in enumerate(["Name", "Link", "Entrants", "Date"]):
            r = ttk.Frame(lf_evt)
            r.pack(fill="x", pady=1)
            f = self._d8_event[i]
            ttk.Label(r, text=lbl + ":", width=9).grid(row=0, column=0, padx=2, sticky="w")
            _entry(r, f["top"]).grid(row=0, column=1, padx=2)
            _entry(r, f["left"]).grid(row=0, column=2, padx=2)
            _entry(r, f["size"], 7).grid(row=0, column=3, padx=2)
            if "color" in f:
                _entry(r, f["color"], 9).grid(row=0, column=4, padx=2)
                _color_btn(r, f["color"]).grid(row=0, column=5, padx=2)

        def _slot_section(title, vars_list, col3_lbl, key3):
            lf = ttk.LabelFrame(frame, text=title, padding=(6, 4))
            lf.pack(fill="x", pady=(0, 6))
            hdr = ttk.Frame(lf)
            hdr.pack(fill="x")
            for ci, (txt, w) in enumerate([("Place", 5), ("Top %", 6), ("Left %", 6), (col3_lbl, 7)]):
                ttk.Label(hdr, text=txt, style="Muted.TLabel", width=w).grid(row=0, column=ci, padx=3, sticky="w")
            for i, f in enumerate(vars_list):
                r = ttk.Frame(lf)
                r.pack(fill="x", pady=1)
                ttk.Label(r, text=str(i + 1), width=5).grid(row=0, column=0, padx=3, sticky="w")
                _entry(r, f["top"]).grid(row=0, column=1, padx=3)
                _entry(r, f["left"]).grid(row=0, column=2, padx=3)
                _entry(r, f[key3], 7).grid(row=0, column=3, padx=3)

        _slot_section("Character Renders", self._d8_renders,  "Height %", "height")
        _slot_section("Placement Numbers", self._d8_nums,     "Size px",  "size")
        _slot_section("Player Names",      self._d8_names,    "Size px",  "size")
        _slot_section("Sponsors",          self._d8_sponsors, "Size px",  "size")

        ttk.Button(frame, text="Apply Config", command=self._apply_default_top8_config,
                   style="Accent.TButton").pack(anchor="w", pady=(6, 0))

        self._d8_config_frame = frame

    def _load_default_top8_config(self):
        import re
        html = self._top8_html_text.get("1.0", "end-1c")

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
        self._d8_label_color.set(m.group(1) if m else "#ffffff")
        m = re.search(r'#canvas \.sponsor \{[^}]*color:\s*(#[0-9a-fA-F]+)', html, re.DOTALL)
        self._d8_sponsor_color.set(m.group(1) if m else "#FFD700")

        for i, eid in enumerate(["event-name", "event-link", "event-entrants", "event-date"]):
            s = get_style(eid)
            f = self._d8_event[i]
            f["top"].set(num_prop(s, "top"))
            f["left"].set(num_prop(s, "left"))
            f["size"].set(num_prop(s, "font-size"))
            if "color" in f:
                f["color"].set(color_prop(s) or "#ffffff")

        for i in range(8):
            n = i + 1
            s = get_style(f"place-{n}-render")
            self._d8_renders[i]["top"].set(num_prop(s, "top"))
            self._d8_renders[i]["left"].set(num_prop(s, "left"))
            self._d8_renders[i]["height"].set(num_prop(s, "height"))

            s = get_style(f"place-{n}-num")
            self._d8_nums[i]["top"].set(num_prop(s, "top"))
            self._d8_nums[i]["left"].set(num_prop(s, "left"))
            self._d8_nums[i]["size"].set(num_prop(s, "font-size"))

            s = get_style(f"place-{n}-name")
            self._d8_names[i]["top"].set(num_prop(s, "top"))
            self._d8_names[i]["left"].set(num_prop(s, "left"))
            self._d8_names[i]["size"].set(num_prop(s, "font-size"))

            s = get_style(f"place-{n}-sponsor")
            self._d8_sponsors[i]["top"].set(num_prop(s, "top"))
            self._d8_sponsors[i]["left"].set(num_prop(s, "left"))
            self._d8_sponsors[i]["size"].set(num_prop(s, "font-size"))

    def _apply_default_top8_config(self):
        import re
        html = self._top8_html_text.get("1.0", "end-1c")

        def patch_style(h, elem_id, props):
            def repl(m):
                style = m.group(2)
                for prop, val, unit in props:
                    if unit == "color":
                        style = re.sub(rf'(color:\s*)#[0-9a-fA-F]+', rf'\g<1>{val}', style)
                    elif unit in ("%", "px"):
                        style = re.sub(rf'({re.escape(prop)}:\s*)[\d.]+({re.escape(unit)})', rf'\g<1>{val}\2', style)
                return m.group(1) + style + '"'
            return re.sub(rf'(id="{re.escape(elem_id)}"[^>]*?style=")([^"]*)"', repl, h)

        label_color   = self._d8_label_color.get()
        sponsor_color = self._d8_sponsor_color.get()
        html = re.sub(r'(#canvas \.label \{[^}]*color:\s*)#[0-9a-fA-F]+',
                      rf'\g<1>{label_color}', html, flags=re.DOTALL)
        html = re.sub(r'(#canvas \.sponsor \{[^}]*color:\s*)#[0-9a-fA-F]+',
                      rf'\g<1>{sponsor_color}', html, flags=re.DOTALL)

        for i, eid in enumerate(["event-name", "event-link", "event-entrants", "event-date"]):
            f = self._d8_event[i]
            props = [("top", f["top"].get(), "%"), ("left", f["left"].get(), "%"),
                     ("font-size", f["size"].get(), "px")]
            if "color" in f:
                props.append(("color", f["color"].get(), "color"))
            html = patch_style(html, eid, props)

        for i in range(8):
            n = i + 1
            f = self._d8_renders[i]
            html = patch_style(html, f"place-{n}-render", [
                ("top", f["top"].get(), "%"), ("left", f["left"].get(), "%"),
                ("height", f["height"].get(), "%"),
            ])
            f = self._d8_nums[i]
            html = patch_style(html, f"place-{n}-num", [
                ("top", f["top"].get(), "%"), ("left", f["left"].get(), "%"),
                ("font-size", f["size"].get(), "px"),
            ])
            f = self._d8_names[i]
            html = patch_style(html, f"place-{n}-name", [
                ("top", f["top"].get(), "%"), ("left", f["left"].get(), "%"),
                ("font-size", f["size"].get(), "px"),
            ])
            f = self._d8_sponsors[i]
            html = patch_style(html, f"place-{n}-sponsor", [
                ("top", f["top"].get(), "%"), ("left", f["left"].get(), "%"),
                ("font-size", f["size"].get(), "px"),
            ])

        self._top8_html_text.delete("1.0", "end")
        self._top8_html_text.insert("end", html)
        self._highlight_html(self._top8_html_text)
        self._log("[Default config applied — click Save to write to disk]\n")

    # ------------------------------------------------------------------ #
    #  Syntax highlighting for the Top 8 editors                          #
    # ------------------------------------------------------------------ #
    # Both editors are plain tk.Text widgets; we colour them with tags    #
    # that are re-applied on load and (debounced) on every keystroke.     #
    def _setup_text_data_highlighting(self, widget: tk.Text):
        """Configure tags + key binding for the tab-delimited data editor."""
        # Created low→high priority so a comment always wins on overlap
        # (key < number < comment).
        widget.tag_configure("key", foreground=_SYN_KEY)
        widget.tag_configure("number", foreground=_SYN_NUMBER)
        widget.tag_configure("comment", foreground=_SYN_COMMENT)
        widget.bind(
            "<KeyRelease>",
            lambda _e: self._schedule_highlight(widget, self._highlight_text_data),
        )

    def _setup_html_highlighting(self, widget: tk.Text):
        """Configure tags + key binding for the HTML editor."""
        # Created low→high priority so later tags win on overlap
        # (tag name < attr < string < comment).
        widget.tag_configure("tag", foreground=_SYN_TAG)
        widget.tag_configure("attr", foreground=_SYN_KEY)
        widget.tag_configure("string", foreground=_SYN_STRING)
        widget.tag_configure("comment", foreground=_SYN_COMMENT)
        widget.bind(
            "<KeyRelease>",
            lambda _e: self._schedule_highlight(widget, self._highlight_html),
        )

    def _schedule_highlight(self, widget: tk.Text, func):
        """Debounce re-highlighting so typing in large files stays smooth."""
        job = getattr(widget, "_hl_job", None)
        if job is not None:
            try:
                widget.after_cancel(job)
            except Exception:
                pass
        widget._hl_job = widget.after(150, lambda: func(widget))

    @staticmethod
    def _apply_tag(widget: tk.Text, tag: str, start: int, end: int):
        """Tag a [start, end) character span. Tk char indices include the
        newline at each line's end, matching Python str offsets exactly."""
        widget.tag_add(tag, f"1.0+{start}c", f"1.0+{end}c")

    def _highlight_text_data(self, widget: tk.Text):
        content = widget.get("1.0", "end-1c")
        for tag in ("comment", "key", "number"):
            widget.tag_remove(tag, "1.0", "end")
        # Field keys: "Event name:" etc. at the start of a non-comment line
        for m in re.finditer(r"(?m)^[^#\n][^:\t\n]*:", content):
            self._apply_tag(widget, "key", m.start(), m.end())
        # Placement rows: leading integer (the place number)
        for m in re.finditer(r"(?m)^\d+", content):
            self._apply_tag(widget, "number", m.start(), m.end())
        # Comment lines (applied last; highest-priority tag overrides keys)
        for m in re.finditer(r"(?m)^[ \t]*#.*$", content):
            self._apply_tag(widget, "comment", m.start(), m.end())

    def _highlight_html(self, widget: tk.Text):
        content = widget.get("1.0", "end-1c")
        for tag in ("tag", "attr", "string", "comment"):
            widget.tag_remove(tag, "1.0", "end")
        # Tag names: <div, </div, <br/
        for m in re.finditer(r"</?[a-zA-Z][\w:-]*", content):
            self._apply_tag(widget, "tag", m.start(), m.end())
        # Attribute names: foo= (the name immediately before '=')
        for m in re.finditer(r"[a-zA-Z_:][\w:-]*(?==)", content):
            self._apply_tag(widget, "attr", m.start(), m.end())
        # Quoted strings (single or double, may span lines)
        for m in re.finditer(r"\"[^\"]*\"|'[^']*'", content, re.DOTALL):
            self._apply_tag(widget, "string", m.start(), m.end())
        # Comments override everything inside them
        for m in re.finditer(r"<!--.*?-->", content, re.DOTALL):
            self._apply_tag(widget, "comment", m.start(), m.end())

    def _open_top8_html_in_browser(self):
        import webbrowser
        import threading
        import http.server
        import socketserver
        import socket

        name = self._top8_html_file_var.get()
        if not name:
            self._log("[Error: no HTML file selected]\n")
            return

        # Start local HTTP server on first use; reuse on subsequent calls
        if not getattr(self, "_http_server", None):
            # Find a free port
            with socket.socket() as s:
                s.bind(("", 0))
                port = s.getsockname()[1]

            import functools
            handler = functools.partial(
                http.server.SimpleHTTPRequestHandler,
                directory=str(ROOT),
            )
            server = socketserver.TCPServer(("", port), handler)
            server.allow_reuse_address = True

            thread = threading.Thread(
                target=server.serve_forever, daemon=True, name="top8-http-server"
            )
            thread.start()
            self._http_server = server
            self._http_server_port = port
            self._log(f"[Local server started on port {port}]\n")

        url = f"http://localhost:{self._http_server_port}/Top_8_Results/{name}"
        webbrowser.open(url)
        self._log(f"[Opened {url}]\n")

    # ------------------------------------------------------------------ #
    #  Tab: Generate Posts                                                #
    # ------------------------------------------------------------------ #
    def _build_posts_tab(self, notebook: ttk.Notebook):
        tab = ttk.Frame(notebook)
        notebook.add(tab, text="Generate Posts")

        # Scrollable container (same pattern as other tabs so resize grip works)
        _canvas = tk.Canvas(tab, bg=_BG, highlightthickness=0)
        _vsb = ttk.Scrollbar(tab, orient="vertical", command=_canvas.yview)
        _canvas.configure(yscrollcommand=_vsb.set)
        _vsb.pack(side="right", fill="y")
        _canvas.pack(side="left", fill="both", expand=True)

        inner = ttk.Frame(_canvas)
        _inner_win = _canvas.create_window((0, 0), window=inner, anchor="nw")
        self._setup_scrollable_canvas(_canvas, inner, _inner_win)

        def _on_mousewheel(event):
            _canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")
        _canvas.bind("<Enter>", lambda e: _canvas.bind_all("<MouseWheel>", _on_mousewheel))
        _canvas.bind("<Leave>", lambda e: _canvas.unbind_all("<MouseWheel>"))

        # ── Event selector ─────────────────────────────────────────────
        lf_event = ttk.LabelFrame(inner, text="Event", padding=(8, 8))
        lf_event.pack(fill="x", padx=10, pady=(10, 4))

        row1 = ttk.Frame(lf_event)
        row1.pack(fill="x", pady=(0, 4))
        ttk.Label(row1, text="Series:").pack(side="left")
        self._posts_series = tk.StringVar()
        self._posts_series_box = ttk.Combobox(
            row1, textvariable=self._posts_series, state="readonly", width=26,
        )
        self._posts_series_box.pack(side="left", padx=(4, 4))
        ttk.Button(row1, text="↺", command=self._refresh_posts_events).pack(side="left", padx=(0, 12))
        ttk.Label(row1, text="# / Suffix:").pack(side="left")
        self._posts_num = tk.StringVar(value="")
        ttk.Entry(row1, textvariable=self._posts_num, width=8).pack(side="left", padx=4)

        row2 = ttk.Frame(lf_event)
        row2.pack(fill="x")
        ttk.Label(row2, text="Event name:").pack(side="left")
        self._posts_event_name = tk.StringVar()
        ttk.Entry(row2, textvariable=self._posts_event_name, width=40,
                  state="readonly").pack(side="left", padx=4)

        # ── Post settings ──────────────────────────────────────────────
        lf_cfg = ttk.LabelFrame(inner, text="Post Settings", padding=(8, 8))
        lf_cfg.pack(fill="x", padx=10, pady=(0, 4))

        # Next event toggle + date + link on one row
        self._posts_has_next = tk.BooleanVar(value=True)
        self._posts_next_date = tk.StringVar()  # used only when tkcalendar unavailable
        self._posts_next_link = tk.StringVar()
        self._posts_vods = tk.StringVar()

        row_next = ttk.Frame(lf_cfg)
        row_next.pack(fill="x", pady=(0, 4))
        ttk.Checkbutton(row_next, text="Next Event",
                        variable=self._posts_has_next,
                        command=self._update_posts_next_state).pack(side="left", padx=(0, 8))
        ttk.Label(row_next, text="Date:").pack(side="left")
        if _TKCALENDAR_AVAILABLE:
            import datetime as _dt
            self._posts_date_picker = _DateEntry(
                row_next, width=12, justify="center",
                showweeknumbers=False, firstweekday="sunday",
            )
            self._posts_date_picker.pack(side="left", padx=(4, 16))
            self._posts_next_date_entry = self._posts_date_picker
        else:
            self._posts_date_picker = None
            self._posts_next_date_entry = ttk.Entry(
                row_next, textvariable=self._posts_next_date, width=14)
            self._posts_next_date_entry.pack(side="left", padx=(4, 16))
        ttk.Label(row_next, text="Link:").pack(side="left")
        self._posts_next_link_entry = ttk.Entry(
            row_next, textvariable=self._posts_next_link, width=34)
        self._posts_next_link_entry.pack(side="left", padx=4)

        row_vods = ttk.Frame(lf_cfg)
        row_vods.pack(fill="x", pady=(0, 6))
        ttk.Label(row_vods, text="Vods link:").pack(side="left")
        ttk.Entry(row_vods, textvariable=self._posts_vods, width=56).pack(side="left", padx=4)

        row_btns = ttk.Frame(lf_cfg)
        row_btns.pack(fill="x")
        ttk.Button(row_btns, text="Fetch Twitter",
                   command=lambda: self._run_fetch_post("twitter")).pack(side="left", padx=(0, 6))
        ttk.Button(row_btns, text="Fetch Discord",
                   command=lambda: self._run_fetch_post("discord")).pack(side="left", padx=(0, 16))
        ttk.Button(row_btns, text="Save",
                   command=self._save_post_file).pack(side="left", padx=(0, 6))
        ttk.Button(row_btns, text="Copy",
                   command=self._copy_post_text).pack(side="left")

        self._posts_next_link.trace_add("write", lambda *_: self._save_settings())
        self._posts_has_next.trace_add("write", lambda *_: self._save_settings())
        self._posts_vods.trace_add("write", lambda *_: self._save_settings())

        # ── Collapsible editable text area ─────────────────────────────
        lf_text = self._make_collapsible_section(inner, "Post Text")

        txt_inner = ttk.Frame(lf_text)
        txt_inner.pack(fill="both", expand=True)
        txt_sb = ttk.Scrollbar(txt_inner)
        txt_sb.pack(side="right", fill="y")
        self._posts_text = tk.Text(
            txt_inner, height=20,
            bg=_BG, fg=_FG, insertbackground=_FG,
            font=("Consolas", 10), wrap="word",
            relief="flat", highlightthickness=0,
            yscrollcommand=txt_sb.set,
        )
        self._posts_text.pack(side="left", fill="both", expand=True)
        txt_sb.config(command=self._posts_text.yview)
        self._add_resize_grip(lf_text, self._posts_text)

        # ── Wire up series/num traces (after all StringVars exist) ─────
        def _on_posts_series_change(*_):
            series = self._posts_series.get()
            widgets = self._fetch_widgets.get(series)
            if widgets:
                self._posts_num.set(widgets["num"].get())
            else:
                custom = next((e for e in self._custom_events if e.get("label") == series), None)
                if custom:
                    slug_tmpl = custom.get("slug_template", custom.get("slug", ""))
                    cw = self._custom_event_widgets.get(slug_tmpl)
                    self._posts_num.set(cw["num"].get() if cw else custom.get("current_num", ""))
                else:
                    saved = self._settings.get("last_event_nums", {}).get(series)
                    if saved:
                        self._posts_num.set(saved)
            # Load per-series post config fields
            saved_cfg = self._settings.get("posts_cfg", {}).get(series, {})
            saved_date = saved_cfg.get("next_date", "")
            if _TKCALENDAR_AVAILABLE and hasattr(self, "_posts_date_picker") and self._posts_date_picker:
                import datetime as _dt
                try:
                    self._posts_date_picker.set_date(_dt.date.fromisoformat(saved_date))
                except (ValueError, TypeError):
                    pass
            else:
                self._posts_next_date.set(saved_date)
            self._posts_next_link.set(saved_cfg.get("next_link",
                next((c.get("tweet_link", "") for c in FETCH_EVENTS if c["label"] == series), "")))
            self._posts_vods.set(saved_cfg.get("vods", ""))
            self._posts_has_next.set(saved_cfg.get("has_next", True))
            self._update_posts_next_state()
            self._save_settings()

        def _update_posts_name(*_):
            template = self._posts_event_map.get(self._posts_series.get(), "{n}")
            self._posts_event_name.set(template.format(n=self._posts_num.get().strip()))
            self._posts_load_file()

        self._posts_series.trace_add("write", _on_posts_series_change)
        self._posts_series.trace_add("write", _update_posts_name)
        self._posts_num.trace_add("write", _update_posts_name)

        self._posts_active_file = None
        self._posts_event_map = {}
        self._refresh_posts_events()

    def _update_posts_next_state(self):
        state = "normal" if self._posts_has_next.get() else "disabled"
        self._posts_next_date_entry.config(state=state)
        self._posts_next_link_entry.config(state=state)

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
        self._posts_series_box["values"] = names
        if names:
            last = self._settings.get("last_posts_series")
            if last in names:
                self._posts_series.set(last)
            elif self._posts_series.get() not in names:
                self._posts_series.set(names[0])

    def _get_posts_cfg(self):
        """Return the FETCH_EVENTS config for the selected series, or None."""
        series = self._posts_series.get()
        return next((c for c in FETCH_EVENTS if c["label"] == series), None)

    def _posts_load_file(self):
        """Load the most recently generated post file for the current event into the text area."""
        event_name = self._posts_event_name.get().strip()
        if not event_name:
            return
        folder = ROOT / "Results_Posts"
        # Prefer whichever file exists (twitter first, then discord)
        for platform in ("twitter", "discord"):
            path = folder / f"{event_name} {platform.capitalize()} Post.txt"
            if path.exists():
                self._posts_active_file = path
                self._posts_text.delete("1.0", "end")
                self._posts_text.insert("1.0", path.read_text(encoding="utf-8").rstrip())
                return
        self._posts_active_file = None
        self._posts_text.delete("1.0", "end")

    def _run_fetch_post(self, platform: str):
        series = self._posts_series.get()
        n = self._posts_num.get().strip()
        event_name = self._posts_event_name.get().strip()
        if not event_name:
            self._log("[Error: no event selected]\n")
            return

        cfg = self._get_posts_cfg()
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

        cmd = [
            PYTHON, str(ROOT / "Python_Scripts" / "fetch_results_tweet.py"),
            slug, "--name", event_name, "--platform", platform, "--out", str(out_path),
        ]
        if self._posts_has_next.get():
            next_link = self._posts_next_link.get().strip()
            if next_link:
                cmd += ["--link", next_link]
            if _TKCALENDAR_AVAILABLE and self._posts_date_picker:
                next_date = _ordinal_date(self._posts_date_picker.get_date())
            else:
                next_date = self._posts_next_date.get().strip()
            if next_date:
                cmd += ["--next", next_date]
        vods = self._posts_vods.get().strip()
        if vods:
            cmd += ["--vods", vods]

        def _on_done():
            if out_path.exists():
                self._posts_text.delete("1.0", "end")
                self._posts_text.insert("1.0", out_path.read_text(encoding="utf-8").rstrip())

        self._run(cmd, on_done=_on_done)

    def _save_post_file(self):
        if not self._posts_active_file:
            event_name = self._posts_event_name.get().strip()
            if not event_name:
                self._log("[Error: no event selected]\n")
                return
            self._posts_active_file = ROOT / "Results_Posts" / f"{event_name} Post.txt"
        self._posts_active_file.parent.mkdir(parents=True, exist_ok=True)
        content = self._posts_text.get("1.0", "end-1c")
        self._posts_active_file.write_text(content + "\n", encoding="utf-8")
        self._log(f"[Saved {self._posts_active_file.name}]\n")

    def _copy_post_text(self):
        content = self._posts_text.get("1.0", "end-1c")
        if content.strip():
            self.root.clipboard_clear()
            self.root.clipboard_append(content)
            self._log("[Copied post to clipboard]\n")
        else:
            self._log("[Nothing to copy — fetch a post first]\n")

    # ------------------------------------------------------------------ #
    #  Tab: Character Renders                                             #
    # ------------------------------------------------------------------ #
    def _build_renders_tab(self, notebook: ttk.Notebook):
        tab = ttk.Frame(notebook)
        notebook.add(tab, text="Character Renders")

        lf = ttk.LabelFrame(tab, text="Manage Renders", padding=(10, 10))
        lf.pack(fill="x", padx=10, pady=10)

        ttk.Label(lf, text="Download render images from dragdown.wiki or copy them to the Full Renders folder.",
                  wraplength=560, justify="left").pack(anchor="w", pady=(0, 8))

        btn_cfg = [
            ("Download & Copy",      self._download_and_copy),
            ("Download Renders",     self._download_renders),
            ("Copy to Full Renders", self._copy_renders),
        ]
        for label, cmd in btn_cfg:
            ttk.Button(lf, text=label, command=cmd).pack(pady=3, anchor="w")

    def _download_renders(self):
        self._run([PYTHON, str(ROOT / "Python_Scripts" / "download_rivals_renders.py")])

    def _copy_renders(self):
        self._run([PYTHON, str(ROOT / "Python_Scripts" / "copy_rivals_renders_to_full.py")])

    def _download_and_copy(self):
        self._run_sequential(
            [PYTHON, str(ROOT / "Python_Scripts" / "download_rivals_renders.py")],
            [PYTHON, str(ROOT / "Python_Scripts" / "copy_rivals_renders_to_full.py")],
        )

    # ------------------------------------------------------------------ #
    #  Tab: Player Database                                               #
    # ------------------------------------------------------------------ #
    def _build_player_db_tab(self, notebook: ttk.Notebook):
        tab = ttk.Frame(notebook)
        notebook.add(tab, text="Player Database")

        self._db_header: list[str] = []
        self._db_players: dict[str, list[tuple[str, str]]] = {}
        self._db_selected_player: str | None = None
        self._db_selected_char_idx: int | None = None
        self._skin_stems: list[str] = []

        # Two-pane layout
        pane = tk.PanedWindow(tab, orient="horizontal", sashrelief="flat",
                              bg=_BG2, sashwidth=6)
        pane.pack(fill="both", expand=True, padx=10, pady=10)

        # --- Left: player list ---
        left = ttk.Frame(pane)
        pane.add(left, width=190)

        ttk.Label(left, text="Players", font=("Segoe UI", 10, "bold")).pack(anchor="w", pady=(0, 2))

        self._player_search = tk.StringVar()
        self._player_search_entry = ttk.Entry(left, textvariable=self._player_search)
        self._player_search_entry.pack(fill="x", pady=(0, 4))
        self._player_search.trace_add("write", lambda *_: self._debounce_player_search())
        _add_placeholder(self._player_search_entry, "Search players...")

        lb_frame = ttk.Frame(left)
        lb_frame.pack(fill="both", expand=True)
        lb_sb = ttk.Scrollbar(lb_frame)
        lb_sb.pack(side="right", fill="y")
        self._player_listbox = tk.Listbox(lb_frame, yscrollcommand=lb_sb.set, selectmode="single",
                                          activestyle="none", relief="flat", borderwidth=0)
        self._player_listbox.pack(side="left", fill="both", expand=True)
        lb_sb.config(command=self._player_listbox.yview)
        self._player_listbox.bind("<<ListboxSelect>>", self._on_player_select)

        self._new_player_frame = ttk.Frame(left)
        ttk.Label(self._new_player_frame, text="Name:").pack(side="left")
        self._new_player_var = tk.StringVar()
        self._new_player_entry = ttk.Entry(self._new_player_frame, textvariable=self._new_player_var)
        self._new_player_entry.pack(side="left", padx=(4, 0), fill="x", expand=True)
        self._new_player_entry.bind("<Return>", lambda _: self._confirm_add_player())
        self._new_player_entry.bind("<Escape>", lambda _: self._cancel_add_player())
        _add_placeholder(self._new_player_entry, "Player name...")

        self._new_player_frame.pack(fill="x", pady=(4, 0))

        self._btn_row = ttk.Frame(left)
        btn_row = self._btn_row
        btn_row.pack(fill="x", pady=(6, 0))
        ttk.Button(btn_row, text="+ Add", command=self._add_player).pack(side="left", fill="x", expand=True, padx=(0, 2))
        ttk.Button(btn_row, text="- Remove", command=self._remove_player).pack(side="left", fill="x", expand=True, padx=(2, 0))

        # --- Right: editor ---
        right = ttk.Frame(pane)
        pane.add(right)

        self._editing_label = ttk.Label(right, text="Select a player", font=("Segoe UI", 10, "bold"))
        self._editing_label.pack(anchor="w", pady=(0, 6))

        # Anchor save row to the bottom before packing expanding widgets so it
        # is never displaced when the skin preview image grows tall.
        save_row = ttk.Frame(right)
        save_row.pack(fill="x", side="bottom")
        ttk.Button(save_row, text="Save Player Database", command=self._save_player_db,
                   style="Accent.TButton").pack(side="left")
        ttk.Button(save_row, text="Reload from File", command=self._reload_player_db).pack(side="left", padx=(8, 0))
        ttk.Separator(right, orient="horizontal").pack(fill="x", pady=6, side="bottom")

        # Treeview
        tree_frame = ttk.Frame(right)
        tree_frame.pack(fill="both", expand=True)
        tree_sb = ttk.Scrollbar(tree_frame)
        tree_sb.pack(side="right", fill="y")
        self._char_tree = ttk.Treeview(
            tree_frame, columns=("char", "skin"), show="headings",
            yscrollcommand=tree_sb.set, selectmode="browse", height=8,
        )
        self._char_tree.heading("char", text="Character")
        self._char_tree.heading("skin", text="Skin")
        self._char_tree.column("char", width=130)
        self._char_tree.column("skin", width=240)
        self._char_tree.pack(side="left", fill="both", expand=True)
        tree_sb.config(command=self._char_tree.yview)
        self._char_tree.bind("<<TreeviewSelect>>", self._on_char_tree_select)

        tree_btns = ttk.Frame(right)
        tree_btns.pack(fill="x", pady=4)
        ttk.Button(tree_btns, text="Edit Selected", command=self._edit_char_entry).pack(side="left", padx=(0, 4))
        ttk.Button(tree_btns, text="Remove Selected", command=self._remove_char_entry).pack(side="left")
        ttk.Button(tree_btns, text="Move Up", command=lambda: self._move_char_entry(-1)).pack(side="right", padx=(4, 0))
        ttk.Button(tree_btns, text="Move Down", command=lambda: self._move_char_entry(1)).pack(side="right")

        ttk.Separator(right, orient="horizontal").pack(fill="x", pady=6)

        ttk.Label(right, text="Add / Edit Entry", font=("Segoe UI", 9, "bold")).pack(anchor="w", pady=(0, 4))

        form_section = ttk.Frame(right)
        form_section.pack(fill="x")
        form_left = ttk.Frame(form_section)
        form_left.pack(side="left", fill="y")
        form_right = ttk.Frame(form_section)
        form_right.pack(side="left", padx=(12, 0), anchor="n")

        form_row = ttk.Frame(form_left)
        form_row.pack(fill="x")
        ttk.Label(form_row, text="Character:").pack(side="left")
        self._form_char = tk.StringVar()
        ttk.Combobox(
            form_row, textvariable=self._form_char, values=CHARACTERS, state="readonly", width=14,
        ).pack(side="left", padx=(4, 12))
        self._form_char.trace_add("write", self._on_form_char_change)

        ttk.Label(form_row, text="Skin:").pack(side="left")
        self._form_skin_var = tk.StringVar()
        self._form_skin_box = ttk.Combobox(form_row, textvariable=self._form_skin_var, state="readonly", width=30)
        self._form_skin_box.pack(side="left", padx=4)
        self._form_skin_var.trace_add("write", self._on_form_skin_change)

        form_btns = ttk.Frame(form_left)
        form_btns.pack(fill="x", pady=4)
        self._form_add_btn = ttk.Button(form_btns, text="Add Entry", command=self._add_char_entry)
        self._form_add_btn.pack(side="left", padx=(0, 4))
        self._form_edit_btn = ttk.Button(form_btns, text="Update Entry", command=self._update_char_entry, state="disabled")
        self._form_edit_btn.pack(side="left")
        ttk.Button(form_btns, text="Clear Form", command=self._clear_form).pack(side="left", padx=(8, 0))

        self._preview_label = tk.Label(form_right, bg=_BG3, width=22, height=9)
        self._preview_label.pack()
        self._preview_img = None
        self._preview_cache = {}
        self._preview_debounce_job = None
        self._preview_loading_stem = None

        self._reload_player_db()

    def _reload_player_db(self):
        self._db_header, self._db_players = load_player_db()
        self._refresh_player_list()
        self._clear_char_tree()
        self._editing_label.config(text="Select a player")
        self._db_selected_player = None

    def _debounce_player_search(self):
        if hasattr(self, "_player_search_job") and self._player_search_job:
            self.root.after_cancel(self._player_search_job)
        self._player_search_job = self.root.after(200, self._refresh_player_list)

    def _refresh_player_list(self):
        raw = self._player_search.get()
        query = "" if raw == "Search players..." else raw.lower()
        self._player_listbox.delete(0, "end")
        for name in sorted(self._db_players, key=str.casefold):
            if query in name.lower():
                self._player_listbox.insert("end", name)

    def _on_player_select(self, _event=None):
        sel = self._player_listbox.curselection()
        if not sel:
            return
        name = self._player_listbox.get(sel[0])
        self._db_selected_player = name
        self._editing_label.config(text=f"Editing: {name}")
        self._populate_char_tree(name)
        self._clear_form()

    def _populate_char_tree(self, name: str):
        self._clear_char_tree()
        for idx, (char, skin) in enumerate(self._db_players.get(name, [])):
            lbl = skin_label(skin) if skin else "(none)"
            self._char_tree.insert("", "end", iid=str(idx), values=(char, lbl))

    def _clear_char_tree(self):
        for row in self._char_tree.get_children():
            self._char_tree.delete(row)

    def _add_player(self):
        self._confirm_add_player()

    def _confirm_add_player(self):
        raw = self._new_player_var.get()
        name = "" if raw == "Player name..." else raw.strip()
        if not name:
            return
        if name in self._db_players:
            self._log(f"[Player '{name}' already exists]\n")
            self._new_player_var.set("")
            return
        self._db_players[name] = []
        self._new_player_var.set("")
        self._player_search.set("")
        self._refresh_player_list()
        all_names = list(self._player_listbox.get(0, "end"))
        if name in all_names:
            idx = all_names.index(name)
            self._player_listbox.selection_clear(0, "end")
            self._player_listbox.selection_set(idx)
            self._player_listbox.see(idx)
            self._on_player_select()

    def _cancel_add_player(self):
        self._new_player_var.set("")

    def _remove_player(self):
        if not self._db_selected_player or self._db_selected_player not in self._db_players:
            return
        del self._db_players[self._db_selected_player]
        self._db_selected_player = None
        self._refresh_player_list()
        self._clear_char_tree()
        self._editing_label.config(text="Select a player")

    def _on_form_char_change(self, *_):
        char = self._form_char.get()
        stems = get_skins_for_char(char)
        self._skin_stems = stems
        labels = [skin_label(s) for s in stems]
        self._form_skin_box["values"] = labels
        self._form_skin_var.set(labels[0] if labels else "")

    def _on_form_skin_change(self, *_):
        stem = self._skin_stem_from_label(self._form_skin_var.get())
        self._show_preview(stem)

    def _on_char_tree_select(self, _event=None):
        sel = self._char_tree.selection()
        if not sel:
            return
        values = self._char_tree.item(sel[0], "values")
        if not values or len(values) < 2:
            return
        char, lbl = values[0], values[1]
        stems = get_skins_for_char(char)
        labels = [skin_label(s) for s in stems]
        stem = stems[labels.index(lbl)] if lbl in labels else ""
        self._show_preview(stem)

    def _show_preview(self, skin_stem: str):
        if not _PIL_AVAILABLE:
            return
        if self._preview_debounce_job:
            self.root.after_cancel(self._preview_debounce_job)
        self._preview_debounce_job = self.root.after(150, self._load_preview, skin_stem)

    def _load_preview(self, skin_stem: str):
        self._preview_debounce_job = None
        if not skin_stem:
            self._clear_preview()
            return
        if skin_stem in self._preview_cache:
            photo, w, h = self._preview_cache[skin_stem]
            self._preview_img = photo
            self._preview_label.config(image=photo, width=w, height=h)
            return
        path = RENDERS_DIR / f"{skin_stem}.png"
        if not path.exists():
            self._clear_preview()
            return
        self._preview_loading_stem = skin_stem

        def _worker():
            try:
                img = Image.open(path)
                w = 220
                h = round(img.height * w / img.width)
                img = img.resize((w, h), Image.LANCZOS)
                self.root.after(0, self._apply_preview, skin_stem, img, w, h)
            except Exception:
                self.root.after(0, self._clear_preview)

        threading.Thread(target=_worker, daemon=True).start()

    def _apply_preview(self, skin_stem: str, img, w: int, h: int):
        if self._preview_loading_stem != skin_stem:
            return
        photo = ImageTk.PhotoImage(img)
        self._preview_cache[skin_stem] = (photo, w, h)
        self._preview_img = photo
        self._preview_label.config(image=photo, width=w, height=h)

    def _clear_preview(self):
        self._preview_img = None
        self._preview_label.config(image="", width=22, height=9)

    def _skin_stem_from_label(self, lbl: str) -> str:
        labels = [skin_label(s) for s in self._skin_stems]
        if lbl in labels:
            return self._skin_stems[labels.index(lbl)]
        return lbl

    def _add_char_entry(self):
        if not self._db_selected_player:
            self._log("[Select a player first]\n")
            return
        char = self._form_char.get()
        if not char:
            self._log("[Select a character]\n")
            return
        skin_stem = self._skin_stem_from_label(self._form_skin_var.get())
        self._db_players[self._db_selected_player].append((char, skin_stem))
        self._populate_char_tree(self._db_selected_player)

    def _edit_char_entry(self):
        sel = self._char_tree.selection()
        if not sel or not self._db_selected_player:
            return
        idx = int(sel[0])
        chars = self._db_players[self._db_selected_player]
        if idx >= len(chars):
            return
        char, skin_stem = chars[idx]
        self._form_char.set(char)  # trace fires _on_form_char_change → loads skins
        self._form_skin_var.set(skin_label(skin_stem) if skin_stem else "")
        self._db_selected_char_idx = idx
        self._form_add_btn.config(state="disabled")
        self._form_edit_btn.config(state="normal")

    def _update_char_entry(self):
        if self._db_selected_char_idx is None or not self._db_selected_player:
            return
        char = self._form_char.get()
        skin_stem = self._skin_stem_from_label(self._form_skin_var.get())
        chars = self._db_players[self._db_selected_player]
        if self._db_selected_char_idx < len(chars):
            chars[self._db_selected_char_idx] = (char, skin_stem)
        self._populate_char_tree(self._db_selected_player)
        self._clear_form()

    def _remove_char_entry(self):
        sel = self._char_tree.selection()
        if not sel or not self._db_selected_player:
            return
        idx = int(sel[0])
        chars = self._db_players[self._db_selected_player]
        if idx < len(chars):
            chars.pop(idx)
        self._populate_char_tree(self._db_selected_player)

    def _move_char_entry(self, direction: int):
        sel = self._char_tree.selection()
        if not sel or not self._db_selected_player:
            return
        idx = int(sel[0])
        chars = self._db_players[self._db_selected_player]
        new_idx = idx + direction
        if 0 <= new_idx < len(chars):
            chars[idx], chars[new_idx] = chars[new_idx], chars[idx]
            self._populate_char_tree(self._db_selected_player)
            self._char_tree.selection_set(str(new_idx))

    def _clear_form(self):
        self._form_char.set("")
        self._form_skin_var.set("")
        self._skin_stems = []
        self._form_skin_box["values"] = []
        self._form_add_btn.config(state="normal")
        self._form_edit_btn.config(state="disabled")
        self._db_selected_char_idx = None
        self._clear_preview()

    def _save_player_db(self):
        try:
            save_player_db(self._db_header, self._db_players)
            self._log("[Player database saved]\n")
        except Exception as exc:
            self._log(f"[Error saving player database: {exc}]\n")

    # ------------------------------------------------------------------ #
    #  Tab: Character Database                                            #
    # ------------------------------------------------------------------ #
    def _build_char_db_tab(self, notebook: ttk.Notebook):
        tab = ttk.Frame(notebook)
        notebook.add(tab, text="Character Database")

        self._cdb_headers: list[str] = []
        self._cdb_chars: list[str] = []

        top = ttk.Frame(tab)
        top.pack(fill="both", expand=True, padx=10, pady=(10, 4))

        ttk.Label(top, text="Characters", font=("Segoe UI", 10, "bold")).pack(anchor="w", pady=(0, 2))

        list_frame = ttk.Frame(top)
        list_frame.pack(fill="both", expand=True)
        cdb_sb = ttk.Scrollbar(list_frame)
        cdb_sb.pack(side="right", fill="y")
        self._cdb_listbox = tk.Listbox(
            list_frame, yscrollcommand=cdb_sb.set,
            selectmode="single", activestyle="none", width=34,
            relief="flat", borderwidth=0,
        )
        self._cdb_listbox.pack(side="left", fill="both", expand=True)
        cdb_sb.config(command=self._cdb_listbox.yview)

        add_row = ttk.Frame(tab)
        add_row.pack(fill="x", padx=10, pady=(4, 0))
        ttk.Label(add_row, text="Name:").pack(side="left")
        self._cdb_new_var = tk.StringVar()
        self._cdb_new_entry = ttk.Entry(add_row, textvariable=self._cdb_new_var, width=25)
        self._cdb_new_entry.pack(side="left", padx=(4, 0))
        self._cdb_new_entry.bind("<Return>", lambda _: self._cdb_add())
        self._cdb_new_entry.bind("<Escape>", lambda _: self._cdb_new_var.set(""))
        _add_placeholder(self._cdb_new_entry, "Character name...")

        btn_row = ttk.Frame(tab)
        btn_row.pack(fill="x", padx=10, pady=4)
        ttk.Button(btn_row, text="+ Add",    command=self._cdb_add).pack(side="left", padx=(0, 4))
        ttk.Button(btn_row, text="Rename",   command=self._cdb_rename).pack(side="left", padx=(0, 4))
        ttk.Button(btn_row, text="- Remove", command=self._cdb_remove).pack(side="left")
        ttk.Button(btn_row, text="Move Up",   command=lambda: self._cdb_move(-1)).pack(side="right", padx=(4, 0))
        ttk.Button(btn_row, text="Move Down", command=lambda: self._cdb_move(1)).pack(side="right")

        ttk.Separator(tab, orient="horizontal").pack(fill="x", padx=10, pady=4)

        save_row = ttk.Frame(tab)
        save_row.pack(fill="x", padx=10, pady=(0, 8))
        ttk.Button(save_row, text="Save Character Database", command=self._cdb_save,
                   style="Accent.TButton").pack(side="left")
        ttk.Button(save_row, text="Reload from File", command=self._cdb_reload).pack(side="left", padx=(8, 0))

        self._cdb_reload()

    def _cdb_reload(self):
        self._cdb_headers, self._cdb_chars = load_char_db()
        self._cdb_refresh()

    def _cdb_refresh(self):
        self._cdb_listbox.delete(0, "end")
        for name in self._cdb_chars:
            self._cdb_listbox.insert("end", name)

    def _cdb_selected_idx(self):
        sel = self._cdb_listbox.curselection()
        return int(sel[0]) if sel else None

    def _cdb_add(self):
        raw = self._cdb_new_var.get()
        name = "" if raw == "Character name..." else raw.strip()
        if not name:
            return
        if name in self._cdb_chars:
            self._log(f"['{name}' already in character database]\n")
            self._cdb_new_var.set("")
            return
        self._cdb_chars.append(name)
        self._cdb_new_var.set("")
        self._cdb_refresh()
        idx = len(self._cdb_chars) - 1
        self._cdb_listbox.selection_set(idx)
        self._cdb_listbox.see(idx)

    def _cdb_rename(self):
        idx = self._cdb_selected_idx()
        if idx is None:
            self._log("[Select a character to rename]\n")
            return
        old_name = self._cdb_chars[idx]

        dialog = tk.Toplevel(self.root)
        dialog.title("Rename Character")
        dialog.geometry("280x110")
        dialog.transient(self.root)
        dialog.grab_set()
        ttk.Label(dialog, text="New name:").pack(pady=(14, 4))
        name_var = tk.StringVar(value=old_name)
        entry = ttk.Entry(dialog, textvariable=name_var, width=28)
        entry.pack()
        entry.focus()
        entry.select_range(0, "end")

        def confirm():
            name = name_var.get().strip()
            if not name or name == old_name:
                dialog.destroy()
                return
            if name in self._cdb_chars:
                self._log(f"['{name}' already in character database]\n")
                dialog.destroy()
                return
            self._cdb_chars[idx] = name
            self._cdb_refresh()
            self._cdb_listbox.selection_set(idx)
            self._cdb_listbox.see(idx)
            dialog.destroy()

        entry.bind("<Return>", lambda _: confirm())
        ttk.Button(dialog, text="Rename", command=confirm).pack(pady=8)

    def _cdb_remove(self):
        idx = self._cdb_selected_idx()
        if idx is None:
            return
        self._cdb_chars.pop(idx)
        self._cdb_refresh()
        new_sel = min(idx, len(self._cdb_chars) - 1)
        if new_sel >= 0:
            self._cdb_listbox.selection_set(new_sel)

    def _cdb_move(self, direction: int):
        idx = self._cdb_selected_idx()
        if idx is None:
            return
        new_idx = idx + direction
        if 0 <= new_idx < len(self._cdb_chars):
            self._cdb_chars[idx], self._cdb_chars[new_idx] = self._cdb_chars[new_idx], self._cdb_chars[idx]
            self._cdb_refresh()
            self._cdb_listbox.selection_set(new_idx)
            self._cdb_listbox.see(new_idx)

    def _cdb_save(self):
        try:
            save_char_db(self._cdb_headers, self._cdb_chars)
            self._log("[Character database saved]\n")
        except Exception as exc:
            self._log(f"[Error saving character database: {exc}]\n")

    # ------------------------------------------------------------------ #
    #  Process runners                                                    #
    # ------------------------------------------------------------------ #
    def _run(self, cmd: list, on_done=None):
        def worker():
            self._log(f"> {' '.join(str(c) for c in cmd)}\n")
            success = False
            try:
                proc = subprocess.Popen(
                    cmd, cwd=str(ROOT),
                    stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                    text=True, encoding="utf-8", errors="replace", bufsize=1,
                )
                for line in proc.stdout:
                    self._log(line)
                proc.wait()
                success = proc.returncode == 0
                self._log(f"[Done — exit {proc.returncode}]\n\n")
            except Exception as exc:
                self._log(f"[Error: {exc}]\n\n")
            # Fire completion callback on the main thread (worker runs off-thread).
            if success and on_done is not None:
                self.root.after(0, on_done)
        threading.Thread(target=worker, daemon=True).start()

    def _run_sequential(self, *cmds: list):
        def worker():
            for cmd in cmds:
                self._log(f"> {' '.join(str(c) for c in cmd)}\n")
                try:
                    proc = subprocess.Popen(
                        cmd, cwd=str(ROOT),
                        stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                        text=True, encoding="utf-8", errors="replace", bufsize=1,
                    )
                    for line in proc.stdout:
                        self._log(line)
                    proc.wait()
                    if proc.returncode != 0:
                        self._log(f"[Stopped — exit {proc.returncode}]\n\n")
                        return
                except Exception as exc:
                    self._log(f"[Error: {exc}]\n\n")
                    return
            self._log("[Done]\n\n")
        threading.Thread(target=worker, daemon=True).start()

    # ------------------------------------------------------------------ #
    #  Console helpers                                                    #
    # ------------------------------------------------------------------ #
    def _log(self, text: str):
        self.root.after(0, self._append_console, text)

    def _append_console(self, text: str):
        self.console.config(state="normal")
        self.console.insert("end", text)
        self.console.see("end")
        self.console.config(state="disabled")

    def _clear_console(self):
        self.console.config(state="normal")
        self.console.delete("1.0", "end")
        self.console.config(state="disabled")


if __name__ == "__main__":
    root = tk.Tk()
    app = RivalsGUI(root)
    root.mainloop()
