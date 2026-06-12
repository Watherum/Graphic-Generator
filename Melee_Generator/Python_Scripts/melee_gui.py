#!/usr/bin/env python3
"""GUI launcher for the Melee_Generator toolset."""
import tkinter as tk
from tkinter import ttk
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

ROOT = Path(__file__).parent.parent
PYTHON = sys.executable
RENDERS_DIR = ROOT / "Resources" / "Character_Renders" / "Melee_Full_Renders"
PLAYER_DB_PATH = ROOT / "Resources" / "Player_database.csv"
CHAR_DB_PATH = ROOT / "Resources" / "Character_database.csv"
THUMBNAIL_SCRIPT = ROOT / "Python_Scripts" / "generate_melee_thumbnails.py"

# sv_ttk dark palette (used for classic tk widgets that sv_ttk doesn't reach)
_BG    = "#1c1c1c"
_BG2   = "#2b2b2b"
_BG3   = "#3b3b3b"
_FG    = "#ffffff"
_MUTED = "#999999"
_SEL   = "#0078d4"

FETCH_EVENTS = [
    {
        "label": "CR Clash",
        "slug_template": "tournament/cr-clash-{n}/event/melee-singles",
        "name_template": "CR Clash {n}",
        "default_num": "77",
        "default_link": "",
        "top8_file": "CR Clash Top 8 HTML.txt",
    },
    {
        "label": "Immortal Fight Night",
        "slug_template": "tournament/immortal-fight-night-{n}/event/melee-singles",
        "name_template": "Immortal Fight Night {n}",
        "default_num": "145",
        "default_link": "",
        "top8_file": "Immortal Fight Night Top 8 HTML.txt",
    },
    {
        "label": "Clip It",
        "slug_template": "tournament/clip-it-{n}/event/melee-singles",
        "name_template": "Clip It {n}",
        "default_num": "3",
        "default_link": "",
        "top8_file": "Clip It Top 8 HTML.txt",
    },
    {
        "label": "CR Arcadian",
        "slug_template": "tournament/cr-arcadian/event/melee-singles",
        "name_template": "CR Arcadian",
        "default_num": "",
        "default_link": "",
        "top8_file": "CR Arcadian Top 8 HTML.txt",
    },
]


def _apply_theme(root: tk.Tk) -> None:
    if _SV_TTK_AVAILABLE:
        sv_ttk.set_theme("dark")
    else:
        style = ttk.Style(root)
        style.theme_use("clam")
        style.configure(".", background=_BG2, foreground=_FG)

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


def get_characters_from_renders() -> list:
    """Derive character names from the renders folder by stripping the ' (N)' suffix."""
    if not RENDERS_DIR.exists():
        return []
    names: set = set()
    for f in RENDERS_DIR.glob("*.png"):
        names.add(re.sub(r"\s*\(\d+\)$", "", f.stem))
    return sorted(names)


def load_thumbnail_events() -> list:
    """Parse startswith() calls from the dispatcher in generate_melee_thumbnails.py."""
    try:
        source = THUMBNAIL_SCRIPT.read_text(encoding="utf-8")
        names = re.findall(r"weekly_event\.startswith\('([^']+)'\)", source)
        return [(name, f"{name} {{n}}") for name in names]
    except Exception:
        return []


def load_player_db() -> tuple:
    """Load player database. Returns (header_lines, {player: [(char, alt), ...]})."""
    headers: list = []
    players: dict = {}
    try:
        lines = PLAYER_DB_PATH.read_text(encoding="utf-8").splitlines()
    except FileNotFoundError:
        return [], {}
    in_players = False
    for line in lines:
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            if not in_players:
                headers.append(line)
            continue
        in_players = True
        parts = [p.strip() for p in stripped.split(",")]
        while parts and not parts[-1]:
            parts.pop()
        if not parts:
            continue
        name = parts[0]
        char_alts: list = []
        for i in range(1, len(parts) - 1, 2):
            char = parts[i]
            alt = parts[i + 1] if i + 1 < len(parts) else ""
            if char:
                char_alts.append((char, alt))
        players[name] = char_alts
    return headers, players


def save_player_db(headers: list, players: dict) -> None:
    lines = list(headers)
    for name, char_alts in players.items():
        parts = [name]
        for char, alt in char_alts:
            parts += [char, alt]
        lines.append(",".join(parts))
    PLAYER_DB_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")


