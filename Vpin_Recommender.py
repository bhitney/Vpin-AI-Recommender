import os
import sys
import sqlite3
import json
import time
from datetime import datetime
# from groq import Groq
#
# Provider SDKs are imported lazily inside their helper functions so that you
# only need the package for the provider you actually use:
#   Azure AI Foundry:  pip install openai azure-identity
#   Google Gemini:     pip install google-genai

# ==============================================================================
# CONFIGURABLE PARAMETERS & PATHS
# ==============================================================================
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PAYLOAD_PATH = os.path.join(SCRIPT_DIR, "ai_prompt_payload_compact.txt")
PROMPT_PATH = os.path.join(SCRIPT_DIR, "ai_prompt_full.txt")
RECS_OUTPUT_PATH = os.path.join(SCRIPT_DIR, "ai_recommendations.json")

# Minimum age (in minutes) before re-generating recommendations
MAX_AGE_MINUTES = 1440

# PinUp Popper System Settings
DB_PATH = r"C:\vPinball\PinUPSystem\PUPDatabase.db"
TARGET_EMU_IDS = "1,2,3" # add whaevever EMUIDs to include in analysis

# Update a PinUp Popper playlist with recommended games?
UPDATE_PLAYLIST = False
RECS_PLAYLIST_ID = 1234

# Tag recommended games with 'AI_Suggested'?
ADD_SUGGESTED_TAGS = True

# Number of tables to recommend
NUM_RECOMMENDATIONS = 15
NUM_RECOMMENDATIONS_EM = 10

# Minimum game rating filter for candidate pool (0 = no filter)
MIN_GAME_RATING = 0
INCLUDE_NON_RATED = 1

# Number of days of play history to analyze
HISTORY_DAYS = 365

# Games played within this many days are excluded from recommendations.
# Games in the history but last played MORE than this many days ago can still be recommended.
REPLAY_WINDOW_DAYS = 220

# How strongly the user's personal star "rating" (1-5) should influence recommendations.
# One of:
#   "none"     - Ignore ratings entirely; rank purely on play behavior, manufacturer/era/theme
#                patterns, freshness, and creator. Use when you want discovery driven only by
#                what you actually play, not by past ratings.
#   "light"    - Ratings are only a minor tie-breaker between otherwise-close candidates.
#   "moderate" - Ratings are one meaningful signal balanced against play frequency/engagement
#                and pattern matching (recommended default).
#   "strong"   - Ratings are a primary signal of taste; heavily weight 5-star patterns and
#                strongly prefer 4-5 rated candidates.
RATING_INFLUENCE = "moderate"

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
# AI PROVIDER SETTINGS
# ==============================================================================
# Primary AI backend to use: "azure" (Azure AI Foundry) or "gemini" (Google).
# Override at runtime with the AI_PROVIDER environment variable.
AI_PROVIDER = os.environ.get("AI_PROVIDER", "azure").strip().lower()

# If the primary provider fails (auth, quota, network, bad JSON), automatically
# fall back to the other provider. Set to False to disable fallback.
AI_FALLBACK = True

# --- Azure AI Foundry (keyless Entra ID auth; run `az login` first) ---
# The resource has local API-key auth disabled by org policy, so authentication
# uses your Azure CLI / Entra ID identity via DefaultAzureCredential.
AZURE_OPENAI_ENDPOINT = os.environ.get(
    "AZURE_OPENAI_ENDPOINT", "https://opsiq-foundry.cognitiveservices.azure.com/")
AZURE_OPENAI_DEPLOYMENT = os.environ.get("AZURE_OPENAI_DEPLOYMENT", "vpin-recommender-gpt5")
AZURE_OPENAI_API_VERSION = os.environ.get("AZURE_OPENAI_API_VERSION", "2024-10-21")

# Sampling temperature for the Azure model. Reasoning models (gpt-5, o-series)
# only accept the default and reject a custom value — set this to None for them.
# Non-reasoning models (e.g. gpt-4.1) work well around 0.4. If a model rejects
# the configured temperature, the script automatically retries without it.
_azure_temp_env = os.environ.get("AZURE_OPENAI_TEMPERATURE")
if _azure_temp_env is None:
    AZURE_OPENAI_TEMPERATURE = None  # default suits the gpt-5 deployment above
elif _azure_temp_env.strip().lower() in ("", "none"):
    AZURE_OPENAI_TEMPERATURE = None
else:
    AZURE_OPENAI_TEMPERATURE = float(_azure_temp_env)

