import os
import sys
import sqlite3
import json
import time
from datetime import datetime
# from groq import Groq
from google import genai
from google.genai import types

# py -m pip install google-genai

# ==============================================================================
# CONFIGURABLE PARAMETERS & PATHS
# ==============================================================================
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PAYLOAD_PATH = os.path.join(SCRIPT_DIR, "ai_prompt_payload_compact.txt")
PROMPT_PATH = os.path.join(SCRIPT_DIR, "ai_prompt_full.txt")
RECS_OUTPUT_PATH = os.path.join(SCRIPT_DIR, "ai_recommendations.json")

# Minimum age (in minutes) before re-generating recommendations
MAX_AGE_MINUTES = 1

# PinUp Popper System Settings
DB_PATH = r"C:\vPinball\PinUPSystem\PUPDatabase.db"
TARGET_EMU_IDS = "10" # add whaevever EMUIDs to include in analysis

# Update a PinUp Popper playlist with recommended games?
UPDATE_PLAYLIST = True
RECS_PLAYLIST_ID = 1234

# Tag recommended games with 'AI_Suggested'?
ADD_SUGGESTED_TAGS = True

# Number of tables to recommend
NUM_RECOMMENDATIONS = 10
NUM_RECOMMENDATIONS_EM = 5

# Minimum game rating filter for candidate pool (0 = no filter)
MIN_GAME_RATING = 0
INCLUDE_NON_RATED = 1

# Number of days of play history to analyze
HISTORY_DAYS = 365

# Games played within this many days are excluded from recommendations.
# Games in the history but last played MORE than this many days ago can still be recommended.
REPLAY_WINDOW_DAYS = 90

# Include "not_owned" recommendations from the VPIN Spreadsheet?
# This is currently deactivated as there were inaccurate results trying to match real vs virtual with games the user doesn't have - 
# specifically we saw lots of games we already had, or games not available virtually. 
# Additionally, this is designed to run periodically and update popper, so there'd be no practical way to surface tables not owned in the playlist.
# Currently not worth the token overhead but an interesting idea for future enhacement
INCLUDE_NOT_OWNED = False
NUM_NOT_OWNED = 5

# Pull the API key from the environment
# GROQ_API_KEY = os.environ.get("GROQ_API_KEY")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")

# ==============================================================================
# SQL QUERIES
# ==============================================================================
HISTORY_QUERY_GENERAL = f"""
SELECT 
    count(1) as TotalPlays, 
    sum(SessionPlayedSecs) as TotalTimePlayedSecs, 
    CAST(JULIANDAY('now') - JULIANDAY(max(cgl.PlayDate)) AS INTEGER) AS LastPlayedDays,
    g.GameId,
    GameDisplay, 
    GameYear, 
    Manufact,
    GameType,
    GameRating
FROM Games AS g 
JOIN CustomGameLog cgl ON g.GameID = cgl.GameID 
WHERE g.EMUID in ({TARGET_EMU_IDS}) 
  and g.visible=1 
  and PlayDate > DateTime('Now', 'LocalTime', '-' || ? || ' Day')
  and g.GameType IS NOT 'EM'
GROUP BY cgl.GameID 
HAVING TotalPlays > 1
ORDER BY TotalPlays DESC
LIMIT 250
"""

HISTORY_QUERY_EM = f"""
SELECT 
    count(1) as TotalPlays, 
    sum(SessionPlayedSecs) as TotalTimePlayedSecs, 
    CAST(JULIANDAY('now') - JULIANDAY(max(cgl.PlayDate)) AS INTEGER) AS LastPlayedDays,
    g.GameId,
    GameDisplay, 
    GameYear, 
    Manufact,
    GameType,
    GameRating
FROM Games AS g 
JOIN CustomGameLog cgl ON g.GameID = cgl.GameID 
WHERE g.EMUID in ({TARGET_EMU_IDS}) 
  and g.visible=1 
  and PlayDate > DateTime('Now', 'LocalTime', '-' || ? || ' Day')
  and g.GameType = 'EM'
GROUP BY cgl.GameID 
HAVING TotalPlays > 1
ORDER BY TotalPlays DESC
LIMIT 250
"""

