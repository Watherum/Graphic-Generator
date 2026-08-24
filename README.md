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

The **Ultimate** and **Melee** generators now have the same Qt GUI with the same tabs. The main game-specific differences:

- Costume **skins are numbered 1–8** (rather than Rivals' named skins) in the Player Database, with the same live preview
- The **Character Database** is a two-column `alias → render filename` mapping rather than a single-column name list
- The **Character Renders** tab simply opens the full render folder (the dragdown.wiki downloader is Rivals-only)
- Per-event thumbnail overrides save to `ultimate_event_configs.json` / `melee_event_configs.json` respectively

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
| Char Scale | Resize multipliers for 1-char, 2-char, and 3-char layouts |
| Character Positions | x/y center-shift values (normalized −1 to 1) per layout |
| Font Sizes | Player 1, Player 2, Event, Round, and rotation Angle° |
| Font Color | Hex entry + color picker |
| Save Config / Clear Config | Write or remove the override for the current series |

**VOD Names** *(collapsible)*

View and edit match data files without leaving the GUI.

- Dropdown shows only files matching the selected series, sorted by event number (highest first)
- Click ↺ to rescan the folder
- Edit lines directly in the table and click **Save**
- The **Len** column shows each line's character count as `N/100` and turns red when a line exceeds the 100-character title limit — a cue to set an **Abbrev** for the series and re-fetch
- Tick rows and use **Delete Marked** to remove them, or **Delete Unmarked** to keep only the ticked rows
- **Search match lines** filter bar narrows the table live as you type; generating while filtered only processes the visible lines. Clearing the filter re-highlights whatever row was selected
- Rows for VS-lines with missing character data are **highlighted red**; fixing a red line auto-saves it and logs the fix to the console
- **Import Missing Players** button (enabled only when red rows exist) jumps to the Player Database tab to fill in the missing entries
- **Generate Thumbnails** is disabled until every VS-line has valid character data
- Double-clicking a line places the cursor inside the first empty `()` so character names can be typed immediately
- A character picker (dropdown + ⟳ refresh + **Copy**) lets you copy a character name into the clipboard for pasting into a line

Click **Generate Thumbnails** to run the pipeline. Output goes to `Youtube_Thumbnails/{Event Name}/`. Missing player/character lookups are logged to `Vod_Names/missing.log`.

---

### 3. Generate Top 8s

Edit Top 8 placement data and preview the HTML bracket graphic.

**Top 8 Text Data** *(collapsible)*

- Select a series and event number — the matching `Top_8_Texts/` file loads automatically
- Selecting **Default Top 8.html** in the HTML file dropdown loads `Default Top 8 HTML.txt` instead
- Edit placements, sponsors, and characters directly in the syntax-highlighted text area
- A character picker (dropdown + ⟳ refresh + **Copy**) lets you copy a character name for pasting into a placement row
- Click **Save** to write changes

Data file format:

```
Event name:	Straight Into The Abyss 1
Event link:	https://start.gg/SITA1
Event entrants:	32 Competitors
Event date:	1/1/2025

1,Viviana,,Galvan
2,SapphireGD,AoC,Zetterburn
3,Turnap,BLZE,Ranno
...
```

Fields per placement row: `place, player name, sponsor (blank if none), character`

**Top 8 HTML Result** *(collapsible)*

The Top 8 graphic is a self-contained HTML file that reads the data file and renders placements, character renders, and sponsor tags live via JavaScript. There is no separate generation step — saving the text data is all that's needed.

- Select the HTML file for the current series from the dropdown (event-specific files plus **Default Top 8.html** are shown)
- Click **Open in Browser** to preview — designed for OBS's fixed canvas, not interactive browser use

**Layout Config** *(collapsible, starts collapsed)*

A visual config form for adjusting the layout of the selected HTML file without touching the raw HTML. Changes apply to whichever HTML file is currently selected.

| Section | Fields |
|---|---|
| Colors | Label color, Sponsor color (hex + color picker) |
| Event Info | Top %, Left %, Size px per field (Name / Link / Entrants / Date); color override for Name |
| Character Renders | Top %, Left %, Height % for each of the 8 placement slots |
| Placement Numbers | Top %, Left %, Size px for each slot |
| Player Names | Top %, Left %, Size px for each slot |
| Sponsors | Top %, Left %, Size px for each slot |

Click **Apply Config & Save** to push the form values into the HTML editor and write them to disk in one step.

**HTML Source** *(collapsible, starts collapsed)*

Raw HTML editor for direct editing. Syntax highlighted. Click **Save** to write changes to disk.

---

### 4. Generate Posts

Fetch and edit results posts for Twitter/X or Discord from start.gg results.

- Select a series and event number
- Toggle **Next Event** to include the next event's date and link in the post
- Click **Fetch Twitter** or **Fetch Discord** to pull standings with the matching social handles
- The generated post text appears in the editable text area
- Click **Save** to write changes back to `Results_Posts/{Event Name} {Platform} Post.txt`, or **Copy** to copy it to the clipboard

---

### 5. Player Database

Add, edit, and search player entries and their character mains/alts.

- Players listed alphabetically; use the search box to filter
- Click a player to load their data into the editor
- Add character rows with skin number and live skin previews (requires Pillow)
- All add/edit/remove/move actions **auto-save immediately** — a `[Auto-saved: player database]` line appears in the console log to confirm. A manual **Save Player Database** button is still available

---

### 6. Character Renders

Download and organize character render images.

- **Download Renders** — downloads renders from dragdown.wiki then copies them to the Full Renders folder
- **Download Renders** — download only
- **Copy to Full Renders** — copy already-downloaded renders to `Resources/Character_Renders/Rivals_2_Full_Renders/`

---

### 7. Character Database

Manage the list of recognised character names used during thumbnail generation. Add entries inline — changes take effect on the next thumbnail run.

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
```

CLI flags for `generate_rivals_thumbnail.py`:
- `-e, --event` — Event name string (required; must match a series in `populate_rivals_globals.py`)
- `-o, --output_file` — File to log missing player/character entries (omit to print to console)

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
| Add new character skins | Place PNGs in `Resources/Character_Renders/Rivals_2_Full_Renders/` |
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
│   ├── fetch_sets.py              # start.gg match data fetcher
│   ├── fetch_startgg_top8.py      # start.gg top 8 fetcher
│   ├── fetch_results_tweet.py     # Results post generator
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
└── Results_Posts/                 # Output: generated results posts
```
