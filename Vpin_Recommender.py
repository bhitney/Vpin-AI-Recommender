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
RECS_OUTPUT_PATH = os.path.join(SCRIPT_DIR, "ai_recommendations.json")

# Minimum age (in minutes) before re-generating recommendations
PAYLOAD_MAX_AGE_MINUTES = 1

# PinUp Popper System Settings
DB_PATH = r"C:\vPinball\PinUPSystem\PUPDatabase.db"
TARGET_EMU_IDS = "1,2,3,4" # add whaevever EMUIDs to include in analysis

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

# Include "not_owned" recommendations from the VPIN Spreadsheet?
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
    g.GameId,
    GameDisplay, 
    GameYear, 
    Manufact,
    GameType
FROM Games AS g 
JOIN CustomGameLog cgl ON g.GameID = cgl.GameID 
WHERE g.EMUID in ({TARGET_EMU_IDS}) 
  and g.visible=1 
  and PlayDate > DateTime('Now', 'LocalTime', '-' || ? || ' Day')
  and g.GameType <> 'EM'
GROUP BY cgl.GameID 
HAVING TotalPlays > 1
ORDER BY TotalPlays DESC
LIMIT 60
"""

HISTORY_QUERY_EM = f"""
SELECT 
    count(1) as TotalPlays, 
    sum(SessionPlayedSecs) as TotalTimePlayedSecs, 
    g.GameId,
    GameDisplay, 
    GameYear, 
    Manufact,
    GameType
FROM Games AS g 
JOIN CustomGameLog cgl ON g.GameID = cgl.GameID 
WHERE g.EMUID in ({TARGET_EMU_IDS}) 
  and g.visible=1 
  and PlayDate > DateTime('Now', 'LocalTime', '-' || ? || ' Day')
  and g.GameType = 'EM'
GROUP BY cgl.GameID 
HAVING TotalPlays > 1
ORDER BY TotalPlays DESC
LIMIT 60
"""

LOCAL_CATALOG_QUERY = f"""
SELECT GameId, GameDisplay, GameYear, Manufact, GameType,
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

    lines = []
    lines.append("## top_played_general [id,plays,secs,game,year,mfr,type]")
    for row in played_history_general:
        lines.append(f"{row.get('GameID', '')},{row['TotalPlays']},{row['TotalTimePlayedSecs']},{row['GameDisplay']},{row.get('GameYear', '')},{row.get('Manufact', '')},{row.get('GameType', '')}")
    lines.append("")
    lines.append("## top_played_em [id,plays,secs,game,year,mfr,type]")
    for row in played_history_em:
        lines.append(f"{row.get('GameID', '')},{row['TotalPlays']},{row['TotalTimePlayedSecs']},{row['GameDisplay']},{row.get('GameYear', '')},{row.get('Manufact', '')},{row.get('GameType', '')}")
    lines.append("")
    lines.append("## candidate_pool [id,game,year,mfr,type,updated_days_ago]")
    for row in available_catalog:
        lines.append(f"{row.get('GameID', '')},{row['GameDisplay']},{row.get('GameYear', '')},{row.get('Manufact', '')},{row.get('GameType', '')},{row.get('LastUpdatedDays', '')}")

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
    You are an expert Virtual Pinball recommendation engine running inside a physical arcade cabinet setup.
    Your job is to look at the user's play history metrics and find relevant tables from the available candidate pool that they should play or explore next.
    The play history is split into two sections: "top_played_general" for non-EM tables and "top_played_em" for EM (electromechanical) tables.
    You must return separate sets of recommendations.

    The data below uses a compact format:
    - "top_played_general" rows are: id,plays,seconds,game,year,manufacturer,type (non-EM history)
    - "top_played_em" rows are: id,plays,seconds,game,year,manufacturer,type (EM history)
    - "candidate_pool" rows are: id,game,year,manufacturer,type,updated_days_ago
    - "id" is the unique GameId from the database
    - "updated_days_ago" is how many days ago the table file was last updated

    {cabinet_data}

    CRITICAL INSTRUCTIONS:
    - Identify patterns in the user's history (e.g., preference for a specific era/year, specific manufacturers like Williams/Bally, or high play counts/times). Analyze general and EM history separately.
    - Return a JSON object with {json_keys_desc}:
       - "general": an array of EXACTLY {NUM_RECOMMENDATIONS} non-EM recommendations from the candidate_pool (where type is NOT 'EM') based on the top_played_general history.
       - "em": an array of EXACTLY {NUM_RECOMMENDATIONS_EM} EM recommendations from the candidate_pool (where type IS 'EM') based on the top_played_em history.
{not_owned_key_instruction}
    - For "general" and "em" recommendations, each object must include: "id" (GameId), "game" (exact game name from candidate_pool), "confidence" (0-1 score based on match quality).
    {not_owned_field_instruction}
    - The names in "general" and "em" output MUST exactly match the game name from the candidate pool so the local system can parse them.
    - Some games with might have "(Videos)" in the title - use the version without "(Videos)"if it exists in the candidate pool, and don't duplicate recommendations by having both a "(Videos)" and non-videos game of the same name.
    - Do not include any chat commentary, explanations, markdown formatting, or backticks. Return ONLY the JSON object specified.
    - Give a confidence boost to tables that have been recently updated (low updated_days_ago values), particularly those updated within the last 180 days.
    - Give a confidence boost to tables known to be from high-quality creators: VPW, SuperTilted, VPX Wizards, Pincredibles, Uncle Paulie, and EMUnderdogs. Use your knowledge of the Virtual Pinball community (including the Virtual Pinball Spreadsheet at virtualpinballspreadsheet.github.io, VPUniverse, and VPForums) to identify which tables in the candidate pool are created by these groups, even if the creator name is not in the game filename. For example, "The Matrix (Original 2026)" is a known VPW/Pincredibles release.
    """

    log("[+] Initializing Gemini Client...")
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
                temperature=0.3,
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

    if os.path.exists(PAYLOAD_PATH):
        file_age_minutes = (time.time() - os.path.getmtime(PAYLOAD_PATH)) / 60
        if file_age_minutes < PAYLOAD_MAX_AGE_MINUTES:
            log(f"[+] Payload file found but only {file_age_minutes:.1f} min old (threshold: {PAYLOAD_MAX_AGE_MINUTES} min). Skipping.")
            sys.exit(0)
        else:
            log(f"[+] Payload file is {file_age_minutes:.1f} min old (threshold: {PAYLOAD_MAX_AGE_MINUTES} min). Refreshing...")
            needs_refresh = True

    if needs_refresh:
        cabinet_payload = extract_data()
        recommendations = fetch_recommendations(cabinet_payload)
        if recommendations:
            if UPDATE_PLAYLIST:
                update_playlist(recommendations)
            if ADD_SUGGESTED_TAGS:
                update_game_tags(recommendations)