LOCAL_CATALOG_QUERY = f"""
SELECT GameId, GameDisplay, GameYear, Manufact, GameType, GameRating,
    coalesce(CAST(julianday('now') - julianday(DateFileUpdated) AS INTEGER),6*365) AS LastUpdatedDays
FROM Games 
WHERE EMUID in ({TARGET_EMU_IDS}) 
  and visible=1
  and (? = 0 OR NULLIF(GameRating, '') >= ? OR (? = 1 AND (GameRating IS NULL OR GameRating = '' OR GameRating = 0)))
ORDER BY GameDisplay ASC
"""

def log(msg):
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}")

# ==============================================================================
# DATA EXTRACTION STEP
# ==============================================================================
def extract_data():
    if not os.path.exists(DB_PATH):
        log(f"[-] Error: PinUp Popper database not found at {DB_PATH}")
        sys.exit(1)

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    log(f"[+] Gathering play metrics from the last {HISTORY_DAYS} days...")
    cursor.execute(HISTORY_QUERY_GENERAL, (HISTORY_DAYS,))
    played_history_general = [dict(row) for row in cursor.fetchall()]

    log(f"[+] Gathering EM play metrics from the last {HISTORY_DAYS} days...")
    cursor.execute(HISTORY_QUERY_EM, (HISTORY_DAYS,))
    played_history_em = [dict(row) for row in cursor.fetchall()]

    log("[+] Extracting local catalog from your cabinet emulators...")
    cursor.execute(LOCAL_CATALOG_QUERY, (MIN_GAME_RATING, MIN_GAME_RATING, INCLUDE_NON_RATED))
    available_catalog = [dict(row) for row in cursor.fetchall()]

    conn.close()

    def fmt_rating(val):
        # 1-5 are valid; anything else (None, '', 0, out-of-range) is unknown
        try:
            r = int(val)
            if 1 <= r <= 5:
                return str(r)
        except (TypeError, ValueError):
            pass
        return ""

    lines = []
    lines.append("## top_played_general [id,plays,secs,last_played,game,year,mfr,type,rating]")
    for row in played_history_general:
        lines.append(f"{row.get('GameID', '')},{row['TotalPlays']},{row['TotalTimePlayedSecs']},{row.get('LastPlayedDays', '')},{row['GameDisplay']},{row.get('GameYear', '')},{row.get('Manufact', '')},{row.get('GameType', '')},{fmt_rating(row.get('GameRating'))}")
    lines.append("")
    lines.append("## top_played_em [id,plays,secs,last_played,game,year,mfr,type,rating]")
    for row in played_history_em:
        lines.append(f"{row.get('GameID', '')},{row['TotalPlays']},{row['TotalTimePlayedSecs']},{row.get('LastPlayedDays', '')},{row['GameDisplay']},{row.get('GameYear', '')},{row.get('Manufact', '')},{row.get('GameType', '')},{fmt_rating(row.get('GameRating'))}")
    lines.append("")
    lines.append("## candidate_pool [id,game,year,mfr,type,rating,updated_days_ago]")
    for row in available_catalog:
        lines.append(f"{row.get('GameID', '')},{row['GameDisplay']},{row.get('GameYear', '')},{row.get('Manufact', '')},{row.get('GameType', '')},{fmt_rating(row.get('GameRating'))},{row.get('LastUpdatedDays', '')}")

    payload = "\n".join(lines)

    with open(PAYLOAD_PATH, 'w', encoding='utf-8') as f:
        f.write(payload)

    log(f"[+] Saved prompt payload to: {PAYLOAD_PATH}")
    return payload

