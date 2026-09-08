# Graphic Generator

Batch image generator for Rivals 2 esports — creates YouTube thumbnails, Top 8 bracket graphics, and results posts for weekly events, from brackets run on **start.gg**, **parry.gg** or **Challonge**. Singles and doubles are both supported. Originally based on work by CR_Jetstream; now primarily focused on Rivals 2. Ultimate and Melee generators are also included and share the same Qt GUI and feature set.

## Requirements

- **Python 3.12** — install from [python.org](https://www.python.org/downloads/) if not already present
- Run `requirments_install.cmd` once to install Python dependencies

### API credentials (optional)

Match data can be pulled from **start.gg**, **parry.gg** or **Challonge**. start.gg needs
nothing; the other two need credentials. Copy `app.example.properties` to
`app.properties` in the repo root and fill in what you use — `app.properties` is
gitignored, so your keys are never committed.

| Site | What to set | Where to get it |
|---|---|---|
| start.gg | nothing | — the queries used are public |
| parry.gg | `parrygg.api.key` | your parry.gg account |
| Challonge | `challonge.client.id` + `challonge.client.secret` | create an application at [challonge.com/settings/developer](https://challonge.com/settings/developer) |

Challonge's developer portal no longer issues bare v1 API keys, so the generator uses an
OAuth application instead — it exchanges the id and secret for a token itself, with no
browser step, and caches it in `.challonge_token.json` beside `app.properties`. An older
`challonge.api.key` is still honoured and takes precedence if you have one.

Selecting a provider on the **Fetch Data** tab with its credentials missing shows a red
hint beside the dropdown rather than failing later on a fetch.

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
same features — including all three fetch providers, doubles support, per-set costume
overrides, the preferred-costume marker, the per-VOD-file thumbnail configs, the live
thumbnail preview in Thumbnail Config, and the embedded Top 8 preview with its PNG
export. The remaining game-specific differences:

- Costumes are **numbered 1–8** (rather than Rivals' named skins) everywhere they appear:
  in the Player Database, the costume pickers, and the `Character:Alt` override syntax —
  where the field is labelled **Costume**
- The **Character Database** is a two-column `alias → render filename` mapping rather than a single-column name list
- The **Character Renders** tab simply opens the full render folder (the dragdown.wiki downloader is Rivals-only)
- Per-event thumbnail overrides save to `ultimate_event_configs.json` / `melee_event_configs.json` respectively
- **Rivals-only:** the dragdown.wiki render downloader, and the named-skin model

The Rivals 2 GUI has eight tabs:

---

### 1. Fetch Data

Pull match data and top 8 standings from **start.gg**, **parry.gg** or **Challonge**,
picked with the **Fetch from** dropdown at the top of the tab. The choice is remembered
between sessions, and only that site's saved events are listed below it.

#### How the three sites differ

|  | start.gg | parry.gg | Challonge |
|---|---|---|---|
| What the URL names | an **event** (one bracket) | a **tournament** | a **tournament** |
| Picking the event | baked into the URL | the **Event:** box — `0` is the first bracket, `1` the next | n/a — a tournament *is* the bracket |
| Credentials | none | `parrygg.api.key` | OAuth client id + secret |
| Characters | yes | yes, when the TO reported games | **never** — Challonge has no game model |
| Round names | as reported | as reported | **derived** from the bracket shape (`Wnrs Semi`, `Grand Final`, …) |
| Results posts | Twitter + Discord handles | Twitter + Discord (Twitter via the player's linked start.gg account) | plain tags — no socials exist |

Challonge's two limits are permanent facts about its API rather than a failed fetch, so
they're shown as a standing amber note under the dropdown. Its Top 8 fetch falls back to
each player's main from `Player_database.csv` for the missing characters, and its
standings need the bracket to be **finalized** — an unfinished one is reported rather
than guessed at.

**The provider filters this tab only.** The Thumbnails, Top 8 and Posts tabs list every
saved event whatever pulled it — a parry-fetched VOD file generates exactly like a
start.gg one.

Each event is shown in a **collapsible panel** — click the header to expand/collapse it.
Collapsed/expanded state is remembered between sessions.

**Preset events** (Immortal Fight Night, Straight Into The Abyss)
- Enter the **Tournament #** and top 8 link
- Optionally set an **Abbrev** (e.g. `IFN`) — see *Tournament abbreviations* below
- Click **Fetch VOD Names** or **Fetch Top 8**
- Tournament numbers, links, and abbreviations are saved automatically between sessions

**Saved Events**
- Events you've previously added appear here as their own panels, filtered to the selected provider
- Every field is **editable in place** — Event URL, Name, Tournament #, Top 8 link, Abbrev
  (plus parry's Event index). A tournament that renames a bracket or moves to a new URL is
  fixed by editing it rather than deleting and re-adding, which would take its abbreviation
  and Top 8 link with it
- Editing the **Name** renames the event everywhere it's listed — Thumbnails, Top 8 and Posts follow
- A pasted URL is normalized when you leave the box, and a URL belonging to a *different*
  site is called out in the console rather than saved as a plausible-looking slug
- **Fetch VOD Names** / **Fetch Top 8** / **Delete** buttons on each panel

**Add A Tournament's Event**
- **Event URL** — paste the event's URL, or a slug template using `{n}` as a placeholder
  for the tournament number (e.g. `tournament/my-event-{n}/event/rivals-2-singles`). The
  form's wording, placeholder and validation follow the selected provider
- **Name** — the series name for the VOD lines, e.g. `Immortal Fight Night {n}`
- **Abbrev** — optional, see below
- **Tournament #** — optional; it fills every `{n}` above. A tournament whose URL and name
  contain no `{n}` needs none
- **Event:** — parry.gg only: which bracket inside the tournament to pull (`0` = the first)
- Click **Save & Fetch VOD Names** — the event is saved and appears under Saved Events on future boots

> **Tournament #** vs **Event**: the number identifies the instalment of a series (274 for
> *Immortal Fight Night 274*); an *event* is one bracket inside that tournament. A
> tournament running both singles and doubles needs one saved entry per bracket.

> **Fetch Top 8** always writes to both the event-specific text file and `Top_8_Texts/Default Top 8 HTML.txt`, keeping the default template in sync with the latest event.

#### Tournament abbreviations

YouTube limits video titles to 100 characters. Each VOD match line begins with the full tournament name, and long names plus long player tags can push a line over that limit.

Set a short **Abbrev** for a series (e.g. `IFN` for *Immortal Fight Night*) and the event
number is appended automatically (`IFN 274`).

**Abbreviating happens when you copy, not when you fetch.** A VOD file always spells the
event name out in full; the fetchers only record the abbreviation in a `# ABBREV:` header
at the top of the file. The **Copy** button in the VOD table is what applies it, so the
editor never shows two spellings of one event and nothing on disk is rewritten. See the
**Len** column below for what a line actually becomes on the clipboard.

---

### 2. Generate Thumbnails

**Event selector**
- Choose a **Series** from the dropdown (includes preset and saved events)
- **# / Label** is what replaces `{n}` in the series name — an event number (`274`), or a
  word for a tournament's other brackets (`Doubles`, `Crews`)
- **Event name** shows the full name that gets generated. It's a dropdown of the events
  that already have a VOD file, so one tournament's several brackets can be picked rather
  than typed, and it stays editable for an event not fetched yet. Picking an event selects
  its VOD names file, and picking a file selects the event

**Thumbnail Config** *(collapsible, starts collapsed)*

Configure rendering for the selected series. Settings are saved to
`rivals_event_configs.json` and applied at generation time on top of any hardcoded defaults.

**Applies to** at the top of the box chooses what the form edits:

- **Series** — every event whose name starts with the series
- **VOD file** — just the names file selected in the VOD Names section

A file config overrides the series config, which is how two brackets of one tournament —
`Twist of Fate` and `Twist of Fate Doubles`, which share a series name — can look
completely different. In file scope the form loads *series + file* settings, since a file
entry layers on top rather than replacing everything, and **Clear Config** drops just the
file entry and reloads the series one. A warning under the picker appears if the selected
file isn't the one the event name will actually read.

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
  clipboard — measured *after* skins are stripped and the shortening strategies below are
  applied, so it's what would be published rather than what the row happens to contain.
  Its colour says how much had to be given up to get there:

  | Colour | Meaning |
  |---|---|
  | none | fits as written |
  | blue | the series abbreviation was enough |
  | amber | the character lists had to go as well |
  | red | still over 100 even then — the line itself needs work |

  Only red asks for action. Hover for the exact line that gets copied and what ran to
  produce it
- Each row has its own **Copy** button and **↑ / ↓** buttons to reorder lines (clear the
  filter first — reordering a filtered view is blocked)
- Right-click a row for **Copy line**, **Set skins…** and **Delete line**
- Tick rows and use **Delete Marked** to remove them, or **Delete Unmarked** to keep only the ticked rows
- The count to the left of the filter box reads **`41 sets`**, or **`12 of 41 sets`** while
  a filter is narrowing the view. Blank rows and `#` comments aren't counted
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

#### Shortening long titles

Two strategies run in order when copying a line, each only if the line is *still* over
100 characters:

1. The series **abbreviation** replaces the event name
2. The `(characters)` after each player is dropped — the one part of a title that
   describes the renders rather than the set

Nothing beyond those two is ever cut: a line still over the limit is copied as it is,
because what to give up next is your call. Only the player section is touched, so
parentheses in an event name (`Some Event (Online) 12`) or a round (`Pools (A) Wnrs Rd 2`)
survive. **The line in the table and on disk is never modified** — every strategy runs on
the way to the clipboard only.

#### Doubles

Doubles brackets generate thumbnails. A team entrant is written with a **comma** between
the members:

```
Twist of Fate Doubles - Lsrs Final - shane,THE PIZZA GUY (Ranno:Goo Green, Kragg:Salaryman Green) Vs Bowler,ybm (Clairen:Samurai Blue, Wrastor:Parrot Blue) - RoA II
```

- start.gg reports a team as `shane / THE PIZZA GUY`, but the match title becomes the
  output **filename** and `/` isn't legal in a Windows one — so the fetchers write the
  comma form, and an older file with a slash in it is normalized as it's read
- **A team has no row of its own** in `Player_database.csv`; each member keeps theirs, and
  character *i* belongs to member *i*. If a member has no row, the character falls back to
  whichever member's row has it, and the missing-entries log names a player rather than a team
- **Any team size works** — a 3v3 writes `A,B,C` and reads back the same. Each set's
  characters are grouped per member, so two teammates on the same character don't collapse
  into one and a counterpick isn't misattributed
- **The thumbnail draws the first three characters per side** (the layouts have
  arrangements for one, two and three); the title keeps them all, and the database lookups
  still run for every one
- **Long labels shrink to fit** rather than running off the canvas — a team name is about
  twice the length of a singles tag. Text that already fits is drawn at its configured size
- A slash doesn't by itself mean a team: a sponsored singles entrant like `NG/POA | Azul`
  is one player, and the fetchers use the *source's own participant count* to decide.
  Challonge reports no count, so it guesses from punctuation and lists every split it made
  on the console — pass `--no-teams` for a singles bracket whose tags contain separators

Top 8 doubles is deliberately unsupported — those data files are comma separated, so a
team name can't be written into one.

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
**Apply Config & Save** writes immediately. Clearing a box leaves that value as it stands —
an empty field means "no change", so you can wipe a number and type a new one without the
half-typed state being written out.

A player name is drawn at the size you set unless it would collide with the slot next to it,
in which case it shrinks to the largest size that still fits (and a name with a space in it
may wrap to two lines first). If a size seems to be ignored, that's the reason — the tag is
simply too wide for the space between it and its neighbour. Hand-added CSS and scripts in the file survive
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

- Reloads itself whenever Layout Config **or** the text data saves. Changing a character
  reloads it from scratch, so the new render is fetched rather than served from the cache
- **⟳ Refresh** forces a fresh load, for when something still looks stale
- **Save Image…** renders the graphic to a full-size 1920×1080 PNG and asks where to put it.
  It captures through the GUI's own browser engine, so it works whatever your default
  browser is, and needs nothing added to the HTML — any page whose graphic starts at the
  top-left corner exports correctly, including one you supplied yourself

---

### 4. Generate Posts

Fetch and edit results posts for Twitter/X or Discord. All three providers generate one.

- Select a series and **# / Label** — the same event picker the Thumbnails tab uses
- Toggle **Next Event** to include the next event's **Date**, **Link** and **Vods link** in the post
- Click **Fetch Twitter** or **Fetch Discord** to pull standings with the matching social handles
- The generated post text appears in the editable text area
- Click **Save** to write changes back to `Results_Posts/{Event Name} {Platform} Post.txt`, or **Copy** to copy it to the clipboard

**The buttons change to suit the provider**, and a note under them explains what that site
can and cannot supply — so a post full of plain tags reads as a limit of the site rather
than a failed fetch:

| Provider | Buttons | Handles come from |
|---|---|---|
| start.gg | Fetch Twitter, Fetch Discord | each player's connected accounts |
| parry.gg | Fetch Twitter, Fetch Discord | linked accounts — Discord directly, Twitter *bridged* through the player's linked start.gg account |
| Challonge | **Generate Post** | nothing; a participant is just a name the organiser typed, so everyone is listed by tag |

Expect a modest hit rate on parry's Twitter side — many players link neither account, and
anyone who linked neither is listed by tag. Challonge posts are written to
`Results_Posts/{Event Name} Post.txt`, with no platform in the name.

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

### Generating, and start.gg

```bash
# Generate thumbnails (run from inside Rivals_2_Generator/)
python "Python_Scripts\generate_rivals_thumbnail.py" -e "Straight Into The Abyss 41"

# Log missing player/character entries to a file
python "Python_Scripts\generate_rivals_thumbnail.py" -e "Straight Into The Abyss 41" -o "Vod_Names\missing.log"

# Fetch match data from start.gg
python "Python_Scripts\fetch_sets.py" tournament/straight-into-the-abyss-41/event/rivals-2-singles --name "Straight Into The Abyss 41" --out "Vod_Names\Straight Into The Abyss 41 Names.txt"

# ...add --abbrev to record an "# ABBREV:" header; the GUI applies it when copying a
# line over 100 chars. The lines themselves always spell the event out in full.
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
- `-v, --vod-file` — Read match lines from this file instead of `{event} Names.txt`
- `-c, --config-file` — Names file whose per-file thumbnail config to apply (used with `-v`)

### parry.gg

Addresses a **tournament**, so the bracket inside it is picked with `--event` (0-based
index, or an event slug). Needs `parrygg.api.key` in `app.properties`.

```bash
python "Python_Scripts\fetch_parrygg_sets.py" fan-the-flames-2-01a02b45 --event 0 --name "Fan The Flames 2" --abbrev "FTF 2" --out "Vod_Names\Fan The Flames 2 Names.txt"
python "Python_Scripts\fetch_parrygg_top8.py" fan-the-flames-2-01a02b45 --event 0 --name "Fan The Flames 2" --link "https://parry.gg/..." --out "Top_8_Texts\Fan The Flames Top 8 HTML.txt"
python "Python_Scripts\fetch_parrygg_post.py" fan-the-flames-2-01a02b45 --platform twitter
```

### Challonge

Addresses a **tournament** — a bracket URL in either `myorg.challonge.com/my-weekly` or
`challonge.com/myorg/my-weekly` form is accepted and normalized. Needs
`challonge.client.id` / `.secret` in `app.properties`.

```bash
python "Python_Scripts\fetch_challonge_sets.py" myorg-my-weekly --name "My Weekly 42" --out "Vod_Names\My Weekly 42 Names.txt"
python "Python_Scripts\fetch_challonge_top8.py" myorg-my-weekly --name "My Weekly 42" --out "Top_8_Texts\My Weekly Top 8 HTML.txt"
python "Python_Scripts\fetch_challonge_post.py" myorg-my-weekly

# Check credentials on their own — token minted, scope granted, tournament readable
python "Python_Scripts\challonge_api.py"
python "Python_Scripts\challonge_api.py" myorg-my-weekly
```

Useful extras: `--debug` on either fetcher dumps the raw tournament, participant and match
when a field comes back empty; `--no-teams` on the sets fetcher stops `/` in a tag being
read as a doubles team; `--all` includes matches that aren't complete yet.

Every fetcher writes the same file formats, so everything downstream — thumbnails, Top 8
graphics, results posts — works identically whichever site the bracket ran on.
`CMD_Scripts/` holds ready-made wrappers for the parry.gg and Challonge fetchers. Each
takes the tournament slug and an optional event name, and prints a usage line if run with
no arguments:

```
Fetch_Challonge_Sets.cmd my-weekly-42 "My Weekly 42"
Fetch_Challonge_Top8.cmd my-weekly-42 "My Weekly 42"
Fetch_Parrygg_Sets.cmd   my-tournament-019c9aeb "My Tournament 5"
Fetch_Parrygg_Top8.cmd   my-tournament-019c9aeb "My Tournament 5" "https://parry.gg/my-tournament-019c9aeb"
```

The name defaults to the slug if you leave it off, and `Fetch_Parrygg_Top8.cmd` takes an
optional third argument — the link printed on the Top 8 graphic. For a tournament's second
bracket, add `--event N` inside the wrapper or call the script directly.

`Event_Generation/` holds batch wrappers for generating each established series'
thumbnails, if you prefer double-clicking to typing.

---

## Adding a New Tournament Series

### Via GUI (no Python required)

1. Add the event in the **Fetch Data** tab → Add A Tournament's Event (pick the site it
   runs on first)
2. Configure overlays, fonts, and positions in the **Generate Thumbnails** tab → Thumbnail Config
3. Settings are saved to `rivals_event_configs.json` automatically
4. For a second bracket of the same tournament (a doubles alongside the singles), save a
   second event pointing at that bracket, then set **Applies to → VOD file** in Thumbnail
   Config so the two can be laid out differently

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
| Lay out one bracket differently | GUI → Thumbnail Config → **Applies to: VOD file**, then Save Config |
| Fetch from parry.gg or Challonge | Set credentials in `app.properties`, then pick the site in **Fetch Data → Fetch from** |
| Sync renders from dragdown.wiki | GUI → Character Renders tab → Download Renders |

---

## File Layout

```
Rivals_2_Generator/
├── Launch_Rivals_GUI.vbs          # GUI entry point
├── rivals_gui_settings.json       # Persisted GUI state (event numbers, etc.)
├── rivals_custom_events.json      # User-added custom tournament series
├── rivals_event_configs.json      # Per-series thumbnail config overrides (plus a
│                                  #   "__files__" section for per-VOD-file overrides)
│
├── Python_Scripts/
│   ├── rivals_gui.py              # PySide6 (Qt) GUI
│   ├── generate_rivals_thumbnail.py  # Thumbnail pipeline
│   ├── populate_rivals_globals.py    # Per-series config & dispatcher
│   ├── skin_utils.py              # Shared skin/render helpers (labels, preferred skins)
│   ├── team_utils.py              # Shared doubles helpers (splitting, per-member chars)
│   ├── results_post.py            # Shared post shaping (emoji, intro, footers)
│   ├── fetch_sets.py              # start.gg match data fetcher
│   ├── fetch_startgg_top8.py      # start.gg top 8 fetcher
│   ├── fetch_results_tweet.py     # start.gg results post
│   ├── fetch_parrygg_sets.py      # parry.gg match data fetcher
│   ├── fetch_parrygg_top8.py      # parry.gg top 8 fetcher
│   ├── fetch_parrygg_post.py      # parry.gg results post
│   ├── challonge_api.py           # Challonge OAuth + shared API access
│   ├── challonge_rounds.py        # Challonge round-name derivation
│   ├── fetch_challonge_sets.py    # Challonge match data fetcher
│   ├── fetch_challonge_top8.py    # Challonge top 8 fetcher
│   ├── fetch_challonge_post.py    # Challonge results post
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