def load_char_db() -> tuple:
    """Load character database. Returns (header_lines, [(alias, filename), ...])."""
    headers: list = []
    entries: list = []
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


def save_char_db(headers: list, entries: list) -> None:
    lines = list(headers)
    for alias, filename in entries:
        lines.append(f"{alias},{filename}")
    CHAR_DB_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")


class MeleeGUI:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title("Melee_Generator")
        self.root.geometry("900x840")
        self.root.resizable(True, True)

        _apply_theme(self.root)

        notebook = ttk.Notebook(root)
        notebook.pack(fill="both", expand=True, padx=0, pady=0)

        self._build_fetch_tab(notebook)
        self._build_thumbnails_tab(notebook)
        self._build_player_db_tab(notebook)
        self._build_char_db_tab(notebook)

        # Shared console
        console_frame = ttk.LabelFrame(root, text="Console Output")
        console_frame.pack(fill="both", expand=True, padx=0, pady=0)

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

        footer = ttk.Frame(root)
        footer.pack(fill="x", padx=8, pady=(4, 8))
        ttk.Button(footer, text="Clear Console", command=self._clear_console).pack(side="right")

    # ------------------------------------------------------------------ #
    #  Tab: Fetch from start.gg                                           #
    # ------------------------------------------------------------------ #
    def _build_fetch_tab(self, notebook: ttk.Notebook):
        tab = ttk.Frame(notebook)
        notebook.add(tab, text="Fetch from start.gg")

        self._fetch_widgets = {}

        for cfg in FETCH_EVENTS:
            lf = ttk.LabelFrame(tab, text=cfg["label"], padding=(8, 6))
            lf.pack(fill="x", padx=10, pady=8)

            row1 = ttk.Frame(lf)
            row1.pack(fill="x", pady=(0, 4))

            has_num = bool(cfg["default_num"] or "{n}" in cfg["slug_template"])

            if has_num:
                ttk.Label(row1, text="Event #:").pack(side="left")
                num_var = tk.StringVar(value=cfg["default_num"])
                ttk.Entry(row1, textvariable=num_var, width=6).pack(side="left", padx=(4, 16))
            else:
                num_var = tk.StringVar(value="")

            if cfg.get("default_link") != "":
                ttk.Label(row1, text="Top 8 Link:").pack(side="left")
                link_var = tk.StringVar(value=cfg["default_link"].replace("{n}", cfg["default_num"]))
                ttk.Entry(row1, textvariable=link_var, width=32).pack(side="left", padx=4)
                if has_num:
                    def _on_num_change(name, index, mode, nv=num_var, lv=link_var, t=cfg["default_link"]):
                        lv.set(t.replace("{n}", nv.get().strip()))
                    num_var.trace_add("write", _on_num_change)
            else:
                link_var = tk.StringVar(value="")

            row2 = ttk.Frame(lf)
            row2.pack(fill="x")

            ttk.Button(
                row2, text="Fetch VOD Names",
                command=lambda c=cfg, nv=num_var: self._fetch_sets(c, nv.get().strip()),
            ).pack(side="left", padx=(0, 6))

            if cfg.get("top8_file"):
                ttk.Button(
                    row2, text="Fetch Top 8",
                    command=lambda c=cfg, nv=num_var, lv=link_var: self._fetch_top8(
                        c, nv.get().strip(), lv.get().strip()
                    ),
                ).pack(side="left")

            self._fetch_widgets[cfg["label"]] = {"num": num_var, "link": link_var}

        lf_custom = ttk.LabelFrame(tab, text="Custom Tournament", padding=(8, 6))
        lf_custom.pack(fill="x", padx=10, pady=(0, 8))

        row_slug = ttk.Frame(lf_custom)
        row_slug.pack(fill="x", pady=(0, 4))
        ttk.Label(row_slug, text="Slug:", width=10, anchor="w").pack(side="left")
        self._custom_slug = tk.StringVar()
        ttk.Entry(row_slug, textvariable=self._custom_slug, width=52).pack(side="left", padx=4)
        ttk.Label(row_slug, text="e.g. tournament/my-event/event/melee-singles",
                  style="Muted.TLabel").pack(side="left", padx=(4, 0))

        row_name = ttk.Frame(lf_custom)
        row_name.pack(fill="x", pady=(0, 4))
        ttk.Label(row_name, text="Name:", width=10, anchor="w").pack(side="left")
        self._custom_name = tk.StringVar()
        ttk.Entry(row_name, textvariable=self._custom_name, width=36).pack(side="left", padx=4)

        row_out = ttk.Frame(lf_custom)
        row_out.pack(fill="x", pady=(0, 4))
        ttk.Label(row_out, text="Output file:", width=10, anchor="w").pack(side="left")
        self._custom_out = tk.StringVar()
        ttk.Entry(row_out, textvariable=self._custom_out, width=36).pack(side="left", padx=4)
        ttk.Label(row_out, text="(saved in Vod_Names/ if no path given)",
                  style="Muted.TLabel").pack(side="left", padx=(4, 0))

        def _on_custom_name_change(*_):
            name = self._custom_name.get().strip()
            if name and not self._custom_out.get().strip():
                self._custom_out.set(f"{name} Names.txt")
        self._custom_name.trace_add("write", _on_custom_name_change)

        ttk.Button(lf_custom, text="Fetch VOD Names",
                   command=self._fetch_custom_sets).pack(anchor="w")

    def _fetch_custom_sets(self):
        slug = self._custom_slug.get().strip()
        name = self._custom_name.get().strip()
        out = self._custom_out.get().strip()
        if not slug:
            self._log("[Error: slug is required]\n")
            return
        if not out:
            self._log("[Error: output filename is required]\n")
            return
        if "/" not in out and "\\" not in out:
            out = str(ROOT / "Vod_Names" / out)
        cmd = [PYTHON, str(ROOT / "Python_Scripts" / "fetch_sets.py"), slug]
        if name:
            cmd += ["--name", name]
        cmd += ["--out", out]
        self._run(cmd)

    def _fetch_sets(self, cfg: dict, n: str):
        if "{n}" in cfg["slug_template"]:
            name = cfg["name_template"].format(n=n)
            slug = cfg["slug_template"].format(n=n)
        else:
            name = cfg["name_template"]
            slug = cfg["slug_template"]
        out = str(ROOT / "Vod_Names" / f"{name} Names.txt")
        self._run([
            PYTHON, str(ROOT / "Python_Scripts" / "fetch_sets.py"),
            slug, "--name", name, "--out", out,
        ])

    def _fetch_top8(self, cfg: dict, n: str, link: str):
        if "{n}" in cfg["slug_template"]:
            name = cfg["name_template"].format(n=n)
            slug = cfg["slug_template"].format(n=n)
        else:
            name = cfg["name_template"]
            slug = cfg["slug_template"]
        out = str(ROOT / "Top_8_Texts" / cfg["top8_file"])
        cmd = [PYTHON, str(ROOT / "Python_Scripts" / "fetch_startgg_top8.py"),
               slug, "--name", name, "--out", out]
        if link:
            cmd += ["--link", link]
        self._run(cmd)

    # ------------------------------------------------------------------ #
    #  Tab: Generate Thumbnails                                           #
    # ------------------------------------------------------------------ #
    def _build_thumbnails_tab(self, notebook: ttk.Notebook):
        tab = ttk.Frame(notebook)
        notebook.add(tab, text="Generate Thumbnails")

        lf = ttk.LabelFrame(tab, text="Event", padding=(8, 8))
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
        self._thumb_num = tk.StringVar(value="1")
        ttk.Entry(row1, textvariable=self._thumb_num, width=8).pack(side="left", padx=4)

        row2 = ttk.Frame(lf)
        row2.pack(fill="x", pady=(0, 6))
        ttk.Label(row2, text="Event name:").pack(side="left")
        self._thumb_event_name = tk.StringVar()
        ttk.Entry(row2, textvariable=self._thumb_event_name, width=40).pack(side="left", padx=4)

        def _update_name(*_):
            template = self._thumb_event_map.get(self._thumb_series.get(), "{n}")
            self._thumb_event_name.set(template.format(n=self._thumb_num.get().strip()))

        self._thumb_series.trace_add("write", _update_name)
        self._thumb_num.trace_add("write", _update_name)
        self._thumb_update_name = _update_name

        self._refresh_thumbnail_events()

        ttk.Button(tab, text="Generate Thumbnails", command=self._generate_thumbnails,
                   style="Accent.TButton").pack(padx=10, pady=8, anchor="w")

    def _refresh_thumbnail_events(self):
        events = load_thumbnail_events()
        self._thumb_event_map = {name: tmpl for name, tmpl in events}
        names = [name for name, _ in events]
        self._thumb_series_box["values"] = names
        if names and self._thumb_series.get() not in names:
            default = "CR Clash" if "CR Clash" in names else names[0]
            self._thumb_series.set(default)
        self._thumb_update_name()

    def _generate_thumbnails(self):
        event_name = self._thumb_event_name.get().strip()
        if not event_name:
            self._log("[Error: event name is empty]\n")
            return
        self._run([
            PYTHON, str(ROOT / "Python_Scripts" / "generate_melee_thumbnails.py"),
            "-e", event_name, "-o", "missing.log",
        ])

    # ------------------------------------------------------------------ #
    #  Tab: Player Database                                               #
    # ------------------------------------------------------------------ #
    def _build_player_db_tab(self, notebook: ttk.Notebook):
        tab = ttk.Frame(notebook)
        notebook.add(tab, text="Player Database")

        self._db_header: list = []
        self._db_players: dict = {}
        self._db_selected_player = None
        self._db_selected_char_idx = None
        self._char_suggestions = get_characters_from_renders()

        pane = tk.PanedWindow(tab, orient="horizontal", sashrelief="flat",
                              bg=_BG2, sashwidth=6)
        pane.pack(fill="both", expand=True, padx=10, pady=10)

        # --- Left: player list ---
        left = ttk.Frame(pane)
        pane.add(left, width=190)

        ttk.Label(left, text="Players", font=("Segoe UI", 10, "bold")).pack(anchor="w", pady=(0, 2))

        self._player_search = tk.StringVar()
        ttk.Entry(left, textvariable=self._player_search).pack(fill="x", pady=(0, 4))
        self._player_search.trace_add("write", lambda *_: self._refresh_player_list())

        lb_frame = ttk.Frame(left)
        lb_frame.pack(fill="both", expand=True)
        lb_sb = ttk.Scrollbar(lb_frame)
        lb_sb.pack(side="right", fill="y")
        self._player_listbox = tk.Listbox(
            lb_frame, yscrollcommand=lb_sb.set, selectmode="single",
            activestyle="none", relief="flat", borderwidth=0,
        )
        self._player_listbox.pack(side="left", fill="both", expand=True)
        lb_sb.config(command=self._player_listbox.yview)
        self._player_listbox.bind("<<ListboxSelect>>", self._on_player_select)

        btn_row = ttk.Frame(left)
        btn_row.pack(fill="x", pady=(6, 0))
        ttk.Button(btn_row, text="+ Add", command=self._add_player).pack(side="left", fill="x", expand=True, padx=(0, 2))
        ttk.Button(btn_row, text="- Remove", command=self._remove_player).pack(side="left", fill="x", expand=True, padx=(2, 0))

        # --- Right: editor ---
        right = ttk.Frame(pane)
        pane.add(right)

        self._editing_label = ttk.Label(right, text="Select a player", font=("Segoe UI", 10, "bold"))
        self._editing_label.pack(anchor="w", pady=(0, 6))

        tree_frame = ttk.Frame(right)
        tree_frame.pack(fill="both", expand=True)
        tree_sb = ttk.Scrollbar(tree_frame)
        tree_sb.pack(side="right", fill="y")
        self._char_tree = ttk.Treeview(
            tree_frame, columns=("char", "alt"), show="headings",
            yscrollcommand=tree_sb.set, selectmode="browse", height=8,
        )
        self._char_tree.heading("char", text="Character")
        self._char_tree.heading("alt", text="Alt #")
        self._char_tree.column("char", width=230)
        self._char_tree.column("alt", width=60)
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
        form_section.pack(fill="x", pady=(0, 4))
        form_left = ttk.Frame(form_section)
        form_left.pack(side="left")
        form_right = ttk.Frame(form_section)
        form_right.pack(side="left", padx=(12, 0), anchor="n")

        form_row = ttk.Frame(form_left)
        form_row.pack(fill="x")
        ttk.Label(form_row, text="Character:").pack(side="left")
        self._form_char = tk.StringVar()
        ttk.Combobox(
            form_row, textvariable=self._form_char,
            values=self._char_suggestions, width=20,
        ).pack(side="left", padx=(4, 12))

        ttk.Label(form_row, text="Alt #:").pack(side="left")
        self._form_alt = tk.StringVar(value="1")
        ttk.Spinbox(form_row, textvariable=self._form_alt, from_=1, to=8, width=4).pack(side="left", padx=4)

        form_btns = ttk.Frame(form_left)
        form_btns.pack(fill="x", pady=4)
        self._form_add_btn = ttk.Button(form_btns, text="Add Entry", command=self._add_char_entry)
        self._form_add_btn.pack(side="left", padx=(0, 4))
        self._form_edit_btn = ttk.Button(form_btns, text="Update Entry", command=self._update_char_entry, state="disabled")
        self._form_edit_btn.pack(side="left")
        ttk.Button(form_btns, text="Clear Form", command=self._clear_form).pack(side="left", padx=(8, 0))

        self._form_char.trace_add("write", self._update_char_preview)
        self._form_alt.trace_add("write", self._update_char_preview)

        self._preview_photo = None
        _preview_container = tk.Frame(form_right, width=300, height=220, bg=_BG3)
        _preview_container.pack()
        _preview_container.pack_propagate(False)
        self._preview_label = tk.Label(_preview_container, bg=_BG3)
        self._preview_label.place(relx=0.5, rely=0.5, anchor="center")

        ttk.Separator(right, orient="horizontal").pack(fill="x", pady=6)

        save_row = ttk.Frame(right)
        save_row.pack(fill="x")
        ttk.Button(save_row, text="Save Player Database", command=self._save_player_db,
                   style="Accent.TButton").pack(side="left")
        ttk.Button(save_row, text="Reload from File", command=self._reload_player_db).pack(side="left", padx=(8, 0))

        self._reload_player_db()

    def _reload_player_db(self):
        self._db_header, self._db_players = load_player_db()
        self._refresh_player_list()
        self._clear_char_tree()
        self._editing_label.config(text="Select a player")
        self._db_selected_player = None

    def _refresh_player_list(self):
        query = self._player_search.get().lower()
        self._player_listbox.delete(0, "end")
        for name in self._db_players:
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
        for idx, (char, alt) in enumerate(self._db_players.get(name, [])):
            self._char_tree.insert("", "end", iid=str(idx), values=(char, alt))

    def _clear_char_tree(self):
        for row in self._char_tree.get_children():
            self._char_tree.delete(row)

    def _add_player(self):
        dialog = tk.Toplevel(self.root)
        dialog.title("Add Player")
        dialog.geometry("300x110")
        dialog.transient(self.root)
        dialog.grab_set()
        ttk.Label(dialog, text="Player name:").pack(pady=(14, 4))
        name_var = tk.StringVar()
        entry = ttk.Entry(dialog, textvariable=name_var, width=30)
        entry.pack()
        entry.focus()

        def confirm():
            name = name_var.get().strip()
            if not name:
                return
            if name in self._db_players:
                self._log(f"[Player '{name}' already exists]\n")
                dialog.destroy()
                return
            self._db_players[name] = []
            self._player_search.set("")
            self._refresh_player_list()
            all_names = list(self._player_listbox.get(0, "end"))
            if name in all_names:
                idx = all_names.index(name)
                self._player_listbox.selection_clear(0, "end")
                self._player_listbox.selection_set(idx)
                self._player_listbox.see(idx)
                self._on_player_select()
            dialog.destroy()

        entry.bind("<Return>", lambda _: confirm())
        ttk.Button(dialog, text="Add", command=confirm).pack(pady=8)

    def _remove_player(self):
        if not self._db_selected_player or self._db_selected_player not in self._db_players:
            return
        del self._db_players[self._db_selected_player]
        self._db_selected_player = None
        self._refresh_player_list()
        self._clear_char_tree()
        self._editing_label.config(text="Select a player")

    def _add_char_entry(self):
        if not self._db_selected_player:
            self._log("[Select a player first]\n")
            return
        char = self._form_char.get().strip()
        if not char:
            self._log("[Enter a character name]\n")
            return
        alt = self._form_alt.get().strip()
        self._db_players[self._db_selected_player].append((char, alt))
        self._populate_char_tree(self._db_selected_player)

    def _edit_char_entry(self):
        sel = self._char_tree.selection()
        if not sel or not self._db_selected_player:
            return
        idx = int(sel[0])
        chars = self._db_players[self._db_selected_player]
        if idx >= len(chars):
            return
        char, alt = chars[idx]
        self._form_char.set(char)
        self._form_alt.set(alt)
        self._db_selected_char_idx = idx
        self._form_add_btn.config(state="disabled")
        self._form_edit_btn.config(state="normal")

    def _update_char_entry(self):
        if self._db_selected_char_idx is None or not self._db_selected_player:
            return
        char = self._form_char.get().strip()
        alt = self._form_alt.get().strip()
        chars = self._db_players[self._db_selected_player]
        if self._db_selected_char_idx < len(chars):
            chars[self._db_selected_char_idx] = (char, alt)
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
        self._form_alt.set("1")
        self._form_add_btn.config(state="normal")
        self._form_edit_btn.config(state="disabled")
        self._db_selected_char_idx = None
        self._preview_label.config(image="")
        self._preview_photo = None

    def _on_char_tree_select(self, _event=None):
        sel = self._char_tree.selection()
        if not sel or not self._db_selected_player:
            return
        idx = int(sel[0])
        chars = self._db_players[self._db_selected_player]
        if idx < len(chars):
            char, alt = chars[idx]
            self._form_char.set(char)
            self._form_alt.set(alt)
            self._show_preview(char, alt)

    def _show_preview(self, char: str, alt: str):
        if not _PIL_AVAILABLE:
            return
        if not char or not alt:
            self._preview_label.config(image="")
            self._preview_photo = None
            return
        img_path = RENDERS_DIR / f"{char} ({alt}).png"
        if not img_path.exists():
            self._preview_label.config(image="")
            self._preview_photo = None
            return
        try:
            img = Image.open(img_path)
            w, h = img.size
            scale = min(300 / w, 220 / h)
            img = img.resize((int(w * scale), int(h * scale)), Image.LANCZOS)
            photo = ImageTk.PhotoImage(img)
            self._preview_label.config(image=photo)
            self._preview_photo = photo
        except Exception:
            self._preview_label.config(image="")
            self._preview_photo = None

    def _update_char_preview(self, *_):
        self._show_preview(self._form_char.get().strip(), self._form_alt.get().strip())

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

        self._cdb_headers: list = []
        self._cdb_entries: list = []
        self._cdb_sel_idx = None

        tree_frame = ttk.Frame(tab)
        tree_frame.pack(fill="both", expand=True, padx=10, pady=(10, 4))
        cdb_sb = ttk.Scrollbar(tree_frame)
        cdb_sb.pack(side="right", fill="y")
        self._cdb_tree = ttk.Treeview(
            tree_frame, columns=("alias", "filename"), show="headings",
            yscrollcommand=cdb_sb.set, selectmode="browse",
        )
        self._cdb_tree.heading("alias", text="Alias (in VOD names)")
        self._cdb_tree.heading("filename", text="Filename (in renders folder)")
        self._cdb_tree.column("alias", width=180)
        self._cdb_tree.column("filename", width=300)
        self._cdb_tree.pack(side="left", fill="both", expand=True)
        cdb_sb.config(command=self._cdb_tree.yview)
        self._cdb_tree.bind("<<TreeviewSelect>>", self._cdb_on_select)

        form_frame = ttk.LabelFrame(tab, text="Add / Edit Entry", padding=(8, 6))
        form_frame.pack(fill="x", padx=10, pady=4)

        row1 = ttk.Frame(form_frame)
        row1.pack(fill="x", pady=(0, 4))
        ttk.Label(row1, text="Alias:", width=12, anchor="w").pack(side="left")
        self._cdb_alias_var = tk.StringVar()
        ttk.Entry(row1, textvariable=self._cdb_alias_var, width=20).pack(side="left", padx=4)
        ttk.Label(row1, text="Filename:", width=10, anchor="w").pack(side="left", padx=(8, 0))
        self._cdb_filename_var = tk.StringVar()
        ttk.Entry(row1, textvariable=self._cdb_filename_var, width=28).pack(side="left", padx=4)

        btn_row = ttk.Frame(form_frame)
        btn_row.pack(fill="x", pady=(0, 2))
        self._cdb_add_btn = ttk.Button(btn_row, text="Add Entry", command=self._cdb_add)
        self._cdb_add_btn.pack(side="left", padx=(0, 4))
        self._cdb_update_btn = ttk.Button(btn_row, text="Update Entry", command=self._cdb_update, state="disabled")
        self._cdb_update_btn.pack(side="left", padx=(0, 4))
        ttk.Button(btn_row, text="Remove Selected", command=self._cdb_remove).pack(side="left", padx=(0, 4))
        ttk.Button(btn_row, text="Clear Form", command=self._cdb_clear_form).pack(side="left")

        ttk.Separator(tab, orient="horizontal").pack(fill="x", padx=10, pady=4)

        save_row = ttk.Frame(tab)
        save_row.pack(fill="x", padx=10, pady=(0, 8))
        ttk.Button(save_row, text="Save Character Database", command=self._cdb_save,
                   style="Accent.TButton").pack(side="left")
        ttk.Button(save_row, text="Reload from File", command=self._cdb_reload).pack(side="left", padx=(8, 0))

        self._cdb_reload()

    def _cdb_reload(self):
        self._cdb_headers, self._cdb_entries = load_char_db()
        self._cdb_refresh()

    def _cdb_refresh(self):
        for row in self._cdb_tree.get_children():
            self._cdb_tree.delete(row)
        for idx, (alias, filename) in enumerate(self._cdb_entries):
            self._cdb_tree.insert("", "end", iid=str(idx), values=(alias, filename))

    def _cdb_on_select(self, _event=None):
        sel = self._cdb_tree.selection()
        if not sel:
            return
        idx = int(sel[0])
        self._cdb_sel_idx = idx
        alias, filename = self._cdb_entries[idx]
        self._cdb_alias_var.set(alias)
        self._cdb_filename_var.set(filename)
        self._cdb_add_btn.config(state="disabled")
        self._cdb_update_btn.config(state="normal")

    def _cdb_add(self):
        alias = self._cdb_alias_var.get().strip()
        filename = self._cdb_filename_var.get().strip()
        if not alias or not filename:
            self._log("[Alias and filename are required]\n")
            return
        self._cdb_entries.append((alias, filename))
        self._cdb_refresh()
        idx = len(self._cdb_entries) - 1
        self._cdb_tree.selection_set(str(idx))
        self._cdb_tree.see(str(idx))

    def _cdb_update(self):
        if self._cdb_sel_idx is None:
            return
        alias = self._cdb_alias_var.get().strip()
        filename = self._cdb_filename_var.get().strip()
        if not alias or not filename:
            self._log("[Alias and filename are required]\n")
            return
        self._cdb_entries[self._cdb_sel_idx] = (alias, filename)
        self._cdb_refresh()
        self._cdb_clear_form()

    def _cdb_remove(self):
        sel = self._cdb_tree.selection()
        if not sel:
            return
        idx = int(sel[0])
        self._cdb_entries.pop(idx)
        self._cdb_refresh()
        self._cdb_clear_form()

    def _cdb_clear_form(self):
        self._cdb_alias_var.set("")
        self._cdb_filename_var.set("")
        self._cdb_sel_idx = None
        self._cdb_add_btn.config(state="normal")
        self._cdb_update_btn.config(state="disabled")

    def _cdb_save(self):
        try:
            save_char_db(self._cdb_headers, self._cdb_entries)
            self._log("[Character database saved]\n")
        except Exception as exc:
            self._log(f"[Error saving character database: {exc}]\n")

    # ------------------------------------------------------------------ #
    #  Process runner                                                     #
    # ------------------------------------------------------------------ #
    def _run(self, cmd: list):
        def worker():
            self._log(f"> {' '.join(str(c) for c in cmd)}\n")
            try:
                proc = subprocess.Popen(
                    cmd, cwd=str(ROOT),
                    stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                    text=True, bufsize=1,
                )
                for line in proc.stdout:
                    self._log(line)
                proc.wait()
                self._log(f"[Done — exit {proc.returncode}]\n\n")
            except Exception as exc:
                self._log(f"[Error: {exc}]\n\n")
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
    app = MeleeGUI(root)
    root.mainloop()
