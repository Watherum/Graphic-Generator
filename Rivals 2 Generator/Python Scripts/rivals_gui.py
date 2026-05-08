#!/usr/bin/env python3
"""GUI launcher for the Rivals 2 Generator toolset."""
import tkinter as tk
from tkinter import ttk, scrolledtext
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

ROOT = Path(__file__).parent.parent
PYTHON = sys.executable
THUMBNAIL_SCRIPT = ROOT / "Python Scripts" / "generate_rivals_thumbnail.py"
RENDERS_DIR = ROOT / "Resources" / "Character_Renders" / "Rivals 2 Full Renders"
PLAYER_DB_PATH = ROOT / "Resources" / "Player_database.csv"
CHAR_DB_PATH   = ROOT / "Resources" / "Character_database.csv"

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


def get_skins_for_char(char_name: str) -> list[str]:
    abbrev = CHAR_ABBREVS.get(char_name)
    if not abbrev or not RENDERS_DIR.exists():
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
    },
    {
        "label": "Straight Into The Abyss",
        "slug_template": "tournament/straight-into-the-abyss-{n}/event/rivals-2-singles",
        "name_template": "Straight Into The Abyss {n}",
        "default_num": "47",
        "default_link": "https://start.gg/SITA{n}",
        "top8_file": "Straight Into The Abyss Top 8 HTML.txt",
    },
]



