import os
import sys
import sqlite3
import json
import time
import requests
# from groq import Groq
from google import genai
from google.genai import types

# py -m pip install requests groq google-genai

# ==============================================================================
# CONFIGURABLE PARAMETERS & PATHS
# ==============================================================================
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PAYLOAD_PATH = os.path.join(SCRIPT_DIR, "ai_prompt_payload_compact.txt") # "ai_prompt_payload.json")
RECS_OUTPUT_PATH = os.path.join(SCRIPT_DIR, "ai_recommendations.json")

# Minimum age (in minutes) before re-generating recommendations
PAYLOAD_MAX_AGE_MINUTES = 1

# PinUp Popper System Settings
DB_PATH = r"C:\vPinball\PinUPSystem\PUPDatabase.db"
TARGET_EMU_IDS = (1, 2, 3, 4, 5)

# Playlist ID to update with AI recommendations
RECS_PLAYLIST_ID = 1234

# Number of tables to recommend
NUM_RECOMMENDATIONS = 15
NUM_RECOMMENDATIONS_EM = 10

# Minimum game rating filter for candidate pool (0 = no filter)
MIN_GAME_RATING = 3
INCLUDE_NON_RATED = 1

# Number of days of play history to analyze
HISTORY_DAYS = 120

# --- MODE SELECTOR ---
# Set to 'LOCAL' to recommend tables you already have installed.
# Set to 'VPS' to recommend external tables from the Virtual Pinball Spreadsheet.
CATALOG_MODE = "LOCAL" 

VPS_JSON_URL = "https://githubusercontent.com"

# Pull the API key from the environment
# GROQ_API_KEY = os.environ.get("GROQ_API_KEY")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")

# ==============================================================================
# SQL QUERIES
# ==============================================================================
HISTORY_QUERY_GENERAL = """
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
WHERE g.EMUID in (?, ?, ?) 
  and g.visible=1 
  and PlayDate > DateTime('Now', 'LocalTime', '-' || ? || ' Day')
  and g.GameType <> 'EM'
GROUP BY cgl.GameID 
HAVING TotalPlays > 1
ORDER BY TotalPlays DESC
LIMIT 60
"""

HISTORY_QUERY_EM = """
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
WHERE g.EMUID in (?, ?, ?) 
  and g.visible=1 
  and PlayDate > DateTime('Now', 'LocalTime', '-' || ? || ' Day')
  and g.GameType = 'EM'
GROUP BY cgl.GameID 
HAVING TotalPlays > 1
ORDER BY TotalPlays DESC
LIMIT 60
"""

LOCAL_CATALOG_QUERY = """
SELECT GameId, GameDisplay, GameYear, Manufact, GameType,
    coalesce(CAST(julianday('now') - julianday(DateFileUpdated) AS INTEGER),6*365) AS LastUpdatedDays
FROM Games 
WHERE EMUID in (?, ?, ?) 
  and visible=1
  and (? = 0 OR NULLIF(GameRating, '') >= ? OR (? = 1 AND (GameRating IS NULL OR GameRating = '' OR GameRating = 0)))
ORDER BY GameDisplay ASC
"""