# --- Google Gemini ---
GEMINI_MODEL = os.environ.get("GEMINI_MODEL", "gemini-2.5-flash")

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
# AI PROVIDER BACKENDS
# ==============================================================================
def _call_azure(prompt):
    """Call Azure AI Foundry via keyless Entra ID auth. Returns (text, usage_str)."""
    from azure.identity import (
        AzureCliCredential,
        DefaultAzureCredential,
        ChainedTokenCredential,
        get_bearer_token_provider,
    )
    from openai import AzureOpenAI

    log(f"[+] Initializing Azure AI Foundry client (deployment: {AZURE_OPENAI_DEPLOYMENT})...")
    # Prefer the Azure CLI identity (run `az login`), then fall back to the
    # broader DefaultAzureCredential chain (managed identity, env vars, etc.).
    credential = ChainedTokenCredential(AzureCliCredential(), DefaultAzureCredential())
    token_provider = get_bearer_token_provider(
        credential, "https://cognitiveservices.azure.com/.default")
    client = AzureOpenAI(
        azure_endpoint=AZURE_OPENAI_ENDPOINT,
        azure_ad_token_provider=token_provider,
        api_version=AZURE_OPENAI_API_VERSION,
    )
    request_kwargs = dict(
        model=AZURE_OPENAI_DEPLOYMENT,
        messages=[
            {"role": "system", "content": "You are a JSON-only response bot. Return only a single valid JSON object with no markdown or commentary."},
            {"role": "user", "content": prompt},
        ],
        response_format={"type": "json_object"},
    )
    if AZURE_OPENAI_TEMPERATURE is not None:
        request_kwargs["temperature"] = AZURE_OPENAI_TEMPERATURE

    try:
        response = client.chat.completions.create(**request_kwargs)
    except Exception as e:
        # Reasoning models (gpt-5, o-series) reject a custom temperature.
        # Self-heal by retrying once without it so swapping models "just works".
        if "temperature" in request_kwargs and "temperature" in str(e).lower():
            log("[*] Model rejected the configured temperature; retrying without it "
                "(set AZURE_OPENAI_TEMPERATURE=None to silence this).")
            request_kwargs.pop("temperature", None)
            response = client.chat.completions.create(**request_kwargs)
        else:
            raise
    text = response.choices[0].message.content.strip()
    usage = getattr(response, "usage", None)
    usage_str = None
    if usage:
        usage_str = f"prompt: {usage.prompt_tokens}, response: {usage.completion_tokens}, total: {usage.total_tokens}"
    return text, usage_str


def _call_gemini(prompt):
    """Call Google Gemini. Returns (text, usage_str)."""
    from google import genai
    from google.genai import types

    if not GEMINI_API_KEY:
        raise RuntimeError("GEMINI_API_KEY environment variable is not set.")
    log(f"[+] Initializing Gemini client (model: {GEMINI_MODEL})...")
    client = genai.Client(api_key=GEMINI_API_KEY)
    response = client.models.generate_content(
        model=GEMINI_MODEL,
        contents=prompt,
        config=types.GenerateContentConfig(
            response_mime_type="application/json",
            temperature=0.4,
        ),
    )
    text = response.text.strip()
    usage = getattr(response, "usage_metadata", None)
    usage_str = None
    if usage:
        usage_str = f"prompt: {usage.prompt_token_count}, response: {usage.candidates_token_count}, total: {usage.total_token_count}"
    return text, usage_str


_PROVIDERS = {"azure": _call_azure, "gemini": _call_gemini}


def _generate_with_provider(prompt):
    """Dispatch the prompt to the configured provider, with optional fallback.

    Returns (raw_text, provider_name). Raises if every attempted provider fails.
    """
    primary = AI_PROVIDER if AI_PROVIDER in _PROVIDERS else "azure"
    order = [primary]
    if AI_FALLBACK:
        order += [name for name in _PROVIDERS if name != primary]

    last_err = None
    for name in order:
        try:
            log(f"[+] Querying AI engine '{name}' for recommendations...")
            ai_start = time.time()
            text, usage_str = _PROVIDERS[name](prompt)
            ai_elapsed = time.time() - ai_start
            if usage_str:
                log(f"[+] Tokens — {usage_str}")
            log(f"[+] AI generation ({name}) completed in {ai_elapsed:.1f}s")
            return text, name
        except Exception as e:
            last_err = e
            log(f"[-] Provider '{name}' failed: {e}")
            if name != order[-1]:
                log("[+] Attempting fallback provider...")
    raise RuntimeError(f"All AI providers failed. Last error: {last_err}")


