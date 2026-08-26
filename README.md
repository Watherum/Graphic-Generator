# Graphic Generator

Batch image generator for Rivals 2 esports — creates YouTube thumbnails, Top 8 bracket graphics, and results posts for weekly events. Originally based on work by CR_Jetstream; now primarily focused on Rivals 2. Ultimate and Melee generators are also included and share the same Qt GUI and feature set.

## Requirements

- **Python 3.12** — install from [python.org](https://www.python.org/downloads/) if not already present
- Run `requirments_install.cmd` once to install Python dependencies

## Updating

Requires [Git for Windows](https://git-scm.com/download/win). Every method stashes your local changes (generated outputs, VOD name files, databases, settings), pulls the latest source, then restores your changes — so updating won't clobber your data. There are three ways:

- **Update everything** — run `update_all_generators.cmd` from the repo root to pull the latest code for all three generators at once.
- **Update one game** — run `update.cmd` inside that generator's folder (e.g. `Rivals_2_Generator\update.cmd`) to update only that generator and leave the others untouched.
- **From the GUI** — open the **Update** tab in any generator's GUI, click **Check for Updates**, then **Update Now**. You'll be prompted to restart the app afterwards so the new version loads.

---

## GUI (Recommended)

Double-click the VBS launcher for the game you want:

```
Rivals_2_Generator\Launch_Rivals_GUI.vbs
Ultimate_Generator\Launch_Ultimate_GUI.vbs
Melee_Generator\Launch_Melee_GUI.vbs
```

The **Ultimate** and **Melee** generators have the same Qt GUI, the same tabs and the
same features — including per-set costume overrides, the preferred-costume marker, the
live thumbnail preview in Thumbnail Config, and the embedded Top 8 preview with its PNG
export. The remaining game-specific differences:

- Costumes are **numbered 1–8** (rather than Rivals' named skins) everywhere they appear:
  in the Player Database, the costume pickers, and the `Character:Alt` override syntax
- The **Character Database** is a two-column `alias → render filename` mapping rather than a single-column name list
- The **Character Renders** tab simply opens the full render folder (the dragdown.wiki downloader is Rivals-only)
- Per-event thumbnail overrides save to `ultimate_event_configs.json` / `melee_event_configs.json` respectively
- **Rivals-only:** the dragdown.wiki render downloader and the parry.gg fetchers

The Rivals 2 GUI has eight tabs:

---

### 1. Fetch From Start.gg

Pull match data and top 8 standings directly from start.gg.

Each tournament series is shown in a **collapsible panel** — click the header to expand/collapse it. Collapsed/expanded state is remembered between sessions.

**Preset Tournaments** (Immortal Fight Night, Straight Into The Abyss)
- Enter the event number and top 8 link
- Optionally set an **Abbrev** (e.g. `IFN`) — see *Tournament abbreviations* below
- Click **Fetch VOD Names** or **Fetch Top 8**
- Event numbers, links, and abbreviations are saved automatically between sessions

**Saved Custom Tournaments**
- Custom tournaments you've previously added appear here as their own sections
- Each shows an Event # field, Top 8 Link field, an **Abbrev** field, and **Fetch VOD Names** / **Fetch Top 8** / **Delete** buttons
- Event numbers, top 8 links, and abbreviations are saved automatically between sessions

**Add New Custom Tournament**
- Enter a slug template (use `{n}` as a placeholder for the event number, e.g. `tournament/my-event-{n}/event/rivals-2-singles`) — pasting a full start.gg URL is also accepted and automatically trimmed down to the slug
- Enter a series name (e.g. `My Weekly`)
- Optionally enter an **Abbrev** for the series
- Enter a starting event number
- Click **Save & Fetch VOD Names** — the tournament is saved and will appear in Saved Custom Tournaments on future boots

> **Fetch Top 8** always writes to both the event-specific text file and `Top_8_Texts/Default Top 8 HTML.txt`, keeping the default template in sync with the latest event.

#### Tournament abbreviations

YouTube limits video titles to 100 characters. Each VOD match line begins with the full tournament name, and long names plus long player tags can push a line over that limit.

Set a short **Abbrev** for a series (e.g. `IFN` for *Immortal Fight Night*) and the event number is appended automatically (`IFN 274`). When fetching VOD names, any line that would exceed 100 characters has its tournament name swapped for the abbreviation; lines that already fit keep the full name. Thumbnails still generate correctly from abbreviated lines — the abbreviation only shortens the title, and the full series name is still drawn on the graphic.

---

### 2. Generate Thumbnails

**Event selector**
- Choose a series from the dropdown (includes preset and saved custom tournaments)
- Enter the event number/suffix — the full event name is built automatically

**Thumbnail Config** *(collapsible, starts collapsed)*

Configure rendering for the selected series. Settings are saved per-series to `rivals_event_configs.json` and applied at generation time on top of any hardcoded defaults.

| Field | Description |
|---|---|
| Background / Foreground | Browse to select an image — copied to `Resources/Overlays/` automatically |
| Font | Choose from fonts in `Resources/Fonts/` |
| Character Glow | Toggle glow effect on character renders |
| One Character Per Player | Limit each player slot to a single character |
| Single Text Block | Draw both players' names as one block instead of two |
| Separator | Text drawn between the two players (e.g. `Vs`) |
| Char Scale | Resize multipliers for 1-char, 2-char, and 3-char layouts |
| Char Window | Width/height of the area characters are fitted into |
| Character Positions | x/y center-shift values (normalized −1 to 1) per 1/2/3-char layout |
| Character Offsets | Per-side x/y nudge (P1 / P2) applied on top of the layout shift |
| Text Label Positions | Normalized x/y for the Player 1, Player 2, Event and Round labels |
| Font Sizes | Player 1, Player 2, Event, Round, and rotation Angle° |
| Font Colors | Separate hex entry + colour picker for P1, P2, Event and Round |
| Save Config / Clear Config | Write or remove the override for the current series |

Every field on a normalized scale (the shifts, offsets, text positions, char window and
char scales) is a **slider paired with a number box**. Drag for a rough value or type an
exact one — the box wins, so a value outside the slider's range is kept verbatim and the
handle simply parks at the end. The scroll wheel is deliberately ignored by these sliders
and by the Series/VOD File dropdowns, so scrolling through a long form can't silently
change a value.

**Live preview**

The config box ends with a preview that renders a real thumbnail from the **form fields as
they stand, saved or not** — so a normalized shift can be judged by eye before committing
it.

- **Preview** dropdown picks the sample: the selected VOD line, or a synthetic 1/2/3-character
  match using placeholder players
- Edits repaint automatically a moment after you stop typing; **Refresh** forces a redraw
- Selecting a different VOD row redraws on its own — no need to press Refresh
- **Drawn from:** above the image names the line that was actually rendered. A selected row
  that is a comment, a header or an unparseable line falls back to the first real match, and
  this is how you can tell
- **Open Full Size** opens the render at full resolution

It runs the real generator, so the preview can't drift from real output — it just stops
after the first character arrangement instead of drawing all six.

**VOD Names** *(collapsible)*

View and edit match data files without leaving the GUI.

- Dropdown shows only files matching the selected series, sorted by event number (highest first)
- Click ⟳ to rescan the folder
- Edit lines directly in the table — **edits auto-save** a moment after you stop typing
  (`[Auto-saved: …]` appears in the console); a manual **Save** button is still there
- The **Len** column shows the exact length of what the **Copy** button would put on the
  clipboard — measured *after* skins are stripped and the series abbreviation is applied.
  It turns red only when a line is still over 100 characters even once abbreviated, which
  is the only case that needs action
- Each row has its own **Copy** button and **↑ / ↓** buttons to reorder lines (clear the
  filter first — reordering a filtered view is blocked)
- Right-click a row for **Copy line**, **Set skins…** and **Delete line**
- Tick rows and use **Delete Marked** to remove them, or **Delete Unmarked** to keep only the ticked rows
- **Search match lines** filter bar narrows the table live as you type; generating while filtered only processes the visible lines. Clearing the filter re-highlights whatever row was selected
- Rows for VS-lines with missing character data are **highlighted red**; fixing a red line auto-saves it and logs the fix to the console
- **Import Missing Players** (enabled only when red rows exist) jumps to the Player Database tab to fill in the missing entries
- **Add Missing Skins** writes every skin named in the loaded lines onto that player's row
  in the player database. It stays greyed out until every player in the lines has a row —
  a skin has nowhere to go otherwise, and the tooltip names who is missing
- **Generate Thumbnails** is disabled until every VS-line has valid character data
- Double-clicking a line places the cursor inside the first empty `()` so character names can be typed immediately
- **Character** and **Skin** pickers with a full-size render preview: choosing either copies
  a `Character` or `Character:Skin` token to the clipboard, ready to paste into a line.
  Changing the character clears the skin box, since its labels belonged to the old character

Click **Generate Thumbnails** to run the pipeline. Output goes to `Youtube_Thumbnails/{Event Name}/`. Missing player/character lookups are logged to `Vod_Names/missing.log`.

#### Per-set skins

A player's row in the database gives their usual skin for each character, but players
change skins between sets. Any character in a match line may carry a skin for that set
after a colon:

```
Immortal Fight Night 290 - Grand Final - Average Alex (Ranno:Abyss Midnight) Vs Grunk (Zetterburn) - RoA II
```

- The label is the friendly name shown in the Skin dropdown (`Abyss Midnight`), matched
  case-insensitively. It may name **any** skin on disk, not just one in the player's row
- Every character in a set can carry its own skin, on both sides:
  `Average Alex (Ranno:Abyss Midnight, Clairen:Leopard Pink, Kragg) Vs Grunk (Zetterburn:Default Blue)`
- Omit the `:Skin` and the player's preferred skin is used — which is what every line
  written before this feature does, so nothing changed for existing files
- An unrecognised label falls back to the preferred skin and is noted in the missing-entries
  log rather than failing the run
- Set them from the GUI with right-click → **Set skins…**, or by pasting a `Character:Skin`
  token from the Skin picker

**Skins never reach the YouTube title.** They are stripped from the Copy button, the Len
count and the generated filenames — `:` isn't even legal in a Windows filename.

The same override works in the Top 8 placement data; see *Generate Top 8s* below.

---

### 3. Generate Top 8s

Edit Top 8 placement data and see the bracket graphic render live.

The tab is ordered **Event → Top 8 HTML Result → Top 8 Text Data → Top 8 Preview**.

**Top 8 HTML Result** *(collapsible)*

The Top 8 graphic is a self-contained HTML file that reads the data file and renders
placements, character renders, and sponsor tags live via JavaScript. There is no separate
generation step — saving the text data is all that's needed.

- Select the HTML file for the current series from the dropdown (event-specific files plus **Default Top 8.html** are shown)
- **Open in Browser** opens it through a local web server. The page scales its 1920×1080
  canvas to fit the window, so the whole graphic is visible at any size; `Ctrl+0` in the
  browser shows it at true 1:1

**Layout Config** *(collapsible, starts collapsed)*

A visual config form for adjusting the layout of the selected HTML file without touching the raw HTML. Changes apply to whichever HTML file is currently selected.

| Section | Fields |
|---|---|
| Colors | Label color, Sponsor color (hex + color picker) |
| Event Info | Top %, Left %, Size px per field (Name / Link / Entrants / Date); color override for Name |
| Character Renders | Top %, Left %, Height % for each of the 8 placement slots |
| Placement Numbers | Top %, Left %, Size px for each slot |
| Player Names | Top %, Left %, Size px for each slot, plus a **Wrap** tick so a long name breaks onto two lines |
| Sponsors | Top %, Left %, Size px for each slot |

The four slot sections flow side by side and rewrap as the window is resized. **Edits
auto-save** a moment after you stop typing and the preview reloads to match;
**Apply Config & Save** writes immediately. Hand-added CSS and scripts in the file survive
a save — the form patches individual styles rather than regenerating the page.

**HTML Source** *(collapsible, starts collapsed)*

Raw HTML editor for direct editing. Syntax highlighted, and auto-saving like the others.

**Top 8 Text Data** *(collapsible)*

- Select a series and event number — the matching `Top_8_Texts/` file loads automatically
- Selecting **Default Top 8.html** in the HTML file dropdown loads `Default Top 8 HTML.txt` instead
- Edit placements, sponsors, and characters directly in the syntax-highlighted text area
- **Character** and **Skin** pickers with a render preview copy a `Character` or
  `Character:Skin` token to the clipboard for pasting into a placement row
- Auto-saves as you type; **Save** writes immediately

Data file format:

```
Event name:	Straight Into The Abyss 1
Event link:	https://start.gg/SITA1
Event entrants:	32 Competitors
Event date:	1/1/2025

1,Viviana,,Galvan
2,SapphireGD,AoC,Zetterburn
3,Turnap,BLZE,Ranno:Abyss Midnight
...
```

Fields per placement row: `place, player name, sponsor (blank if none), character`

The character field takes the same **`Character:Skin` override** the VOD lines use (see
*Per-set skins* above). Leave it off to use the player's preferred skin. A skin that names
no render on disk falls back to the player's usual one rather than blanking the slot.

**Top 8 Preview** *(collapsible)*

A live render of the selected HTML file, at a size worth looking at.

- Reloads itself whenever Layout Config **or** the text data saves
- **⟳ Refresh** forces a fresh load, for when something still looks stale
- **Save Image…** renders the graphic to a full-size 1920×1080 PNG and asks where to put it.
  It captures through the GUI's own browser engine, so it works whatever your default
  browser is, and needs nothing added to the HTML — any page whose graphic starts at the
  top-left corner exports correctly, including one you supplied yourself

---

### 4. Generate Posts

Fetch and edit results posts for Twitter/X or Discord from start.gg results.

- Select a series and event number
- Toggle **Next Event** to include the next event's **Date**, **Link** and **Vods link** in the post
- Click **Fetch Twitter** or **Fetch Discord** to pull standings with the matching social handles
- The generated post text appears in the editable text area
- Click **Save** to write changes back to `Results_Posts/{Event Name} {Platform} Post.txt`, or **Copy** to copy it to the clipboard

**Notes** *(collapsible)*

A free-form scratchpad kept **per series** — whatever doesn't belong in the generated post:
running order, a recurring caster note, a reminder for next week.

- Saves automatically as you type to `Results_Posts/{Series} Notes.txt`, shown above the box
- Keyed to the series, not the event number, so the notes carry over from one week's event
  to the next instead of starting empty every time. Changing the event number leaves them alone
- Switching series writes the current notes to the series they were typed for, then loads the new one's
- Clearing the notes deletes the file rather than leaving an empty one behind

---

### 5. Player Database

Add, edit, and search player entries and their character mains/alts.

- Players listed alphabetically; use the search box to filter. **+ Add** / **- Remove** manage the list
- Click a player to load their characters into the editor; clicking a character row fills the form for editing
- Add character rows with a named skin and a full-size live preview. **Add Entry** /
  **Update Entry** / **Clear Form**, plus **Edit Selected**, **Remove Selected** and
  **Move Up** / **Move Down** for the character list
- A character may be listed **more than once** to give a player several skins for it. The
  **Preferred** tick (or the **Set Preferred** button) marks which one is used when a
  match line doesn't name a skin. With nothing ticked the first listed wins, so single-skin
  players behave exactly as they always have
- All add/edit/remove/move actions **auto-save immediately** — a `[Auto-saved: player database]` line appears in the console log to confirm. **Save Player Database** and **Reload from File** are also there

Row format in `Resources/Player_database.csv` — player tag, then alternating character and
skin, with `*` marking the preferred skin:

```
Average Alex,Ranno,T_Ran_Default_Neutral_CSP,Ranno,*T_Ran_Abyss_Midnight_CSP,Clairen,T_Cla_Default_Black_CSP
```

Skin resolution order: **the `:Skin` on the match line** → **the `*` preferred skin** →
**first listed** → the character's neutral default.

*(In the Ultimate and Melee GUIs costumes are numbered 1–8 instead of named, so the
same feature reads `Mario:5` in a match line and `*5` in the database. Those generators
also still accept the older inline form, `Mario 5`; both are stripped from the YouTube
title. Their neutral default is alt 1.)*

---

### 6. Character Renders

Download and organise character render images from [dragdown.wiki](https://dragdown.wiki).

The roster is **discovered from the wiki**, not hardcoded, so newly released characters are
picked up automatically — any missing from `Character_database.csv` are added to it on
download (existing entries are never removed). Downloads are atomic, so an interrupted run
can't leave a corrupt PNG behind.

- **Download Renders** — fetch every character's CSP renders and copy them into the Full Renders folder
- **Check for New Characters** — list the wiki roster and what's missing from your character database, without downloading anything
- **Open Full Renders** — open `Resources/Character_Renders/Rivals_2_Full_Renders/` in File Explorer
- **Open Renders Source** — open the raw download folder

*(The downloader is Rivals-only; the Ultimate and Melee tabs just open the render folder.)*

---

### 7. Character Database

Manage the list of recognised character names used during thumbnail generation. Add entries
inline with **+ Add**, and use **Rename**, **- Remove** and **Move Up** / **Move Down** to
tidy the list; **Save Character Database** and **Reload from File** write and re-read
`Resources/Character_database.csv`. Changes take effect on the next thumbnail run, and the
render downloader keeps this list in sync with the wiki roster for you.

*(In the Ultimate and Melee GUIs this is a two-column `alias → render filename` table instead.)*

---

### 8. Update

Check for and install updates to this generator from GitHub without leaving the GUI.

- **Check for Updates** — compares your copy against the latest on GitHub and reports whether you're up to date
- **Update Now** — downloads and applies the update for **this generator only**; your databases and settings are preserved
- After a successful update, a prompt offers to **Restart Now** so the new version loads

Requires the project to be a Git checkout (cloned, not a downloaded ZIP). Detection ignores your local edits (databases, settings), so they never trigger a false "update available".

---

## CLI Usage

```bash
# Generate thumbnails (run from inside Rivals_2_Generator/)
python "Python_Scripts\generate_rivals_thumbnail.py" -e "Straight Into The Abyss 41"

# Log missing player/character entries to a file
python "Python_Scripts\generate_rivals_thumbnail.py" -e "Straight Into The Abyss 41" -o "Vod_Names\missing.log"

# Fetch match data from start.gg
python "Python_Scripts\fetch_sets.py" tournament/straight-into-the-abyss-41/event/rivals-2-singles --name "Straight Into The Abyss 41" --out "Vod_Names\Straight Into The Abyss 41 Names.txt"

# ...add --abbrev to shorten lines over 100 chars (writes an "# ABBREV:" header the generator reads)
python "Python_Scripts\fetch_sets.py" tournament/straight-into-the-abyss-41/event/rivals-2-singles --name "Straight Into The Abyss 41" --abbrev "SITA 41" --out "Vod_Names\Straight Into The Abyss 41 Names.txt"

# Fetch top 8 bracket data
python "Python_Scripts\fetch_startgg_top8.py" tournament/straight-into-the-abyss-41/event/rivals-2-singles --name "Straight Into The Abyss 41" --out "Top_8_Texts\Straight Into The Abyss Top 8 HTML.txt"

# Download character renders from dragdown.wiki
python "Python_Scripts\download_rivals_renders.py"
python "Python_Scripts\download_rivals_renders.py" --list-characters      # roster + what's missing from the CSV
python "Python_Scripts\download_rivals_renders.py" --characters Ranno Clairen --overwrite
```

CLI flags for `generate_rivals_thumbnail.py`:
- `-e, --event` — Event name string (required; must match a series in `populate_rivals_globals.py`)
- `-o, --output_file` — File to log missing player/character entries (omit to print to console)

**parry.gg** events are supported by their own fetchers, `fetch_parrygg_sets.py` and
`fetch_parrygg_top8.py` (wrapped by `CMD_Scripts\Fetch_Parrygg_Sets.cmd` /
`Fetch_Parrygg_Top8.cmd`). They write the same file formats as the start.gg fetchers, so
everything downstream — thumbnails, Top 8 graphics — works identically. They are not yet
wired into the GUI.

`CMD_Scripts/` and `Event_Generation/` hold ready-made batch wrappers for the established
series, if you prefer double-clicking to typing.

---

## Adding a New Tournament Series

### Via GUI (no Python required)

1. Add the tournament in the **Fetch From Start.gg** tab → Add New Custom Tournament
2. Configure overlays, fonts, and positions in the **Generate Thumbnails** tab → Thumbnail Config
3. Settings are saved to `rivals_event_configs.json` automatically

### Via Code

1. Add a config function in `Python_Scripts/populate_rivals_globals.py`:

```python
def setGlobalsMyEvent(weekly_event):
    props = {}
    props["event_name"] = weekly_event
    props["background_file"] = "Resources/Overlays/MyEvent Background.png"
    # ... populate remaining properties
    return props
```

2. Add a dispatcher branch in the `setGlobals()` function in the same file:

```python
if weekly_event.startswith("My Event"):
    return setGlobalsMyEvent(weekly_event)
```

3. Place overlay images in `Resources/Overlays/`

---

## Maintenance

| Task | How |
|---|---|
| Add new character skins | GUI → Character Renders → **Download Renders**, or place PNGs in `Resources/Character_Renders/Rivals_2_Full_Renders/` |
| Give a player a second skin | GUI → Player Database → add the character twice, tick **Preferred** on the default one |
| Use a one-off skin for one set | Right-click the VOD line → **Set skins…**, or type `Character:Skin` |
| Add new characters | GUI → Character Database tab, or edit `Resources/Character_database.csv` directly |
| Add/update players | GUI → Player Database tab |
| Add overlay images | Place in `Resources/Overlays/` or use Browse in Thumbnail Config |
| Sync renders from dragdown.wiki | GUI → Character Renders tab → Download Renders |

---

## File Layout

```
Rivals_2_Generator/
├── Launch_Rivals_GUI.vbs          # GUI entry point
├── rivals_gui_settings.json       # Persisted GUI state (event numbers, etc.)
├── rivals_custom_events.json      # User-added custom tournament series
├── rivals_event_configs.json      # Per-series thumbnail config overrides
│
├── Python_Scripts/
│   ├── rivals_gui.py              # PySide6 (Qt) GUI
│   ├── generate_rivals_thumbnail.py  # Thumbnail pipeline
│   ├── populate_rivals_globals.py    # Per-series config & dispatcher
│   ├── skin_utils.py              # Shared skin/render helpers (labels, preferred skins)
│   ├── fetch_sets.py              # start.gg match data fetcher
│   ├── fetch_startgg_top8.py      # start.gg top 8 fetcher
│   ├── fetch_parrygg_sets.py      # parry.gg match data fetcher
│   ├── fetch_parrygg_top8.py      # parry.gg top 8 fetcher
│   ├── fetch_results_tweet.py     # Results post generator
│   ├── download_rivals_renders.py # dragdown.wiki render downloader
│   ├── copy_rivals_renders_to_full.py
│   └── helper.py                  # PIL utilities
│
├── Resources/
│   ├── Character_database.csv     # Character name list
│   ├── Player_database.csv        # Player → character mains + alts
│   ├── Character_Renders/         # Character PNGs
│   ├── Overlays/                  # Background/foreground templates
│   └── Fonts/                     # TTF/OTF fonts
│
├── Vod_Names/                     # Input: match data .txt files; missing.log written here
├── Top_8_Texts/                   # Input/output: top 8 data files
│   └── Default Top 8 HTML.txt    # Always updated on any Fetch Top 8
├── Youtube_Thumbnails/            # Output: generated thumbnails
├── Top_8_Results/                 # Output: HTML bracket graphics
│   └── Default Top 8.html        # Generic template usable for any series
├── Results_Posts/                 # Output: generated results posts
├── CMD_Scripts/                   # Batch wrappers for fetching + render downloads
└── Event_Generation/              # Batch wrappers for generating each series' thumbnails
```
