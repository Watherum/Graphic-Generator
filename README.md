# Graphic Generation
This project is based off the work of my good friend CR_Jetstream!

This project is now mainly focused on generating thumbnails and top 8 graphics for Rivals 2.
Ultimate Support is still maintained but not the main focus. Some Melee support exists as well.

## Updating

Run `update.cmd` from the repo root to pull the latest code from GitHub.

It will automatically stash any local changes (generated outputs, VOD name files, etc.), pull the latest source, then restore your local changes. Requires [Git for Windows](https://git-scm.com/download/win) to be installed.

## Notes
Currently these scripts only run with Python 3.9. An exe is included.

---

## GUI (Recommended)

Launch the GUI from the generator folder:

```
Rivals_2_Generator\Launch_Rivals_GUI.cmd
```

The GUI has five tabs:

### 1. Fetch From Start.gg

Pull match data and top 8 standings directly from start.gg.

**Preset Tournaments** (Immortal Fight Night, Straight Into The Abyss)
- Enter the event number and top 8 link
- Click **Fetch VOD Names** or **Fetch Top 8**
- Event numbers are saved automatically between sessions

**Saved Custom Tournaments**
- Custom tournaments you've previously added appear here as their own sections
- Each shows an Event # field, Top 8 Link field, and **Fetch VOD Names** / **Fetch Top 8** / **Delete** buttons
- Event numbers and top 8 links are saved automatically between sessions
- Top 8 output files are created automatically if they don't exist yet

**Add New Custom Tournament**
- Enter a slug (use `{n}` as a placeholder for the event number, e.g. `tournament/{event}-{n}/event/rivals-2-singles`)
- Enter a series name (e.g. `Immortal Fight Night`)
- Enter a starting event number
- Click **Save & Fetch VOD Names** — the tournament is saved and will appear in Saved Custom Tournaments on future boots

### 2. Generate Thumbnails

**Event selector**
- Choose a series from the dropdown (includes both preset and saved custom tournaments)
- Enter the event number/suffix — the full event name is built automatically
- Custom events sync their number from the Saved Custom Tournaments section

**Thumbnail Config** *(collapsible)*

Configure how thumbnails are rendered for the selected series. Settings are saved per-series to `rivals_event_configs.json` and applied automatically at generation time on top of any hardcoded defaults.

| Field | Description |
|---|---|
| Background / Foreground | Browse to select an image — it is copied to `Resources/Overlays/` automatically |
| Font | Choose from fonts in `Resources/Fonts/` |
| Character Glow | Toggle glow effect on character renders |
| One Character Per Player | Limit each player slot to a single character |
| Char Scale | Resize multipliers for 1-char, 2-char, and 3-char layouts |
| Character Positions | x/y center-shift values (normalized −1 to 1) for each layout (1-char, 2-char, 3-char) |
| Font Sizes | Player 1, Player 2, Event, Round, and text rotation Angle° |
| Font Color | Hex entry + color picker — applies to all text elements |
| Save Config / Clear Config | Write or remove the override for the current series |

Configs for unknown/custom events are merged on top of the default property set, so only the fields you set are overridden.

**VOD Names** *(collapsible)*

View and edit match data files without leaving the GUI.

- Dropdown shows only files matching the currently selected series, sorted by event number (highest first)
- Click ↺ to rescan the folder
- Edit lines directly in the text area
- Click **Save** to write changes back to disk

Click **Generate Thumbnails** to run the thumbnail pipeline for the current event name.

### 3. Character Renders

Download character render images from dragdown.wiki or copy them into the Full Renders folder.

### 4. Player Database

Add, edit, and search player entries and their character mains/alts.

- Players are listed **alphabetically**
- Use the search box to filter
- Click a player to load their data into the editor
- Add character rows with skin previews (requires Pillow)
- Click **Save Player Database** to persist changes

### 5. Character Database

Manage the list of recognised character names used during thumbnail generation.

---

## CLI Usage

```bash
# Generate thumbnails
python "Rivals_2_Generator\Python_Scripts\generate_rivals_thumbnail.py" -e "Immortal Fight Night 278" -o missing.log

# Fetch match data from start.gg
python "Rivals_2_Generator\Python_Scripts\fetch_sets.py" tournament/ultimate-immortal-fight-night-278/event/rivals-2-singles --name "Immortal Fight Night 278" --out "Vod_Names\Immortal Fight Night 278 Names.txt"

# Fetch top 8 bracket data
python "Rivals_2_Generator\Python_Scripts\fetch_startgg_top8.py" tournament/ultimate-immortal-fight-night-278/event/rivals-2-singles --name "Immortal Fight Night 278" --link "https://start.gg/UIFN278" --out "Top_8_Texts\Immortal Fight Night Top 8 HTML.txt"
```

---

## Adding a New Tournament Series (CLI / Manual)

1. Add a `setGlobalsMyEvent(weekly_event)` function in `populate_rivals_globals.py`
2. Add a dispatcher branch in `setGlobals()` in `generate_rivals_thumbnail.py`
3. Place overlay images in `Resources/Overlays/`
4. Create match data in `Vod_Names/{Event Name} Names.txt`

Alternatively, use the GUI **Thumbnail Config** tab to configure overlays, fonts, and character positions for any series without touching Python — settings are saved to `rivals_event_configs.json` and applied automatically.

---

## Maintenance

| Task | How |
|---|---|
| Add new character skins | Place PNGs in `Resources/Character_Renders/Rivals_2_Full_Renders/` |
| Add new characters | Add name to `Resources/Character_database.csv` |
| Add/update players | Use GUI → Player Database tab |
| Add overlay images | Place in `Resources/Overlays/` or use Browse in Thumbnail Config |

## Generating Top 8 Graphics

Requires a foreground and background image in `Resources/Top8_Graphics/`.

Use **Fetch Top 8** in the GUI (preset or saved custom tournament) to pull standings from start.gg into `Top_8_Texts/`. The HTML-based top 8 graphic is updated automatically.

---

# Original Readme
A project for quickly creating YouTube Thumbnails and Top 8 Graphics for Nintendo fighting game Super Smash Brothers Ultimate.
The purpose of this project is to provide an efficient way to create these images. This is especially useful for weekly events or big events with lots of videos.

This project has been a side project and has no current commitment to long term support.