# ==============================================================================
# AI GENERATION STEP
# ==============================================================================
def fetch_recommendations(cabinet_data):
    if not GEMINI_API_KEY:
        log("[-] Error: GEMINI_API_KEY environment variable is not set.")
        print("    Please set it before running. Example: set GEMINI_API_KEY=your_key")
        sys.exit(1)
    # if not GROQ_API_KEY:
    #     log("[-] Error: GROQ_API_KEY environment variable is not set.")
    #     print("    Please set it before running. Example: set GROQ_API_KEY=your_key")
    #     sys.exit(1)

    # Build the not_owned portion of the prompt only if enabled
    if INCLUDE_NOT_OWNED:
        not_owned_key_instruction = f"""       - "not_owned": an array of EXACTLY {NUM_NOT_OWNED} recommendations for tables the user does NOT already have in their candidate_pool but that match their play history patterns. Use your knowledge of the full virtual pinball ecosystem, including the VPIN Spreadsheet current CSV export at https://virtualpinballspreadsheet.github.io/export, to identify high-quality tables the user is missing. These table must exist virtually and available in the virtual pinball community but are absent from the user's local catalog."""
        not_owned_field_instruction = """    For "not_owned" recommendations, each object must include: "game" (table name as commonly known), "confidence" (0-1 score), a location/link where it is available (if known), and "reason" (a brief explanation of why this table fits the user's preferences). Do NOT include an "id" field since these tables are not in the local database. Note that table naming across sources can be fuzzy and inexact, so use best-effort matching when checking whether a table is already in the candidate_pool."""
        json_keys_desc = "three keys"
    else:
        not_owned_key_instruction = ""
        not_owned_field_instruction = ""
        json_keys_desc = "two keys"

    prompt = f"""
    You are an expert Virtual Pinball recommendation engine.
    Your objective is to analyze a user's play history and select the best matching games from an available "candidate_pool". 
    The data below uses a compact format:
    - "top_played_general" rows are: id,plays,seconds,last_played,game,year,manufacturer,type,rating (non-EM history)
    - "top_played_em" rows are: id,plays,seconds,last_played,game,year,manufacturer,type,rating (EM history)
    - "id" is the unique GameId from the database
    - "plays" is the total number of play sessions in the last {HISTORY_DAYS} days
    - "seconds" is the total time played in seconds in the last {HISTORY_DAYS} days
    - "last_played" is the number of days since the game was last played
    - "candidate_pool" rows are: id,game,year,manufacturer,type,rating,updated_days_ago
    - "id" is the unique GameId from the database
    - "updated_days_ago" is how many days ago the table file was last updated
    - "rating" is the user's personal star rating for the table on a 1-5 scale where 5 is the highest (best) and 1 is the lowest (worst). An empty/missing rating value means unknown/unrated and should be treated as neutral (neither favored nor penalized).

    ---
    [INPUT DATA]
    {cabinet_data}
    
    ---
    [ANALYSIS STEP]
    Before selecting tables, analyze the play history in two separate tracks:
    1. General History (top_played_general): Identify favorite eras (e.g., 90s DMD), manufacturers (e.g., Williams, Bally, Stern), and high-engagement tables.
    2. EM History (top_played_em): Identify mechanical style preferences (e.g., Gottlieb 70s) and high-engagement tables.
    
    ---
    [SCORING CRITERIA]
    Rank candidate tables using the following scoring logic:
    1. Core Match: High points for matching a manufacturer or era dominant in the user's top history.
    2. Theme Alignment: Bonus points if the table's theme aligns with frequently played tables (e.g., if user plays a lot of space-themed tables, a new space-themed table gets a boost).
    3. Freshness Boost: Add a moderate weight if "updated_days_ago" is less than 180.
    4. Creator Boost: Add a moderate weight if the game name or metadata from online sources indicates it is by: VPW, SuperTilted, VPX Wizards, Pincredibles, Uncle Paulie, or EMUnderdogs.
    5. User Rating Weight: Use the user's personal "rating" (1-5 scale) as a strong signal of taste.
       - In history: tables rated 5 are top favorites — heavily weight their manufacturer/era/theme patterns. Tables rated 4 are strong positives. Rating 3 is neutral. Ratings 1-2 are dislikes — however, don't overly penalize them because we don't know the reason - it could be a low quality version of an otherwise fantastic theme.
       - In candidate_pool: strongly prefer candidates rated 4-5, give a small boost to 3, and penalize candidates rated 1-2 so they are only recommended if other signals are overwhelmingly strong.
       - An empty/missing rating means unknown — treat as neutral; do not boost or penalize based on rating alone.
    
    ---
    [CRITICAL CONSTRAINTS]
    - Separated Output: "general" recommendations must NEVER have type 'EM'. "em" recommendations must ALWAYS have type 'EM'.
    - Strict Counts: Output exactly {NUM_RECOMMENDATIONS} items for "general" and exactly {NUM_RECOMMENDATIONS_EM} items for "em".
    - Exact Matching: The "id" and "game" string fields must perfectly match the database values provided in the candidate pool.
    - Deduplication: Never recommend the same base game title twice. If a game has a standard version and a "(Videos)" version in the pool, prioritize the standard version and discard the "(Videos)" version. Do not output both.
    - Candidate Isolation: Only recommend games that are explicitly listed in the "candidate_pool". 
    - Do not recommend games from the play history if they were last played within {REPLAY_WINDOW_DAYS} days (i.e., last_played < {REPLAY_WINDOW_DAYS}). Games in the history with last_played >= {REPLAY_WINDOW_DAYS} ARE eligible for recommendation since enough time has passed.

    ---
    [OUTPUT FORMAT]
    Return ONLY a raw JSON object. Do not include markdown formatting, markdown code blocks (such as ```json) or any conversational text. 

    JSON Schema:
    {{
      "general": [
        {{
          "id": <int/string GameId>,
          "game": "<string exact_name>",
          "confidence": <float between 0.0 and 1.0>
        }}
      ],
      "em": [
        {{
          "id": <int/string GameId>,
          "game": "<string exact_name>",
          "confidence": <float between 0.0 and 1.0>
        }}
      ]
    }}

    """

    log("[+] Initializing Gemini Client...")

    with open(PROMPT_PATH, 'w', encoding='utf-8') as f:
        f.write(prompt)
    log(f"[+] Saved full AI prompt to: {PROMPT_PATH}")

    client = genai.Client(api_key=GEMINI_API_KEY)
    # log("[+] Initializing Groq Client...")
    # client = Groq(api_key=GROQ_API_KEY)

    try:
        log("[+] Querying AI engine for recommendations...")
        ai_start = time.time()
        response = client.models.generate_content(
            model='gemini-2.5-flash',
            contents=prompt,
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                temperature=0.4,
            ),
        )
        ai_elapsed = time.time() - ai_start

        recommendations = json.loads(response.text.strip())

        # Log token usage if available
        usage = getattr(response, 'usage_metadata', None)
        if usage:
            log(f"[+] Tokens — prompt: {usage.prompt_token_count}, response: {usage.candidates_token_count}, total: {usage.total_token_count}")

        # --- Groq alternative ---
        # response = client.chat.completions.create(
        #     model="llama-3.3-70b-versatile",
        #     messages=[
        #         {"role": "system", "content": "You are a JSON-only response bot. Return only valid JSON arrays with no markdown or commentary."},
        #         {"role": "user", "content": prompt}
        #     ],
        #     temperature=0.3,
        #     response_format={"type": "json_object"},
        # )
        # recommendations = json.loads(response.choices[0].message.content.strip())

        with open(RECS_OUTPUT_PATH, 'w', encoding='utf-8') as f:
            json.dump(recommendations, f, indent=4)

        log(f"[+] AI generation completed in {ai_elapsed:.1f}s")
        print("\n==================================================")
        print(f" SUCCESS: Generated recommendations")
        print("==================================================")
        general_recs = recommendations.get("general", [])
        em_recs = recommendations.get("em", [])
        print(f"  --- General ({len(general_recs)}) ---")
        for i, rec in enumerate(general_recs, 1):
            print(f"  {i}. {rec}")
        print(f"  --- EM ({len(em_recs)}) ---")
        for i, rec in enumerate(em_recs, 1):
            print(f"  {i}. {rec}")
        if INCLUDE_NOT_OWNED:
            not_owned_recs = recommendations.get("not_owned", [])
            print(f"  --- Not Owned ({len(not_owned_recs)}) ---")
            for i, rec in enumerate(not_owned_recs, 1):
                print(f"  {i}. {rec}")
        print(f"==================================================")
        log(f"[+] Final JSON saved to: {RECS_OUTPUT_PATH}")

        return recommendations

    except Exception as e:
        log(f"[-] AI Generation or JSON parsing failed: {e}")
        return None

