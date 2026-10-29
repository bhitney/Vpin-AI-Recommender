# ==============================================================================
# VPIN AI RECOMMENDER - CONFIGURATION
# ==============================================================================
# All user-tunable settings live here so you can update the main script
# (Vpin_Recommender.py) without clobbering your local settings. On a cabinet,
# edit this file only; overwriting Vpin_Recommender.py is then always safe.
# ==============================================================================
import os

# ==============================================================================
# CONFIGURABLE PARAMETERS & PATHS
# ==============================================================================
# Resolve paths relative to this config file (same directory as the main script).
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

# Log each AI recommendation's confidence and reason to CustomAiLog for history
# and additional analysis. This is optional and only writes when the table exists.
LOG_AI_RECOMMENDATIONS = False

# Number of tables to recommend
NUM_RECOMMENDATIONS = 15
NUM_RECOMMENDATIONS_EM = 15

# Minimum game rating filter for candidate pool (0 = no filter)
MIN_GAME_RATING = 0
INCLUDE_NON_RATED = 1

# Number of days of play history to analyze
HISTORY_DAYS = 365

# Play-history filters. These keep noise (tables launched briefly to test or record media)
# out of the history sent to the AI, without editing the SQL in Vpin_Recommender.py.
# Minimum number of plays (sessions) within HISTORY_DAYS for a table to count as history.
HISTORY_MIN_PLAYS = 1
# Minimum TOTAL seconds played within HISTORY_DAYS for a table to count as history.
HISTORY_MIN_SECS = 60
# Maximum number of history tables sent per track (general and EM), most recently played first.
HISTORY_MAX_ROWS = 300

# How strongly average session length (total seconds / plays) should influence recommendations.
# Long average sessions suggest real enjoyment, but playtime can be deceptive (idling, finishing
# a single mode), so an explicit star rating ALWAYS outweighs playtime. It only affects how much
# a history table counts as a taste signal; it never penalizes a candidate.
# One of:
#   "none"     - Ignore session length entirely.
#   "light"    - Long average sessions are a minor tie-breaker.
#   "moderate" - Long average sessions are one meaningful signal; very short ones are discounted
#                (recommended default).
#   "strong"   - Long average sessions heavily weight that table's patterns; short ones are
#                largely discounted.
PLAYTIME_INFLUENCE = "moderate"
# Games played within this many days are excluded from recommendations.
# Games in the history but last played MORE than this many days ago can still be recommended.
REPLAY_WINDOW_DAYS = 220

# How strongly the user's POSITIVE/neutral star "rating" (3-5) should influence recommendations.
# This lever governs how much your favorites (4-5) pull similar tables in. A high rating is
# treated as a BROAD signal: it can reinforce that table's manufacturer/era/theme patterns.
# Keep this lighter if you want variety and don't want 5-star tables (and their patterns) to
# dominate every run. Negative ratings (1-2) are handled separately by NEGATIVE_RATING_INFLUENCE.
# One of:
#   "none"     - Ignore positive ratings entirely; rank purely on play behavior,
#                manufacturer/era/theme patterns, freshness, and creator. Use when you want
#                discovery driven only by what you actually play, not by past ratings.
#   "light"    - Positive ratings are only a minor tie-breaker between otherwise-close candidates.
#   "moderate" - Positive ratings are one meaningful signal balanced against play
#                frequency/engagement and pattern matching (recommended default).
#   "strong"   - Positive ratings are a primary signal of taste; heavily weight 5-star patterns
#                and strongly prefer 4-5 rated candidates.
RATING_INFLUENCE = "moderate"

# How strongly the user's NEGATIVE star "rating" (1-2) should influence recommendations.
# This is a SEPARATE lever from RATING_INFLUENCE so you can, for example, let favorites nudge
# results lightly while letting dislikes push hard. A 1-2 rating is a deliberate "I don't like
# this" signal, so you may want it to weigh more strongly than your positive ratings.
# IMPORTANT: A negative rating penalizes ONLY that specific table — it never penalizes the
# table's manufacturer, era, theme, or platform (a 1-star might just be a poor build of an
# otherwise great theme). Max is "strong" (not a hard exclude) because recency/other signals
# may still make an earlier/alternate version worth surfacing occasionally.
# One of:
#   "none"     - Ignore negative ratings entirely; a 1-2 is treated the same as unrated.
#   "light"    - A 1-2 is a minor tie-breaker against an otherwise-close candidate.
#   "moderate" - A 1-2 is a meaningful penalty on that specific table, but strong play-behavior
#                or pattern signals can still override it.
#   "strong"   - A 1-2 strongly penalizes that specific table so it is only recommended if other
#                signals are overwhelmingly strong (recommended if you want dislikes respected).
NEGATIVE_RATING_INFLUENCE = "strong"

