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