# ==============================================================================
# DATA EXTRACTION STEP
# ==============================================================================
def extract_data():
    if not os.path.exists(DB_PATH):
        print(f"[-] Error: PinUp Popper database not found at {DB_PATH}")
        sys.exit(1)

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    print(f"[+] Gathering play metrics from the last {HISTORY_DAYS} days...")
    cursor.execute(HISTORY_QUERY_GENERAL, (*TARGET_EMU_IDS, HISTORY_DAYS))
    played_history_general = [dict(row) for row in cursor.fetchall()]

    print(f"[+] Gathering EM play metrics from the last {HISTORY_DAYS} days...")
    cursor.execute(HISTORY_QUERY_EM, (*TARGET_EMU_IDS, HISTORY_DAYS))
    played_history_em = [dict(row) for row in cursor.fetchall()]
    
    if CATALOG_MODE.upper() == "VPS":
        print("[+] Downloading live global database from VPS...")
        try:
            response = requests.get(VPS_JSON_URL, timeout=15)
            response.raise_for_status()
            vps_data = response.json()
            available_catalog = []
            for table_id, details in vps_data.items():
                available_catalog.append({
                    "GameDisplay": details.get("name", "Unknown Table"),
                    "GameYear": details.get("year", ""),
                    "Manufact": details.get("manufacturer", "")
                })
            mode_used = "VPS (Online Discovery)"
        except Exception as e:
            print(f"[!] VPS fetch failed ({e}). Falling back to local catalog.")
            cursor.execute(LOCAL_CATALOG_QUERY, (*TARGET_EMU_IDS, MIN_GAME_RATING, MIN_GAME_RATING, INCLUDE_NON_RATED))
            available_catalog = [dict(row) for row in cursor.fetchall()]
            mode_used = "LOCAL (Fallback)"
    else:
        print("[+] Extracting local catalog from your cabinet emulators...")
        cursor.execute(LOCAL_CATALOG_QUERY, (*TARGET_EMU_IDS, MIN_GAME_RATING, MIN_GAME_RATING, INCLUDE_NON_RATED))
        available_catalog = [dict(row) for row in cursor.fetchall()]
        mode_used = "LOCAL (Cabinet Inventory)"

    conn.close()

    lines = []
    lines.append(f"mode:{mode_used}")
    lines.append("")
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

    print(f"[+] Saved prompt payload to: {PAYLOAD_PATH}")
    return payload