class RivalsGUI:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title("Rivals 2 Generator")
        self.root.geometry("720x640")
        self.root.resizable(True, True)

        notebook = ttk.Notebook(root)
        notebook.pack(fill="both", expand=True, padx=10, pady=(10, 5))

        self._build_fetch_tab(notebook)
        self._build_thumbnails_tab(notebook)
        self._build_renders_tab(notebook)
        self._build_player_db_tab(notebook)
        self._build_char_db_tab(notebook)

        # Shared console
        console_frame = tk.LabelFrame(root, text="Console Output")
        console_frame.pack(fill="both", expand=True, padx=10, pady=(0, 5))

        self.console = scrolledtext.ScrolledText(
            console_frame, height=10, state="disabled",
            bg="#1e1e1e", fg="#d4d4d4", font=("Consolas", 9),
            wrap="word",
        )
        self.console.pack(fill="both", expand=True, padx=5, pady=5)

        footer = tk.Frame(root)
        footer.pack(fill="x", padx=10, pady=(0, 8))
        tk.Button(footer, text="Clear Console", command=self._clear_console).pack(side="right")

    # ------------------------------------------------------------------ #
    #  Tab: Fetch from start.gg                                           #
    # ------------------------------------------------------------------ #
    def _build_fetch_tab(self, notebook: ttk.Notebook):
        tab = tk.Frame(notebook)
        notebook.add(tab, text="Fetch from start.gg")

        self._fetch_widgets = {}

        for cfg in FETCH_EVENTS:
            lf = tk.LabelFrame(tab, text=cfg["label"], padx=8, pady=6)
            lf.pack(fill="x", padx=10, pady=8)

            row1 = tk.Frame(lf)
            row1.pack(fill="x", pady=(0, 4))

            tk.Label(row1, text="Event #:").pack(side="left")
            num_var = tk.StringVar(value=cfg["default_num"])
            tk.Entry(row1, textvariable=num_var, width=6).pack(side="left", padx=(4, 16))

            tk.Label(row1, text="Top 8 Link:").pack(side="left")
            link_var = tk.StringVar(value=cfg["default_link"].replace("{n}", cfg["default_num"]))
            tk.Entry(row1, textvariable=link_var, width=32).pack(side="left", padx=4)

            # Auto-fill link when number changes
            def _on_num_change(name, index, mode, nv=num_var, lv=link_var, t=cfg["default_link"]):
                lv.set(t.replace("{n}", nv.get().strip()))
            num_var.trace_add("write", _on_num_change)

            row2 = tk.Frame(lf)
            row2.pack(fill="x")

            btn_sets = tk.Button(
                row2, text="Fetch VOD Names",
                command=lambda c=cfg, nv=num_var: self._fetch_sets(c, nv.get().strip()),
            )
            btn_sets.pack(side="left", padx=(0, 6))

            btn_top8 = tk.Button(
                row2, text="Fetch Top 8",
                command=lambda c=cfg, nv=num_var, lv=link_var: self._fetch_top8(
                    c, nv.get().strip(), lv.get().strip()
                ),
            )
            btn_top8.pack(side="left")

            self._fetch_widgets[cfg["label"]] = {"num": num_var, "link": link_var}

        # Custom tournament section
        lf_custom = tk.LabelFrame(tab, text="Custom Tournament", padx=8, pady=6)
        lf_custom.pack(fill="x", padx=10, pady=(0, 8))

        row_slug = tk.Frame(lf_custom)
        row_slug.pack(fill="x", pady=(0, 4))
        tk.Label(row_slug, text="Slug:", width=10, anchor="w").pack(side="left")
        self._custom_slug = tk.StringVar()
        tk.Entry(row_slug, textvariable=self._custom_slug, width=52).pack(side="left", padx=4)
        tk.Label(row_slug, text="e.g. tournament/my-event/event/singles",
                 fg="gray").pack(side="left", padx=(4, 0))

        row_name = tk.Frame(lf_custom)
        row_name.pack(fill="x", pady=(0, 4))
        tk.Label(row_name, text="Name:", width=10, anchor="w").pack(side="left")
        self._custom_name = tk.StringVar()
        tk.Entry(row_name, textvariable=self._custom_name, width=36).pack(side="left", padx=4)

        row_out = tk.Frame(lf_custom)
        row_out.pack(fill="x", pady=(0, 4))
        tk.Label(row_out, text="Output file:", width=10, anchor="w").pack(side="left")
        self._custom_out = tk.StringVar()
        tk.Entry(row_out, textvariable=self._custom_out, width=36).pack(side="left", padx=4)
        tk.Label(row_out, text="(saved in Vod_Names/ if no path given)",
                 fg="gray").pack(side="left", padx=(4, 0))

        # Auto-fill output filename when name changes
        def _on_custom_name_change(*_):
            name = self._custom_name.get().strip()
            if name and not self._custom_out.get().strip():
                self._custom_out.set(f"{name} Names.txt")
        self._custom_name.trace_add("write", _on_custom_name_change)

        tk.Button(lf_custom, text="Fetch VOD Names",
                  command=self._fetch_custom_sets).pack(anchor="w")

    def _fetch_custom_sets(self):
        slug = self._custom_slug.get().strip()
        name = self._custom_name.get().strip()
        out  = self._custom_out.get().strip()
        if not slug:
            self._log("[Error: slug is required]\n")
            return
        if not out:
            self._log("[Error: output filename is required]\n")
            return
        # Prepend Vod_Names/ if the user gave just a filename (no path separator)
        from pathlib import PurePath
        if "/" not in out and "\\" not in out:
            out = str(ROOT / "Vod_Names" / out)
        cmd = [PYTHON, str(ROOT / "Python Scripts" / "fetch_sets.py"), slug]
        if name:
            cmd += ["--name", name]
        cmd += ["--out", out]
        self._run(cmd)

    def _fetch_sets(self, cfg: dict, n: str):
        name = cfg["name_template"].format(n=n)
        slug = cfg["slug_template"].format(n=n)
        out  = str(ROOT / "Vod_Names" / f"{name} Names.txt")
        self._run([
            PYTHON, str(ROOT / "Python Scripts" / "fetch_sets.py"),
            slug, "--name", name, "--out", out,
        ])

    def _fetch_top8(self, cfg: dict, n: str, link: str):
        name = cfg["name_template"].format(n=n)
        slug = cfg["slug_template"].format(n=n)
        out  = str(ROOT / "Top_8_Texts" / cfg["top8_file"])
        self._run([
            PYTHON, str(ROOT / "Python Scripts" / "fetch_startgg_top8.py"),
            slug, "--name", name, "--link", link, "--out", out,
        ])

    # ------------------------------------------------------------------ #
    #  Tab: Generate Thumbnails                                           #
    # ------------------------------------------------------------------ #
    def _build_thumbnails_tab(self, notebook: ttk.Notebook):
        tab = tk.Frame(notebook)
        notebook.add(tab, text="Generate Thumbnails")

        lf = tk.LabelFrame(tab, text="Event", padx=8, pady=8)
        lf.pack(fill="x", padx=10, pady=10)

        row1 = tk.Frame(lf)
        row1.pack(fill="x", pady=(0, 6))

        tk.Label(row1, text="Series:").pack(side="left")
        self._thumb_series = tk.StringVar()
        self._thumb_series_box = ttk.Combobox(
            row1, textvariable=self._thumb_series,
            state="readonly", width=26,
        )
        self._thumb_series_box.pack(side="left", padx=(4, 4))
        tk.Button(row1, text="↺", width=2,
                  command=self._refresh_thumbnail_events).pack(side="left", padx=(0, 12))

        tk.Label(row1, text="# / Suffix:").pack(side="left")
        self._thumb_num = tk.StringVar(value="274")
        tk.Entry(row1, textvariable=self._thumb_num, width=8).pack(side="left", padx=4)

        row2 = tk.Frame(lf)
        row2.pack(fill="x", pady=(0, 6))

        tk.Label(row2, text="Event name:").pack(side="left")
        self._thumb_event_name = tk.StringVar()
        tk.Entry(row2, textvariable=self._thumb_event_name, width=40).pack(side="left", padx=4)

        def _update_name(*_):
            template = self._thumb_event_map.get(self._thumb_series.get(), "{n}")
            self._thumb_event_name.set(template.format(n=self._thumb_num.get().strip()))

        self._thumb_series.trace_add("write", _update_name)
        self._thumb_num.trace_add("write", _update_name)
        self._thumb_update_name = _update_name

        self._refresh_thumbnail_events()

        tk.Button(tab, text="Generate Thumbnails", command=self._generate_thumbnails,
                  width=22).pack(padx=10, pady=4, anchor="w")

    def _refresh_thumbnail_events(self):
        events = load_thumbnail_events()
        self._thumb_event_map = {name: tmpl for name, tmpl in events}
        names = [name for name, _ in events]
        self._thumb_series_box["values"] = names
        if names and self._thumb_series.get() not in names:
            self._thumb_series.set(names[0])
        self._thumb_update_name()

    def _generate_thumbnails(self):
        event_name = self._thumb_event_name.get().strip()
        if not event_name:
            self._log("[Error: event name is empty]\n")
            return
        self._run([
            PYTHON, str(ROOT / "Python Scripts" / "generate_rivals_thumbnail.py"),
            "-e", event_name, "-o", "missing.log",
        ])

    # ------------------------------------------------------------------ #
    #  Tab: Character Renders                                             #
    # ------------------------------------------------------------------ #
    def _build_renders_tab(self, notebook: ttk.Notebook):
        tab = tk.Frame(notebook)
        notebook.add(tab, text="Character Renders")

        lf = tk.LabelFrame(tab, text="Manage Renders", padx=10, pady=10)
        lf.pack(fill="x", padx=10, pady=10)

        tk.Label(lf, text="Download render images from dragdown.wiki or copy them to the Full Renders folder.",
                 wraplength=560, justify="left").pack(anchor="w", pady=(0, 8))

        btn_cfg = [
            ("Download & Copy",     self._download_and_copy),
            ("Download Renders",    self._download_renders),
            ("Copy to Full Renders",self._copy_renders),
        ]
        for label, cmd in btn_cfg:
            tk.Button(lf, text=label, width=22, command=cmd).pack(pady=3, anchor="w")

    def _download_renders(self):
        self._run([PYTHON, str(ROOT / "Python Scripts" / "download_rivals_renders.py")])

    def _copy_renders(self):
        self._run([PYTHON, str(ROOT / "Python Scripts" / "copy_rivals_renders_to_full.py")])

    def _download_and_copy(self):
        self._run_sequential(
            [PYTHON, str(ROOT / "Python Scripts" / "download_rivals_renders.py")],
            [PYTHON, str(ROOT / "Python Scripts" / "copy_rivals_renders_to_full.py")],
        )

    # ------------------------------------------------------------------ #
    #  Tab: Player Database                                               #
    # ------------------------------------------------------------------ #
    def _build_player_db_tab(self, notebook: ttk.Notebook):
        tab = tk.Frame(notebook)
        notebook.add(tab, text="Player Database")

        self._db_header: list[str] = []
        self._db_players: dict[str, list[tuple[str, str]]] = {}
        self._db_selected_player: str | None = None
        self._db_selected_char_idx: int | None = None
        self._skin_stems: list[str] = []

        # Two-pane layout
        pane = tk.PanedWindow(tab, orient="horizontal", sashrelief="raised")
        pane.pack(fill="both", expand=True, padx=10, pady=10)

        # --- Left: player list ---
        left = tk.Frame(pane)
        pane.add(left, width=190)

        tk.Label(left, text="Players", font=("TkDefaultFont", 10, "bold")).pack(anchor="w", pady=(0, 2))

        self._player_search = tk.StringVar()
        tk.Entry(left, textvariable=self._player_search).pack(fill="x", pady=(0, 4))
        self._player_search.trace_add("write", lambda *_: self._refresh_player_list())

        lb_frame = tk.Frame(left)
        lb_frame.pack(fill="both", expand=True)
        lb_sb = tk.Scrollbar(lb_frame)
        lb_sb.pack(side="right", fill="y")
        self._player_listbox = tk.Listbox(lb_frame, yscrollcommand=lb_sb.set, selectmode="single", activestyle="dotbox")
        self._player_listbox.pack(side="left", fill="both", expand=True)
        lb_sb.config(command=self._player_listbox.yview)
        self._player_listbox.bind("<<ListboxSelect>>", self._on_player_select)

        btn_row = tk.Frame(left)
        btn_row.pack(fill="x", pady=(6, 0))
        tk.Button(btn_row, text="+ Add", command=self._add_player).pack(side="left", fill="x", expand=True, padx=(0, 2))
        tk.Button(btn_row, text="- Remove", command=self._remove_player).pack(side="left", fill="x", expand=True, padx=(2, 0))

        # --- Right: editor ---
        right = tk.Frame(pane)
        pane.add(right)

        self._editing_label = tk.Label(right, text="Select a player", font=("TkDefaultFont", 10, "bold"))
        self._editing_label.pack(anchor="w", pady=(0, 6))

        # Treeview
        tree_frame = tk.Frame(right)
        tree_frame.pack(fill="both", expand=True)
        tree_sb = tk.Scrollbar(tree_frame)
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

        tree_btns = tk.Frame(right)
        tree_btns.pack(fill="x", pady=4)
        tk.Button(tree_btns, text="Edit Selected", command=self._edit_char_entry).pack(side="left", padx=(0, 4))
        tk.Button(tree_btns, text="Remove Selected", command=self._remove_char_entry).pack(side="left")
        tk.Button(tree_btns, text="Move Up", command=lambda: self._move_char_entry(-1)).pack(side="right", padx=(4, 0))
        tk.Button(tree_btns, text="Move Down", command=lambda: self._move_char_entry(1)).pack(side="right")

        ttk.Separator(right, orient="horizontal").pack(fill="x", pady=6)

        tk.Label(right, text="Add / Edit Entry", font=("TkDefaultFont", 9, "bold")).pack(anchor="w", pady=(0, 4))

        form_section = tk.Frame(right)
        form_section.pack(fill="x")
        form_left = tk.Frame(form_section)
        form_left.pack(side="left", fill="y")
        form_right = tk.Frame(form_section)
        form_right.pack(side="left", padx=(12, 0), anchor="n")

        form_row = tk.Frame(form_left)
        form_row.pack(fill="x")
        tk.Label(form_row, text="Character:").pack(side="left")
        self._form_char = tk.StringVar()
        ttk.Combobox(
            form_row, textvariable=self._form_char, values=CHARACTERS, state="readonly", width=14,
        ).pack(side="left", padx=(4, 12))
        self._form_char.trace_add("write", self._on_form_char_change)

        tk.Label(form_row, text="Skin:").pack(side="left")
        self._form_skin_var = tk.StringVar()
        self._form_skin_box = ttk.Combobox(form_row, textvariable=self._form_skin_var, state="readonly", width=30)
        self._form_skin_box.pack(side="left", padx=4)
        self._form_skin_var.trace_add("write", self._on_form_skin_change)

        form_btns = tk.Frame(form_left)
        form_btns.pack(fill="x", pady=4)
        self._form_add_btn = tk.Button(form_btns, text="Add Entry", command=self._add_char_entry)
        self._form_add_btn.pack(side="left", padx=(0, 4))
        self._form_edit_btn = tk.Button(form_btns, text="Update Entry", command=self._update_char_entry, state="disabled")
        self._form_edit_btn.pack(side="left")
        tk.Button(form_btns, text="Clear Form", command=self._clear_form).pack(side="left", padx=(8, 0))

        self._preview_label = tk.Label(form_right, bg="#111111", width=11, height=9)
        self._preview_label.pack()
        self._preview_img = None

        ttk.Separator(right, orient="horizontal").pack(fill="x", pady=6)

        save_row = tk.Frame(right)
        save_row.pack(fill="x")
        tk.Button(save_row, text="Save Player Database", command=self._save_player_db,
                  bg="#2d6a2d", fg="white", width=22).pack(side="left")
        tk.Button(save_row, text="Reload from File", command=self._reload_player_db).pack(side="left", padx=(8, 0))

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
        for idx, (char, skin) in enumerate(self._db_players.get(name, [])):
            lbl = skin_label(skin) if skin else "(none)"
            self._char_tree.insert("", "end", iid=str(idx), values=(char, lbl))

    def _clear_char_tree(self):
        for row in self._char_tree.get_children():
            self._char_tree.delete(row)

    def _add_player(self):
        dialog = tk.Toplevel(self.root)
        dialog.title("Add Player")
        dialog.geometry("300x110")
        dialog.transient(self.root)
        dialog.grab_set()
        tk.Label(dialog, text="Player name:").pack(pady=(14, 4))
        name_var = tk.StringVar()
        entry = tk.Entry(dialog, textvariable=name_var, width=30)
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
            self._player_search.set("")  # clear filter so new player is visible
            self._refresh_player_list()
            # find position in the (now unfiltered) listbox
            all_names = list(self._player_listbox.get(0, "end"))
            if name in all_names:
                idx = all_names.index(name)
                self._player_listbox.selection_clear(0, "end")
                self._player_listbox.selection_set(idx)
                self._player_listbox.see(idx)
                self._on_player_select()
            dialog.destroy()

        entry.bind("<Return>", lambda _: confirm())
        tk.Button(dialog, text="Add", command=confirm).pack(pady=8)

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
        if not skin_stem:
            self._clear_preview()
            return
        path = RENDERS_DIR / f"{skin_stem}.png"
        if not path.exists():
            self._clear_preview()
            return
        try:
            img = Image.open(path)
            h = 130
            w = round(img.width * h / img.height)
            img = img.resize((w, h), Image.LANCZOS)
            self._preview_img = ImageTk.PhotoImage(img)
            self._preview_label.config(image=self._preview_img, width=w, height=h)
        except Exception:
            self._clear_preview()

    def _clear_preview(self):
        self._preview_img = None
        self._preview_label.config(image="", width=11, height=9)

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
        tab = tk.Frame(notebook)
        notebook.add(tab, text="Character Database")

        self._cdb_headers: list[str] = []
        self._cdb_chars: list[str] = []

        top = tk.Frame(tab)
        top.pack(fill="both", expand=True, padx=10, pady=(10, 4))

        tk.Label(top, text="Characters", font=("TkDefaultFont", 10, "bold")).pack(anchor="w", pady=(0, 2))

        list_frame = tk.Frame(top)
        list_frame.pack(fill="both", expand=True)
        cdb_sb = tk.Scrollbar(list_frame)
        cdb_sb.pack(side="right", fill="y")
        self._cdb_listbox = tk.Listbox(
            list_frame, yscrollcommand=cdb_sb.set,
            selectmode="single", activestyle="dotbox", width=34,
        )
        self._cdb_listbox.pack(side="left", fill="both", expand=True)
        cdb_sb.config(command=self._cdb_listbox.yview)

        btn_row = tk.Frame(tab)
        btn_row.pack(fill="x", padx=10, pady=4)
        tk.Button(btn_row, text="+ Add",    command=self._cdb_add).pack(side="left", padx=(0, 4))
        tk.Button(btn_row, text="Rename",   command=self._cdb_rename).pack(side="left", padx=(0, 4))
        tk.Button(btn_row, text="- Remove", command=self._cdb_remove).pack(side="left")
        tk.Button(btn_row, text="Move Up",   command=lambda: self._cdb_move(-1)).pack(side="right", padx=(4, 0))
        tk.Button(btn_row, text="Move Down", command=lambda: self._cdb_move(1)).pack(side="right")

        ttk.Separator(tab, orient="horizontal").pack(fill="x", padx=10, pady=4)

        save_row = tk.Frame(tab)
        save_row.pack(fill="x", padx=10, pady=(0, 8))
        tk.Button(save_row, text="Save Character Database", command=self._cdb_save,
                  bg="#2d6a2d", fg="white", width=24).pack(side="left")
        tk.Button(save_row, text="Reload from File", command=self._cdb_reload).pack(side="left", padx=(8, 0))

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
        dialog = tk.Toplevel(self.root)
        dialog.title("Add Character")
        dialog.geometry("280x110")
        dialog.transient(self.root)
        dialog.grab_set()
        tk.Label(dialog, text="Character name:").pack(pady=(14, 4))
        name_var = tk.StringVar()
        entry = tk.Entry(dialog, textvariable=name_var, width=28)
        entry.pack()
        entry.focus()

        def confirm():
            name = name_var.get().strip()
            if not name:
                return
            if name in self._cdb_chars:
                self._log(f"['{name}' already in character database]\n")
                dialog.destroy()
                return
            self._cdb_chars.append(name)
            self._cdb_refresh()
            idx = len(self._cdb_chars) - 1
            self._cdb_listbox.selection_set(idx)
            self._cdb_listbox.see(idx)
            dialog.destroy()

        entry.bind("<Return>", lambda _: confirm())
        tk.Button(dialog, text="Add", command=confirm).pack(pady=8)

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
        tk.Label(dialog, text="New name:").pack(pady=(14, 4))
        name_var = tk.StringVar(value=old_name)
        entry = tk.Entry(dialog, textvariable=name_var, width=28)
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
        tk.Button(dialog, text="Rename", command=confirm).pack(pady=8)

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

    def _run_sequential(self, *cmds: list):
        def worker():
            for cmd in cmds:
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
