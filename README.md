# Vpin Recommender

An AI-powered virtual pinball table recommendation engine for PinUp Popper cabinets. Analyzes your play history and recommends tables from your local catalog (or the Virtual Pinball Spreadsheet) using Google Gemini.

## Features

- Analyzes play history separately for **General** (non-EM) and **EM** (electromechanical) tables
- Returns two distinct recommendation sets tailored to each category
- Weights recommendations toward recently updated tables and known high-quality creators (configurable - you can adjust the weights in the script)
- Factors in game ratings, recency, and other factors to help you discover new tables that match your play style and preferences
- Optionally updates a PinUp Popper playlist with results
- Optionally tags recommended games with `AI_Suggested` for dynamic playlist creation

## Warning

This is a prototype and requires manual setup and knowledge of Python and SQL. It is not an official product and is provided "as-is" without warranty. Use at your own risk, and always back up your `PUPDatabase.db` before making any changes.

## Prerequisites

- Python 3.10+
- A PinUp Popper installation with `PUPDatabase.db`
- A [Google Gemini API key](https://aistudio.google.com/apikey)
- The `CustomGameLog` table and triggers must be set up in your `PUPDatabase.db` — see [CustomGameLog creation](#customgamelog-creation) below


## Setup

### 1. Clone the repository

```cmd
git clone <repo-url>
cd Vpin_Recommender
```

### 2. Create a virtual environment

If `python` is on your PATH (common on Linux/macOS or single-version Windows installs):
```cmd
python -m venv .venv
```

If you have multiple Python versions installed on Windows, use the [Python Launcher (`py`)](https://docs.python.org/3/using/windows.html#python-launcher-for-windows) to ensure the correct version is used:
```cmd
py -m venv .venv
```

### 3. Activate the virtual environment

**PowerShell:**
```powershell
.venv\Scripts\activate
```

**CMD:**
```cmd
.venv\Scripts\activate.bat
```

### 4. Install dependencies

```cmd
pip install -r requirements.txt
```

### 5. Configure your API key

The script reads `GEMINI_API_KEY` from an environment variable. **Do not hard-code your key in the script or commit it to source control.**

#### Option A: `.env` file (recommended for local development)

Create a `.env` file in the project root:

```
GEMINI_API_KEY=your_api_key_here
```

Then set it before running:

**PowerShell:**
```powershell
$env:GEMINI_API_KEY = (Get-Content .env | Where-Object { $_ -match "GEMINI_API_KEY" }) -replace "GEMINI_API_KEY=", ""
```

**CMD:**
```cmd
for /f "tokens=2 delims==" %a in ('findstr GEMINI_API_KEY .env') do set GEMINI_API_KEY=%a
```

> **Important:** Add `.env` to your `.gitignore` so it is never committed.

#### Option B: Windows User Environment Variable (persistent, no file needed)

Set it once and it persists across sessions:

**PowerShell (admin not required):**
```powershell
[System.Environment]::SetEnvironmentVariable("GEMINI_API_KEY", "your_api_key_here", "User")
```

Or via **Settings → System → About → Advanced system settings → Environment Variables → User variables**.

#### Option C: Windows Credential Manager (most secure)

For maximum security, store the key in Windows Credential Manager and retrieve it at runtime. You can use the `keyring` library:

```bash
pip install keyring
```

Store the key once:
```python
import keyring
keyring.set_password("vpin_recommender", "gemini_api_key", "your_api_key_here")
```

Retrieve in your script:
```python
import keyring
GEMINI_API_KEY = keyring.get_password("vpin_recommender", "gemini_api_key")
```

## Configuration

Edit the constants at the top of `Vpin_Recommender.py` to match your setup:

| Variable | Description |
|----------|-------------|
| `DB_PATH` | Path to your `PUPDatabase.db` |
| `TARGET_EMU_IDS` | Comma-separated emulator IDs to include (see below) |
| `UPDATE_PLAYLIST` | `True` to update a PinUp Popper playlist with recommendations |
| `RECS_PLAYLIST_ID` | Playlist ID to populate (only used when `UPDATE_PLAYLIST` is `True`) |
| `ADD_SUGGESTED_TAGS` | `True` to tag recommended games with `AI_Suggested` |
| `NUM_RECOMMENDATIONS` | Number of general (non-EM) recommendations |
| `NUM_RECOMMENDATIONS_EM` | Number of EM recommendations |
| `MIN_GAME_RATING` | Minimum rating filter (0 = no filter) |
| `INCLUDE_NON_RATED` | Set to `1` to include unrated tables even when filtering by rating |
| `HISTORY_DAYS` | Days of play history to analyze |
| `INCLUDE_NOT_OWNED` | `True` to include external table suggestions from the VPIN Spreadsheet |
| `NUM_NOT_OWNED` | Number of external table suggestions (only used when `INCLUDE_NOT_OWNED` is `True`) |

### Playlist setup

A dedicated playlist is only required if `UPDATE_PLAYLIST` is set to `True`. In that case, you can use an existing playlist or create a new one (the games in the playlist are overwritten each refresh). To find the playlist ID, open the **PinUp Popper Setup Utility**, navigate to your playlists, and note the ID of the playlist you want to use. Set `RECS_PLAYLIST_ID` in the script to that value.

Alternatively, if `ADD_SUGGESTED_TAGS` is `True`, recommended games are tagged with `AI_Suggested` and you can build a dynamic playlist using a SQL query of your choice, for example:

```sql
SELECT * FROM Games WHERE TAGS LIKE '%AI_Suggested%'
```

### Emulator IDs

Set `TARGET_EMU_IDS` to the emulator IDs you want the recommender to analyze. You can find these in the PinUp Popper Setup Utility under the emulator configuration. Note that some emulators, like **PinballFX**, may not have standard filenames and would require additional work to integrate properly.

## Usage

### Quick launch (recommended)

Double-click `run.bat` or add it to Windows Task Scheduler / Startup folder for automatic execution on boot.

```cmd
run.bat
```

This batch file automatically loads your API key from `.env`, activates the venv, and runs the script.

### Run on Windows startup

1. Press `Win + R`, type `shell:startup`, and press Enter.
2. Create a shortcut to `run.bat` in the folder that opens.

The recommender will now run once each time you log in.

### Manual launch

```bash
.venv\Scripts\activate
python Vpin_Recommender.py
```

The script will:
1. Extract play history and candidate pool from your database
2. Send the data to Google Gemini for AI-powered recommendations
3. Save results to `ai_recommendations.json`
4. Update the specified PinUp Popper playlist (if `UPDATE_PLAYLIST` is `True`)
5. Tag recommended games with `AI_Suggested` (if `ADD_SUGGESTED_TAGS` is `True`)

## Files

| File | Purpose |
|------|---------|
| `Vpin_Recommender.py` | Main script |
| `requirements.txt` | Python dependencies |
| `ai_prompt_payload_compact.txt` | Generated payload sent to AI (auto-created) |
| `ai_recommendations.json` | AI output (auto-created) |
| `.env` | Your API key (create manually, do not commit) |

## .gitignore recommendations

```
.venv/
.env
ai_prompt_payload_compact.txt
ai_prompt_full.txt
ai_recommendations.json
```


## CustomGameLog creation

The default `GamesStats` table in PinUp Popper tracks high-level stats like total plays and last played date, but lacks the granularity needed for meaningful analysis. It cannot tell you *when* each individual session occurred, making it impossible to determine trends, recency, or frequency of play over time.

`CustomGameLog` solves this by acting as a detailed log that records every play session.

> ⚠️ **Warning:** Please create a backup of your `PUPDatabase.db` file (by copying it or using the built-in Backup Database feature) before making any alterations.

It is populated automatically via triggers on the `GamesStats` table — every time a game is played, a row is inserted capturing the game ID, timestamp, and session duration. This enables time-based analysis such as play activity over the last 90, 180, or 365 days, and can surface games that were once heavily played but have fallen off recently.

### Setup

Run the following SQL statements against your `PUPDatabase.db` to create the table, indexes, and triggers:

```sql
-- Create the CustomGameLog table
CREATE TABLE CustomGameLog (
    UniqueID INTEGER PRIMARY KEY AUTOINCREMENT,
    GameID INTEGER,
    PlayDate DATETIME DEFAULT(current_timestamp),
    SessionPlayedSecs INTEGER DEFAULT(0),
    TotalTimePlayedSecs INTEGER DEFAULT(0),
    Flags varchar(200) DEFAULT (''),
    Timestamp DATETIME DEFAULT(current_timestamp)
);

CREATE INDEX cglGameIdIdx ON CustomGameLog (GameID);
CREATE INDEX cglPlayDateIdx ON CustomGameLog (PlayDate);
```

```sql
-- Create triggers to log each play session automatically
CREATE TRIGGER GameStatsInsertTrigger AFTER INSERT ON GamesStats
BEGIN
    INSERT INTO CustomGameLog (GameID, PlayDate, SessionPlayedSecs, TotalTimePlayedSecs, Flags)
    VALUES (NEW.GameID, NEW.LastPlayed, NEW.TimePlayedSecs, NEW.TimePlayedSecs, 'I');
END;

CREATE TRIGGER GameStatsUpdateTrigger AFTER UPDATE ON GamesStats
BEGIN
    INSERT INTO CustomGameLog (GameID, PlayDate, SessionPlayedSecs, TotalTimePlayedSecs, Flags)
    VALUES (NEW.GameID, NEW.LastPlayed, (NEW.TimePlayedSecs - OLD.TimePlayedSecs), NEW.TimePlayedSecs, 'U');
END;
```

**Note: The TotalTimePlayedSecs and Flags are primarily there for debugging/validation.