# ==============================================================================
# PLAYLIST UPDATE STEP
# ==============================================================================
def update_playlist(recommendations):
    all_recs = recommendations.get("general", []) + recommendations.get("em", [])
    sorted_recs = sorted(all_recs, key=lambda r: (-r.get("confidence", 0), r.get("game", "")))

    game_ids = []
    for rec in sorted_recs:
        game_id = rec.get("id") or rec.get("GameId")
        if game_id:
            game_ids.append(int(game_id))

    if not game_ids:
        log("[-] No GameIds found in recommendations. Skipping playlist update.")
        return

    log(f"[+] Updating playlist {RECS_PLAYLIST_ID} with {len(game_ids)} recommendations...")
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    try:
        cursor.execute("DELETE FROM PlayListDetails WHERE PlayListID = ?", (RECS_PLAYLIST_ID,))
        log(f"[+] Cleared existing entries from playlist {RECS_PLAYLIST_ID}.")

        for order, game_id in enumerate(game_ids, 1):
            cursor.execute(
                "INSERT INTO PlayListDetails (PlayListID, GameID, Visible, DisplayOrder, LastPlayed, NumPlayed, isFav) "
                "VALUES (?, ?, 1, ?, '', 0, 0)",
                (RECS_PLAYLIST_ID, game_id, order)
            )

        conn.commit()
        log(f"[+] Inserted {len(game_ids)} games into playlist {RECS_PLAYLIST_ID}.")
    except Exception as e:
        log(f"[-] Playlist update failed: {e}")
        conn.rollback()
    finally:
        conn.close()