# ==============================================================================
# AI GENERATION STEP
# ==============================================================================
def fetch_recommendations(cabinet_data):
    if not GEMINI_API_KEY:
        print("[-] Error: GEMINI_API_KEY environment variable is not set.")
        print("    Please set it before running. Example: set GEMINI_API_KEY=your_key")
        sys.exit(1)
    # if not GROQ_API_KEY:
    #     print("[-] Error: GROQ_API_KEY environment variable is not set.")
    #     print("    Please set it before running. Example: set GROQ_API_KEY=your_key")
    #     sys.exit(1)

    prompt = f"""
    You are an expert Virtual Pinball recommendation engine running inside a physical arcade cabinet setup.
    Your job is to look at the user's play history metrics and find relevant tables from the available candidate pool that they should play or explore next.
    The play history is split into two sections: "top_played_general" for non-EM tables and "top_played_em" for EM (electromechanical) tables.
    You must return two separate sets of recommendations.

    The data below uses a compact format:
    - "top_played_general" rows are: id,plays,seconds,game,year,manufacturer,type (non-EM history)
    - "top_played_em" rows are: id,plays,seconds,game,year,manufacturer,type (EM history)
    - "candidate_pool" rows are: id,game,year,manufacturer,type,updated_days_ago
    - "id" is the unique GameId from the database
    - "updated_days_ago" is how many days ago the table file was last updated

    {cabinet_data}

    CRITICAL INSTRUCTIONS:
    1. Identify patterns in the user's history (e.g., preference for a specific era/year, specific manufacturers like Williams/Bally, or high play counts/times). Analyze general and EM history separately.
    2. Return a JSON object with two keys:
       - "general": an array of EXACTLY {NUM_RECOMMENDATIONS} non-EM recommendations from the candidate_pool (where type is NOT 'EM') based on the top_played_general history.
       - "em": an array of EXACTLY {NUM_RECOMMENDATIONS_EM} EM recommendations from the candidate_pool (where type IS 'EM') based on the top_played_em history.
    3. Each recommendation object must include: "id" (GameId), "game" (exact game name from candidate_pool), "confidence" (0-1 score based on match quality).
    4. The names in your output MUST exactly match the game name from the candidate pool so the local system can parse them.
    5. Do not include any chat commentary, explanations, markdown formatting, or backticks. Return ONLY the JSON object specified.
    6. Give a confidence boost to tables that have been recently updated (low updated_days_ago values), particularly those updated within the last 180 days.
    7. Give a confidence boost to tables known to be from high-quality creators: VPW, SuperTilted, VPX Wizards, Pincredibles, and EMUnderdogs. Use your knowledge of the Virtual Pinball community (including the Virtual Pinball Spreadsheet at virtualpinballspreadsheet.github.io and VPUniverse) to identify which tables in the candidate pool are created by these groups, even if the creator name is not in the game filename. For example, "The Matrix (Original 2026)" is a known VPW/Pincredibles release.
    """

    print("[+] Initializing Gemini Client...")
    client = genai.Client(api_key=GEMINI_API_KEY)
    # print("[+] Initializing Groq Client...")
    # client = Groq(api_key=GROQ_API_KEY)

    try:
        print("[+] Querying AI engine for recommendations...")
        response = client.models.generate_content(
            model='gemini-2.5-flash',
            contents=prompt,
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                temperature=0.3,
            ),
        )

        recommendations = json.loads(response.text.strip())

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
        print(f"==================================================")
        print(f"[+] Final JSON saved to: {RECS_OUTPUT_PATH}\n")

        return recommendations

    except Exception as e:
        print(f"[-] AI Generation or JSON parsing failed: {e}")
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
        print("[-] No GameIds found in recommendations. Skipping playlist update.")
        return

    print(f"[+] Updating playlist {RECS_PLAYLIST_ID} with {len(game_ids)} recommendations...")
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    try:
        cursor.execute("DELETE FROM PlayListDetails WHERE PlayListID = ?", (RECS_PLAYLIST_ID,))
        print(f"[+] Cleared existing entries from playlist {RECS_PLAYLIST_ID}.")

        for order, game_id in enumerate(game_ids, 1):
            cursor.execute(
                "INSERT INTO PlayListDetails (PlayListID, GameID, Visible, DisplayOrder, LastPlayed, NumPlayed, isFav) "
                "VALUES (?, ?, 1, ?, '', 0, 0)",
                (RECS_PLAYLIST_ID, game_id, order)
            )

        conn.commit()
        print(f"[+] Inserted {len(game_ids)} games into playlist {RECS_PLAYLIST_ID}.")
    except Exception as e:
        print(f"[-] Playlist update failed: {e}")
        conn.rollback()
    finally:
        conn.close()

# ==============================================================================
# GAME TAG UPDATE STEP (alternate approach)
# ==============================================================================
def update_game_tags(recommendations):
    all_recs = recommendations.get("general", []) + recommendations.get("em", [])
    sorted_recs = sorted(all_recs, key=lambda r: (-r.get("confidence", 0), r.get("game", "")))

    game_ids = []
    for rec in sorted_recs:
        game_id = rec.get("id") or rec.get("GameId")
        if game_id:
            game_ids.append(int(game_id))

    if not game_ids:
        print("[-] No GameIds found in recommendations. Skipping game tag update.")
        return

    print(f"[+] Updating AI_Suggested tags for {len(game_ids)} recommendations...")
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
        print(f"[+] Cleared existing AI_Suggested tags.")

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
        print(f"[+] Tagged {len(game_ids)} games with AI_Suggested.")
    except Exception as e:
        print(f"[-] Game tag update failed: {e}")
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
            print(f"[+] Payload file found but only {file_age_minutes:.1f} min old (threshold: {PAYLOAD_MAX_AGE_MINUTES} min). Skipping.")
            sys.exit(0)
        else:
            print(f"[+] Payload file is {file_age_minutes:.1f} min old (threshold: {PAYLOAD_MAX_AGE_MINUTES} min). Refreshing...")
            needs_refresh = True

    if needs_refresh:
        cabinet_payload = extract_data()
        recommendations = fetch_recommendations(cabinet_payload)
        if recommendations:
            # update_playlist(recommendations)
            update_game_tags(recommendations)