# How strongly an upcoming holiday should influence recommendations. The script computes the
# days until the next holiday in HOLIDAYS (below) and only mentions it to the AI when it falls
# within HOLIDAY_WINDOW_DAYS. The AI matches the holiday's keywords against table names and its
# own knowledge of the table's theme (theme/tags columns are NOT sent, to limit token usage).
# One of:
#   "none"     - Ignore holidays entirely (nothing is added to the prompt).
#   "slight"   - Holiday-themed tables are a minor tie-breaker.
#   "moderate" - Holiday-themed tables get a meaningful boost.
#   "strong"   - Strongly prioritize holiday-themed tables; they should fill a large share of the list.
HOLIDAY_INFLUENCE = "moderate"
# A holiday is only considered when it is within this many days ahead (or HOLIDAY_GRACE_DAYS behind).
# These are the defaults; any holiday below can override them with its own "days_before" / "days_after".
HOLIDAY_WINDOW_DAYS = 7
HOLIDAY_GRACE_DAYS = 5

# Holidays to consider. Add, remove, or edit entries to suit your locale.
#   name     - Shown to the AI.
#   date     - One of:
#                "MM-DD"          fixed yearly date, e.g. "10-31"
#                "YYYY-MM-DD"     a single specific date
#                "Nth-day-mon"    Nth weekday of a month, e.g. "4th-thu-nov"; use "last" for the last one
#                "easter"         Easter Sunday (Western)
#   keywords - Theme words the AI should look for in table names / known themes.
#   days_before / days_after - Optional. Override HOLIDAY_WINDOW_DAYS / HOLIDAY_GRACE_DAYS for this holiday.
HOLIDAYS = [
    {"name": "New Year's Day",  "date": "01-01", "keywords": ["new year", "party", "celebration"]},
    {"name": "Valentine's Day", "date": "02-14", "keywords": ["love", "romance", "valentine", "heart"]},
    {"name": "St. Patrick's Day", "date": "03-17", "keywords": ["irish", "ireland", "leprechaun", "lucky", "shamrock"]},
    {"name": "Easter",          "date": "easter", "keywords": ["easter", "bunny", "spring"]},
    {"name": "Star Wars Day",   "date": "05-04", "days_before": 7, "days_after": 1, "keywords": ["star wars", "jedi", "sith", "empire", "space", "galaxy", "sci-fi"]},
    {"name": "Independence Day", "date": "07-04", "keywords": ["patriotic", "america", "usa", "fireworks", "liberty"]},
    {"name": "Talk Like a Pirate Day", "date": "09-19", "days_before": 7, "days_after": 1, "keywords": ["pirate", "pirates", "caribbean", "treasure", "buccaneer", "sea", "ship"]},
    {"name": "Halloween",       "date": "10-31", "days_before": 14, "days_after": 2, "keywords": ["horror", "monster", "zombie", "vampire", "ghost", "haunted", "witch", "halloween", "creature", "addams", "ghostbusters"]},
    {"name": "Thanksgiving",    "date": "4th-thu-nov", "keywords": ["thanksgiving", "harvest", "turkey", "football"]},
    {"name": "Christmas",       "date": "12-25", "days_before": 28, "days_after": 7, "keywords": ["christmas", "xmas", "santa", "snow", "winter", "holiday", "elf", "reindeer"]},
]

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
#
# NOTE: The default endpoint below points at the author's personal Foundry
# resource. Replace it with YOUR OWN Foundry endpoint (roll your own deployment)
# — set AZURE_OPENAI_ENDPOINT or edit the fallback string here. The author's
# endpoint is harmless to leave checked in (it requires an authorized Entra ID
# login to use), but it won't work for you until you point at your own resource.
AZURE_OPENAI_ENDPOINT = os.environ.get(
    "AZURE_OPENAI_ENDPOINT", "https://opsiq-foundry.cognitiveservices.azure.com/")
# AZURE_OPENAI_DEPLOYMENT = os.environ.get("AZURE_OPENAI_DEPLOYMENT", "vpin-recommender-gpt5")
AZURE_OPENAI_DEPLOYMENT = os.environ.get("AZURE_OPENAI_DEPLOYMENT", "vpin-recommender-gpt-6-sol")
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