# ==============================================================================
# GAME TAG UPDATE STEP (alternate approach)
# ==============================================================================
def update_game_tags(recommendations):
    # Only tag locally owned tables (general + em); not_owned have no GameId
    all_recs = recommendations.get("general", []) + recommendations.get("em", [])
    sorted_recs = sorted(all_recs, key=lambda r: (-r.get("confidence", 0), r.get("game", "")))

    game_ids = []
    for rec in sorted_recs:
        game_id = rec.get("id") or rec.get("GameId")
        if game_id:
            game_ids.append(int(game_id))

    if not game_ids:
        log("[-] No GameIds found in recommendations. Skipping game tag update.")
        return

    log(f"[+] Updating AI_Suggested tags for {len(game_ids)} recommendations...")
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    try:
        # Remove all existing AI_Suggested tags
        cursor.execute("""
            UPDATE Games
            SET TAGS = TRIM(
                REPLACE(
                    REPLACE(
                        REPLACE(
                            ',' || TAGS || ',', 
                            ',AI_Suggested,', 
                            ','
                        ), 
                        ', AI_Suggested,', 
                        ','
                    ),
                    ',AI_Suggested ,', 
                    ','
                ), 
                ','
            )
            WHERE TAGS LIKE '%AI_Suggested%'
        """)
        log(f"[+] Cleared existing AI_Suggested tags.")

        # Add AI_Suggested tag to recommended games
        placeholders = ','.join(str(gid) for gid in game_ids)
        cursor.execute(f"""
            UPDATE Games
            SET TAGS = CASE 
                WHEN TAGS IS NULL OR TRIM(TAGS) = '' THEN 'AI_Suggested'
                ELSE TAGS || ', AI_Suggested'
            END
            WHERE GameID IN ({placeholders})
        """)

        conn.commit()
        log(f"[+] Tagged {len(game_ids)} games with AI_Suggested.")
    except Exception as e:
        log(f"[-] Game tag update failed: {e}")
        conn.rollback()
    finally:
        conn.close()

# ==============================================================================
# MAIN EXECUTION
# ==============================================================================
if __name__ == "__main__":
    needs_refresh = True

    if os.path.exists(RECS_OUTPUT_PATH):
        file_age_minutes = (time.time() - os.path.getmtime(RECS_OUTPUT_PATH)) / 60
        if file_age_minutes < MAX_AGE_MINUTES:
            log(f"[+] Recommendations file found but only {file_age_minutes:.1f} min old (threshold: {MAX_AGE_MINUTES} min). Skipping.")
            sys.exit(0)
        else:
            log(f"[+] Recommendations file is {file_age_minutes:.1f} min old (threshold: {MAX_AGE_MINUTES} min). Refreshing...")
            needs_refresh = True

    if needs_refresh:
        cabinet_payload = extract_data()
        recommendations = fetch_recommendations(cabinet_payload)
        if recommendations:
            if UPDATE_PLAYLIST:
                update_playlist(recommendations)
            if ADD_SUGGESTED_TAGS:
                update_game_tags(recommendations)