# ==============================================================================
# AI GENERATION STEP
# ==============================================================================
def fetch_recommendations(cabinet_data):
    # if not GROQ_API_KEY:
    #     log("[-] Error: GROQ_API_KEY environment variable is not set.")
    #     print("    Please set it before running. Example: set GROQ_API_KEY=your_key")
    #     sys.exit(1)

    # Build the optional "not_owned" portion of the prompt only if enabled.
    # NOTE: This is an experimental future hook (see INCLUDE_NOT_OWNED above). When
    # disabled, nothing related to not_owned is injected into the prompt so it cannot
    # influence or degrade the core recommendations.
    if INCLUDE_NOT_OWNED:
        not_owned_constraint = f"""    - Not-Owned Suggestions: In addition to the above, include a "not_owned" array with EXACTLY {NUM_NOT_OWNED} suggestions for tables the user does NOT already have in their candidate_pool but that fit their play history patterns. These are speculative "you might also enjoy" ideas drawn from your own knowledge of the virtual pinball ecosystem.
        - Each not_owned object must include: "game" (table name as commonly known), "confidence" (0.0-1.0), and "reason" (brief explanation of the fit). Do NOT include an "id" field for these.
        - Only suggest tables you are confident actually exist as virtual pinball recreations. If unsure a table exists virtually, do not include it. Treat these as lower-confidence than owned picks.
        - Table naming across sources is fuzzy; use best-effort matching and do NOT suggest a table that already appears (even approximately) in the candidate_pool."""
        not_owned_schema = f""",
      "not_owned": [
        {{
          "game": "<string table name>",
          "confidence": <float between 0.0 and 1.0>,
          "reason": "<string brief explanation>"
        }}
      ]"""
    else:
        not_owned_constraint = ""
        not_owned_schema = ""

    # Build scoring criterion #5 based on how strongly ratings should influence output.
    _rating_blocks = {
        "none": """    5. User Rating Weight: IGNORE the "rating" field entirely for this run. Do NOT boost or penalize any table (in history or candidate_pool) based on its star rating. Base taste inference purely on play behavior (plays, seconds, recency) and manufacturer/era/theme/platform patterns. A high or low rating must have ZERO effect on the ranking.""",
        "light": """    5. User Rating Weight: Treat the user's personal "rating" (1-5 scale) as a MINOR signal only — a tie-breaker, not a driver.
       - Primary signals are play behavior and manufacturer/era/theme/platform patterns. Only when two candidates are otherwise near-equal, nudge slightly toward the higher-rated one.
       - Do not let a high rating alone pull a table into the list if play-behavior/pattern signals are weak. An empty/missing rating is neutral.""",
        "moderate": """    5. User Rating Weight: Use the user's personal "rating" (1-5 scale) as ONE meaningful signal, balanced against play frequency/engagement and manufacturer/era/theme/platform patterns — it should inform but not dominate.
       - In history: a 5-star rating is a positive taste signal that reinforces that table's manufacturer/era/theme patterns, but weigh it alongside how often/recently the user actually plays. Rating 3 is neutral; 1-2 are mild negatives (don't overly penalize — it may just be a poor build of a great theme).
       - In candidate_pool: give a moderate preference to 4-5 rated candidates and a mild penalty to 1-2, but do not let rating override strong play-behavior or pattern matches.
       - An empty/missing rating means unknown — treat as neutral.""",
        "strong": """    5. User Rating Weight: Use the user's personal "rating" (1-5 scale) as a STRONG signal of taste.
       - In history: tables rated 5 are top favorites — heavily weight their manufacturer/era/theme patterns. Tables rated 4 are strong positives. Rating 3 is neutral. Ratings 1-2 are dislikes — however, don't overly penalize them because we don't know the reason - it could be a low quality version of an otherwise fantastic theme.
       - In candidate_pool: strongly prefer candidates rated 4-5, give a small boost to 3, and penalize candidates rated 1-2 so they are only recommended if other signals are overwhelmingly strong.
       - An empty/missing rating means unknown — treat as neutral; do not boost or penalize based on rating alone.""",
    }
    rating_criterion = _rating_blocks.get(RATING_INFLUENCE, _rating_blocks["moderate"])

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
    Reason through the following internally before selecting tables (do NOT include this reasoning in your output). Analyze the play history in two separate tracks:
    1. General History (top_played_general): Identify favorite eras (e.g., 90s DMD), manufacturers (e.g., Williams, Bally, Stern), hardware platforms (e.g., WPC, WPC-95, Stern Spike), and high-engagement tables.
    2. EM History (top_played_em): Identify mechanical style preferences (e.g., Gottlieb 70s) and high-engagement tables.
    
    ---
    [SCORING CRITERIA]
    Rank candidate tables using the following scoring logic:
    1. Core Match: High points for matching a manufacturer or era dominant in the user's top history.
    2. Theme Alignment: Bonus points if the table's theme aligns with frequently played tables (e.g., if user plays a lot of space-themed tables, a new space-themed table gets a boost).
    3. Freshness Boost: Add a moderate weight if "updated_days_ago" is less than 180.
    4. Creator Boost: Add a moderate weight if the game name or metadata from online sources indicates it is by: VPW, SuperTilted, VPX Wizards, Pincredibles, Uncle Paulie, or EMUnderdogs.
{rating_criterion}
    6. Respect Natural Clustering:

    ---
    [CONFIDENCE SCORE]
    The "confidence" value reflects how strongly a candidate matches the scoring criteria above:
    - 1.0 = near-certain match (aligns with multiple strong signals, e.g., a favored manufacturer AND era AND theme).
    - ~0.5 = a plausible but weaker match on a single signal.
    - Near 0.0 = speculative.
    Use the full range so the ranking is meaningful; reserve values above 0.9 for standout picks rather than clustering every item near the same number.
    
    ---
    [CRITICAL CONSTRAINTS]
    - Separated Output: "general" recommendations must NEVER have type 'EM'. "em" recommendations must ALWAYS have type 'EM'.
    - Strict Counts: Output exactly {NUM_RECOMMENDATIONS} items for "general" and exactly {NUM_RECOMMENDATIONS_EM} items for "em".
    - Exact Matching: The "id" and "game" string fields must perfectly match the database values provided in the candidate pool.
    - Deduplication: Never recommend the same base game title twice. If a game has a standard version and a "(Videos)" version in the pool, prioritize the standard version and discard the "(Videos)" version. Do not output both.
    - Candidate Isolation: Only recommend games that are explicitly listed in the "candidate_pool". 
    - Do not recommend games from the play history if they were last played within {REPLAY_WINDOW_DAYS} days (i.e., last_played < {REPLAY_WINDOW_DAYS}). Games in the history with last_played >= {REPLAY_WINDOW_DAYS} ARE eligible for recommendation since enough time has passed.
{not_owned_constraint}
    ---
    [OUTPUT FORMAT]
    Return ONLY a raw JSON object. Do not include markdown formatting, markdown code blocks (such as ```json) or any conversational text. 
    Each recommendation's "reason" must be a short phrase (roughly 3-12 words) citing the SPECIFIC signal from the user's history that drove the pick — e.g., a manufacturer, era, hardware platform, theme, or a high personal rating ("Williams 90s DMD favorite", "matches your space-theme affinity", "you rated similar Gottlieb EMs 5 stars"). Do NOT use generic justifications like "popular" or "highly rated by the community".

    JSON Schema:
    {{
      "general": [
        {{
          "id": <int/string GameId>,
          "game": "<string exact_name>",
          "confidence": <float between 0.0 and 1.0>,
          "reason": "<string short phrase citing the specific history signal>"
        }}
      ],
      "em": [
        {{
          "id": <int/string GameId>,
          "game": "<string exact_name>",
          "confidence": <float between 0.0 and 1.0>,
          "reason": "<string short phrase citing the specific history signal>"
        }}
      ]{not_owned_schema}
    }}

    """

    log("[+] Preparing AI request...")
    log(f"[+] Rating influence level: {RATING_INFLUENCE}")

    with open(PROMPT_PATH, 'w', encoding='utf-8') as f:
        f.write(prompt)
    log(f"[+] Saved full AI prompt to: {PROMPT_PATH}")

    try:
        raw_text, provider_used = _generate_with_provider(prompt)
        recommendations = json.loads(raw_text)

        with open(RECS_OUTPUT_PATH, 'w', encoding='utf-8') as f:
            json.dump(recommendations, f, indent=4)

        print("\n==================================================")
        print(f" SUCCESS: Generated recommendations via '{provider_used}'")
        print("==================================================")
        general_recs = recommendations.get("general", [])
        em_recs = recommendations.get("em", [])

        def _fmt(rec):
            name = rec.get("game", "?")
            conf = rec.get("confidence", "")
            conf_str = f"{conf:.2f}" if isinstance(conf, (int, float)) else str(conf)
            reason = rec.get("reason", "")
            line = f"{name} (conf {conf_str})"
            if reason:
                line += f" - {reason}"
            return line

        print(f"  --- General ({len(general_recs)}) ---")
        for i, rec in enumerate(general_recs, 1):
            print(f"  {i}. {_fmt(rec)}")
        print(f"  --- EM ({len(em_recs)}) ---")
        for i, rec in enumerate(em_recs, 1):
            print(f"  {i}. {_fmt(rec)}")
        if INCLUDE_NOT_OWNED:
            not_owned_recs = recommendations.get("not_owned", [])
            print(f"  --- Not Owned ({len(not_owned_recs)}) ---")
            for i, rec in enumerate(not_owned_recs, 1):
                print(f"  {i}. {_fmt(rec)}")
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
