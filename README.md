# Vpin Recommender

An AI-powered virtual pinball table recommendation engine for PinUp Popper cabinets. Analyzes your play history and recommends tables from your local catalog using an AI model — either **Azure AI Foundry** (default, fast) or **Google Gemini** (free, slower).

Note: This project is intended as a prototype, not as a fully baked solution. It supports two interchangeable AI backends with automatic fallback: Azure AI Foundry (recommended for speed/quality) and Google Gemini (free, but somewhat slow — best suited to be run as a background task).

## Features

- Supports two AI backends: **Azure AI Foundry** (gpt-5 by default) and **Google Gemini**, selectable via `AI_PROVIDER` with automatic fallback
- Analyzes play history separately for **General** (non-EM) and **EM** (electromechanical) tables
- Returns two distinct recommendation sets tailored to each category
- Weights recommendations toward recently updated tables and known high-quality creators (configurable - you can adjust the weights in the script)
- Factors in game ratings, recency, and other factors to help you discover new tables that match your play style and preferences
- Optionally updates a PinUp Popper playlist with results
- Optionally tags recommended games with `AI_Suggested` for dynamic playlist creation

## Warning

This is a prototype and requires manual setup and knowledge of Python and SQL. It is not an official product and is provided "as-is" without warranty. 
Use at your own risk, and always back up your `PUPDatabase.db` before making any changes. If you aren't comfortable with any of this, please ask for help in the community. 

## Quick start (Azure, single PC)

If you just want to try it on **one Windows PC** using Azure AI Foundry (the default backend), this is the short version. Every step is explained in more detail further down, and there's a [Troubleshooting](#troubleshooting) section at the end.

1. **Install the tools** (one time): [Python 3.10+](https://www.python.org/downloads/) and the [Azure CLI](https://learn.microsoft.com/cli/azure/install-azure-cli). In the Python installer, tick **"Add python.exe to PATH."**
2. **Get the code**, then open a terminal (Command Prompt) in the project folder.
3. **Create the Python environment:**
   ```cmd
   py -m venv .venv
   .venv\Scripts\activate
   pip install -r requirements.txt
   ```
4. **Sign in to Azure** (opens a browser once): `az login`
5. **Make sure you have a model deployed** in Azure AI Foundry and that `AZURE_OPENAI_ENDPOINT` and `AZURE_OPENAI_DEPLOYMENT` in `vpin_recommender_config.py` match it — see [Azure AI Foundry setup](#azure-ai-foundry-setup).
6. **Point the script at your cabinet:** edit `DB_PATH`, `TARGET_EMU_IDS`, and `RECS_PLAYLIST_ID` in `vpin_recommender_config.py` — see [Configuration](#configuration).
7. **Back up `PUPDatabase.db`**, then run:
   ```cmd
   python Vpin_Recommender.py
   ```

For a cabinet with **no keyboard/mouse**, see [Headless / unattended deployment](#headless--unattended-deployment).

## Prerequisites

- Python 3.10+
- A PinUp Popper installation with `PUPDatabase.db`
- **One AI backend:**
  - **Azure AI Foundry** (default): an Azure subscription with a deployed chat model and the [Azure CLI](https://learn.microsoft.com/cli/azure/install-azure-cli) (`az login`). No API key is stored — authentication is keyless via your Entra ID identity. See [Azure AI Foundry setup](#azure-ai-foundry-setup).
  - **Google Gemini** (alternative): a [Google Gemini API key](https://aistudio.google.com/apikey).
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

### 5. Choose your AI backend

The script supports two interchangeable AI backends, selected with the `AI_PROVIDER` environment variable (default: `azure`):

| `AI_PROVIDER` | Backend | Auth |
|---------------|---------|------|
| `azure` (default) | Azure AI Foundry (gpt-5) | Keyless, via Azure CLI / Entra ID |
| `gemini` | Google Gemini | `GEMINI_API_KEY` |

If the primary provider fails (auth, quota, network, or bad JSON), the script automatically falls back to the other provider. Disable this by setting `AI_FALLBACK = False` in `vpin_recommender_config.py`.

- For **Azure**, follow [Azure AI Foundry setup](#azure-ai-foundry-setup) below.
- For **Gemini**, follow [Configure your Gemini API key](#configure-your-gemini-api-key) below.

> **Most testers should keep the default (`azure`) and jump straight to [Azure AI Foundry setup](#azure-ai-foundry-setup).** The Gemini section immediately below is optional — skip it unless you specifically want to use Google Gemini.

### Configure your Gemini API key

> Only needed if you use `AI_PROVIDER=gemini` (or want Gemini as a fallback).

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

## Azure AI Foundry setup

> Only needed if you use `AI_PROVIDER=azure` (the default).

Azure AI Foundry gives faster, higher-quality recommendations than the free Gemini tier. Authentication is **keyless** — the script uses your Azure CLI / Entra ID identity via `DefaultAzureCredential`, so there is no API key to store or leak. (Many Azure tenants disable local API-key auth by policy, which is why keyless is the default.)

### 1. Sign in with the Azure CLI

Install the [Azure CLI](https://learn.microsoft.com/cli/azure/install-azure-cli), then:

```powershell
az login
az account set --subscription "<your-subscription-id-or-name>"
```

### 2. Deploy a model (one-time)

If you don't already have a Foundry (Azure AI Services) resource and a chat deployment, create them. Example using the CLI (adjust names/region/quota to taste):

```powershell
# Create a resource group and an Azure AI Services (Foundry) resource
az group create -n vpin-ai-rg -l centralus
az cognitiveservices account create -n my-foundry -g vpin-ai-rg -l centralus `
  --kind AIServices --sku S0 --custom-domain my-foundry --yes

# Deploy a chat model (gpt-5 is the project default; gpt-4.1 is a faster alternative)
# The deployment name here must match AZURE_OPENAI_DEPLOYMENT in vpin_recommender_config.py.
az cognitiveservices account deployment create -n my-foundry -g vpin-ai-rg `
  --deployment-name vpin-recommender-gpt5 `
  --model-name gpt-5 --model-version "2025-08-07" --model-format OpenAI `
  --sku-name GlobalStandard --sku-capacity 50

# Get the endpoint
az cognitiveservices account show -n my-foundry -g vpin-ai-rg --query "properties.endpoint" -o tsv
```

You can also create the resource and deployment interactively in the [Azure AI Foundry portal](https://ai.azure.com).

> **Which model should I deploy?** This project defaults to **`gpt-5`**, a reasoning model with excellent ranking/deduplication and broad knowledge of pinball tables and creators. It's slower (roughly 30–60s per run) but that's fine for a background job. For a faster, cheaper option, **`gpt-4.1`** is a strong alternative — set `AZURE_OPENAI_DEPLOYMENT` to your gpt-4.1 deployment and `AZURE_OPENAI_TEMPERATURE=0.4`. Reasoning models (gpt-5, o-series) only accept the default temperature, so leave `AZURE_OPENAI_TEMPERATURE=None` for them (the script also auto-retries without temperature if a model rejects it). You can compare any models side-by-side on your real prompt (`ai_prompt_full.txt`) in the Foundry **Compare** view. In practice, the biggest quality gains come from richer play-history data (see [CustomGameLog creation](#customgamelog-creation)), not just a bigger model.

Example: deploy gpt-5 with the CLI (adjust names/region/quota):

```powershell
az cognitiveservices account deployment create -n my-foundry -g my-rg `
  --deployment-name vpin-recommender --model-name gpt-5 --model-version "2025-08-07" `
  --model-format OpenAI --sku-name GlobalStandard --sku-capacity 50
```

### 3. Grant yourself access

Your identity needs the **Cognitive Services OpenAI User** role on the resource:

```powershell
$uid = az ad signed-in-user show --query id -o tsv
$scope = az cognitiveservices account show -n my-foundry -g vpin-ai-rg --query id -o tsv
az role assignment create --assignee $uid --role "Cognitive Services OpenAI User" --scope $scope
```

### 4. Point the script at your deployment

Set these in `vpin_recommender_config.py` (or override via environment variables):

| Variable | Env var | Description |
|----------|---------|-------------|
| `AZURE_OPENAI_ENDPOINT` | `AZURE_OPENAI_ENDPOINT` | e.g. `https://my-foundry.cognitiveservices.azure.com/` |
| `AZURE_OPENAI_DEPLOYMENT` | `AZURE_OPENAI_DEPLOYMENT` | The deployment name, e.g. `vpin-recommender` |
| `AZURE_OPENAI_API_VERSION` | `AZURE_OPENAI_API_VERSION` | API version, e.g. `2024-10-21` |

Then run normally — no key needed, as long as `az login` is valid.

### Headless / unattended deployment

On a cabinet PC with no interactive user, **do not rely on `az login`** — its refresh token expires after ~90 days of inactivity (and breaks on password changes or Conditional Access prompts) with no one at the keyboard to fix it. Instead, use a **service principal**, which authenticates non-interactively and is picked up automatically by `DefaultAzureCredential` via three environment variables.

> The script's credential chain is `AzureCliCredential` → `DefaultAzureCredential`. The latter reads the `AZURE_*` variables below, so **no code changes are needed** — just set them.

**1. Create a service principal and grant it access** (run once, from an admin machine):

```powershell
$scope = az cognitiveservices account show -n my-foundry -g my-rg --query id -o tsv
az ad sp create-for-rbac --name "vpin-recommender-sp" `
  --role "Cognitive Services OpenAI User" --scopes $scope
```

This prints `appId`, `password`, and `tenant`. **Copy the password now — it is shown only once.**

**2. Put the credentials in `.env` on the cabinet** (gitignored, never committed):

```
AZURE_TENANT_ID=<tenant>
AZURE_CLIENT_ID=<appId>
AZURE_CLIENT_SECRET=<password>
```

`run.bat` loads every `KEY=VALUE` line from `.env` into the environment before launching the script, so the service principal is used automatically.

**3. Deployment checklist for the cabinet:**

| Step | Detail |
|------|--------|
| Copy files | Copy the repo **without** `.venv` (virtual environments are not portable) |
| Python | Install Python 3.10+ |
| venv + deps | `py -m venv .venv` then `pip install -r requirements.txt` |
| Auth | Service principal via `.env` (above) — preferred over `az login` for headless |
| Config | Set real `DB_PATH`, `TARGET_EMU_IDS`, `RECS_PLAYLIST_ID`; keep `AI_PROVIDER=azure` |
| Network | Allow outbound HTTPS to `*.cognitiveservices.azure.com`; keep the system clock synced (token validation fails on clock skew) |
| Schedule | Add `run.bat` to Task Scheduler or the Startup folder |

> **Secret rotation:** the client secret has an expiry (2 years in the example). Rotate before it lapses with `az ad app credential reset --id <appId>` and update `.env`.

## Security & authentication notes

### How authentication works

A **service principal** is a non-human identity in Microsoft Entra ID — effectively a login for this script rather than for a person. It has an `appId` (like a username), a `client secret` (like a password), and a set of role assignments.

At runtime the flow is:

1. `run.bat` loads `AZURE_TENANT_ID`, `AZURE_CLIENT_ID`, and `AZURE_CLIENT_SECRET` from `.env` into environment variables.
2. The script's `DefaultAzureCredential` detects those variables and exchanges them with Entra ID for a **short-lived bearer token** (valid ~1 hour).
3. The token is sent to the Azure AI Foundry endpoint; Azure checks the service principal's **role assignment** and allows the call.

No interactive login, no browser, and no long-lived API key are involved — which is what makes it suitable for an unattended cabinet. On your own dev machine, the script instead uses your `az login` session (via the same credential chain), so no `.env` secret is needed there.

### Why a service principal here

| Option | Best for | Why / why not |
|--------|----------|---------------|
| **Managed identity** | Azure-hosted compute (VM, App Service, Arc) | The gold standard — *no secret at all* — but requires Azure-managed hardware. A home cabinet doesn't qualify unless Arc-enrolled. |
| **Service principal** *(used here)* | Off-Azure unattended machines | Correct, conventional choice for a physical cabinet. One secret to manage. |
| **User `az login`** | Your interactive dev machine | Interactive and the token expires after ~90 days idle — unsuitable for headless. |
| **API keys** | — | Blocked by tenant policy here, and a long-lived shared secret is the weakest option. |

### Security considerations

- **The client secret is a password.** `.env` is gitignored — never commit it, and never paste it into logs, screenshots, or chat.
- **Least privilege (already applied).** The service principal is scoped to a *single* Foundry resource with a *data-plane* role (**Cognitive Services OpenAI User**). It can call the model but cannot manage Azure resources or reach other services. If leaked, the blast radius is "someone can use that one deployment's quota," not your whole subscription.
- **One service principal per tester.** If everyone shares one secret, a single leak forces a rotation for all. Having each tester run `az ad sp create-for-rbac` for themselves means you can revoke one without affecting others.
- **Rotation & revocation.** Rotate the secret before expiry (and immediately if exposed) with `az ad app credential reset --id <appId>`. You can disable or delete the service principal in Entra ID to cut off access instantly; its sign-ins are logged per `appId`.
- **Secret at rest.** Plaintext `.env` is acceptable for a home cabinet. To harden, use Windows Credential Manager/DPAPI or a certificate credential instead of a shared secret.

### Can model-side instructions protect the credential? (No — and what does)

A natural instinct is to "restrict the model on the Foundry side to only answer this query." That improves output quality but is **not** a security control against a stolen credential: the system prompt is supplied *by the caller on every request*, so anyone holding the secret just sends their own prompt and ignores yours.

What actually limits damage from a leaked credential — all enforced server-side, for every caller:

- **Quota caps** on the deployment (TPM/RPM) bound the cost and throughput an attacker could consume.
- **Content filter (RAI) policy** (a default policy is already attached) runs on Azure's side for every call; you can attach a stricter custom policy.
- **Network restrictions** — lock the resource to specific IPs or a private endpoint. For a cabinet with a stable IP, an allow-list makes a stolen key unusable from anywhere else. This is the strongest single control.
- **Scope, rotation, and revocation**, as above.

Model instructions *do* matter for a **different** threat — **prompt injection through your own data.** Table names and metadata are embedded in the prompt, so a maliciously named table could try to steer the output. The firm JSON-only system prompt plus the script's output validation (it only acts on game IDs that exist in your candidate pool, never on free text from the model) defend against that.

### Future option: enforce "only pinball queries" server-side

This script calls the **raw model deployment** directly, which means the "you are a pinball recommender" instruction lives only in this client. Anyone with a valid credential can bypass the script and ask the deployment arbitrary questions. Content filters do **not** fix this — they block harmful *categories*, not off-topic questions.

To truly constrain *what can be asked* regardless of caller, don't expose the raw deployment. Front it with a layer that owns the system prompt and input shape, and grant the credential access only to that layer:

- A **Foundry Agent** or **Prompt Flow** endpoint with a fixed, server-side system prompt, or
- A small **Azure Function / API** that injects the prompt, accepts only the play-data payload, and returns only the structured JSON.

Then lock the underlying model deployment to be callable only by that layer's identity. This is architectural enforcement, not a deployment toggle. It's unnecessary for a single-user cabinet test (exposure is already bounded by quota, least-privilege scope, and revocation) but is the right move if this graduates to wider or production use.

## Configuration

Edit the settings in `vpin_recommender_config.py` to match your setup:

| Variable | Description |
|----------|-------------|
| `AI_PROVIDER` | Primary AI backend: `azure` (default) or `gemini`. Also settable via env var. |
| `AI_FALLBACK` | `True` to automatically try the other provider if the primary fails |
| `AZURE_OPENAI_ENDPOINT` | Azure AI Foundry endpoint URL (used when provider is `azure`) |
| `AZURE_OPENAI_DEPLOYMENT` | Azure model deployment name |
| `AZURE_OPENAI_API_VERSION` | Azure OpenAI API version |
| `AZURE_OPENAI_TEMPERATURE` | Sampling temperature. Use `None` for reasoning models (gpt-5, o-series); `0.4` works for gpt-4.1. The script auto-retries without it if the model objects. |
| `GEMINI_MODEL` | Gemini model name (used when provider is `gemini`) |
| `DB_PATH` | Path to your `PUPDatabase.db` |
| `TARGET_EMU_IDS` | Comma-separated emulator IDs to include (see below) |
| `UPDATE_PLAYLIST` | `True` to update a PinUp Popper playlist with recommendations |
| `RECS_PLAYLIST_ID` | Playlist ID to populate (only used when `UPDATE_PLAYLIST` is `True`) |
| `ADD_SUGGESTED_TAGS` | `True` to tag recommended games with `AI_Suggested` |
| `NUM_RECOMMENDATIONS` | Number of general (non-EM) recommendations |
| `NUM_RECOMMENDATIONS_EM` | Number of EM recommendations |
| `MIN_GAME_RATING` | Minimum rating filter (0 = no filter) |
| `INCLUDE_NON_RATED` | Set to `1` to include unrated tables even when filtering by rating |
| `MAX_AGE_MINUTES` | Minutes before a cached result expires and a new AI request is made |
| `HISTORY_DAYS` | Days of play history to analyze |
| `REPLAY_WINDOW_DAYS` | Games last played within this many days are excluded from recommendations |
| `RATING_INFLUENCE` | How strongly your high star ratings (4-5) drive picks: `none`, `light`, `moderate` (default), or `strong` |
| `NEGATIVE_RATING_INFLUENCE` | How strongly your low star ratings (1-2) push a table out: `none`, `light`, `moderate`, or `strong` (default). Penalizes only that specific table, never its theme/era/manufacturer |
| `INCLUDE_NOT_OWNED` | `True` to include external table suggestions from the VPIN Spreadsheet |
| `NUM_NOT_OWNED` | Number of external table suggestions (only used when `INCLUDE_NOT_OWNED` is `True`) |

### Key Settings

**`MAX_AGE_MINUTES`** — Controls how often the AI is actually called. If a cached `ai_recommendations.json` exists and is newer than this threshold, the script skips the AI request and reuses the previous results. Set this to `1440` (24 hours) to limit calls to once per day, which is a reasonable default if you run the script on startup or via Task Scheduler. Lower values refresh results more frequently at the cost of additional API usage.

**`TARGET_EMU_IDS`** — A comma-separated string of emulator IDs from PinUp Popper (e.g., `"10"` or `"10,11"`). Only tables belonging to these emulators will be included in both the play history analysis and the recommendation candidate pool. You can find emulator IDs in the PinUp Popper Setup Utility under the emulator configuration. Use this to focus recommendations on specific emulators (e.g., VPX only) or broaden them across multiple.

**`HISTORY_DAYS`** — The number of days of play history the AI uses to understand your preferences. A longer window (e.g., `365`) gives a broader picture of your overall taste, while a shorter window (e.g., `90`) makes the analysis more responsive to recent play patterns. Tune this based on how actively you play and how much your preferences shift over time.

**`REPLAY_WINDOW_DAYS`** — Any game last played within this many days is excluded from recommendations, preventing the AI from suggesting tables you've recently played. For example, setting this to `90` keeps suggestions fresh by filtering out anything touched in the past three months. If you set this equal to `HISTORY_DAYS`, every game in the play history sample will be excluded, ensuring recommendations only surface tables you haven't played in a long time or haven't tried at all.

### Playlist setup

note the ID of the playlist you want to use. Set `RECS_PLAYLIST_ID` in `vpin_recommender_config.py` to that value.

Alternatively, if `ADD_SUGGESTED_TAGS` is `True`, recommended games are tagged with `AI_Suggested` and you can build a dynamic playlist using a SQL query of your choice, for example:

```sql
SELECT * FROM Games WHERE TAGS LIKE '%AI_Suggested%'
```

### Wheel art

The `images/` folder includes ready-made **wheel images** you can use for your AI-recommended playlists in PinUp Popper — one for the **General** recommendations and one for the **EM** recommendations:

| General | EM |
|:---:|:---:|
| ![AI Recommended wheel](images/ai%20recommended%20wheel.png) | ![AI Recommended EM wheel](images/ai%20recommended%20em%20wheel.png) |

Two styles are provided for each category:

- `ai recommended wheel.png` / `ai recommended em wheel.png` — a single, ready-to-use wheel (1600×1600 PNG). **Use these on your cabinet.**
- `ai recommended wheels.webp` / `ai recommended em wheels.webp` — a medley of **4 design variations** in one image, so you can pick the look you prefer and crop/export your favorite.

To apply one to a playlist, open the **PinUp Popper Setup Utility**, select your playlist (e.g. the one set by `RECS_PLAYLIST_ID`, or your dynamic `AI_Suggested` playlist), and set its wheel/media image to the corresponding PNG. The General art suits your non-EM playlist and the EM art suits your electromechanical playlist.

### Emulator IDs

Set `TARGET_EMU_IDS` to the emulator IDs you want the recommender to analyze. You can find these in the PinUp Popper Setup Utility under the emulator configuration. Note that some emulators, like **PinballFX**, may not have standard filenames and would require additional work to integrate properly.

## Usage

### Quick launch (recommended)

Double-click `run.bat` or add it to Windows Task Scheduler / Startup folder for automatic execution on boot.

```cmd
run.bat
```

This batch file automatically loads your credentials from `.env` (service principal and/or `GEMINI_API_KEY`), activates the venv, and runs the script.

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
2. Send the data to the configured AI backend (Azure AI Foundry or Google Gemini) for AI-powered recommendations
3. Save results to `ai_recommendations.json`
4. Update the specified PinUp Popper playlist (if `UPDATE_PLAYLIST` is `True`)
5. Tag recommended games with `AI_Suggested` (if `ADD_SUGGESTED_TAGS` is `True`)

## Troubleshooting

Common issues testers hit, and how to fix them:

| Symptom | Likely cause & fix |
|---------|--------------------|
| `'python' is not recognized` / `'py' is not recognized` | Python isn't on your PATH. Reinstall Python and tick **"Add python.exe to PATH,"** then open a new terminal. |
| `ModuleNotFoundError: No module named 'openai'` (or `azure`, `google`) | The virtual environment isn't active or dependencies aren't installed. Run `.venv\Scripts\activate` then `pip install -r requirements.txt`. |
| `DefaultAzureCredential failed to retrieve a token` | You're not signed in to Azure on this machine. Run `az login`. On a headless cabinet, set up the service principal `.env` — see [Headless / unattended deployment](#headless--unattended-deployment). |
| `... (403) ... PermissionDenied` or `Access denied` | Your identity (or service principal) lacks the **Cognitive Services OpenAI User** role on the Foundry resource. See [Azure AI Foundry setup](#azure-ai-foundry-setup), step 3. |
don't match your actual Foundry deployment. Double-check both in `vpin_recommender_config.py`. |
| `GEMINI_API_KEY environment variable is not set` | Only relevant if you chose the Gemini backend (or fallback tried it). Either set the key or set `AI_PROVIDER=azure`. |
| `(401) ... invalid_client` or `AADSTS7000215` | The service principal secret in `.env` is wrong or expired. Regenerate it with `az ad app credential reset --id <appId>` and update `.env`. |
| `database is locked` | PinUp Popper (or another tool) has `PUPDatabase.db` open. Close it and re-run. Always back up the database first. |
| "Recommendations file ... Skipping." | A fresh `ai_recommendations.json` already exists. This is normal caching — lower `MAX_AGE_MINUTES` or delete that file to force a new run. |
| No recommendations / empty results | `TARGET_EMU_IDS` probably doesn't match your emulators, or there isn't enough play history yet. See [Emulator IDs](#emulator-ids) and [CustomGameLog creation](#customgamelog-creation). |

## Files

| File | Purpose |
|------|---------|
| `Vpin_Recommender.py` | Main script |
| `vpin_recommender_config.py` | User-tunable settings (paths, provider, counts, rating influence, etc.) |
| `requirements.txt` | Python dependencies |
| `ai_prompt_payload_compact.txt` | Generated payload sent to AI (auto-created) |
| `ai_recommendations.json` | AI output (auto-created) |
| `images/` | Wheel art for the AI-recommended General and EM playlists |
| `.env` | Your credentials — service principal and/or `GEMINI_API_KEY` (create manually, do not commit) |

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

### Using GamesStats

If you prefer to just use the existing GamesStats table and not create the CustomGameLog table, you can! In the Vpin_Recommender.py script, modify the history query (for non-EMs) to something like:

```sql
SELECT 
	s.NumberPlays as TotalPlays,
	s.TimePlayedSecs as TotalTimePlayedSecs,
	CAST(JULIANDAY('now') - JULIANDAY(s.LastPlayed) AS INTEGER) AS LastPlayedDays,
	g.GameId,
	GameDisplay, 
	GameYear, 
	Manufact,
	GameType,
	GameRating
FROM Games g
JOIN GamesStats s on g.GameID = s.GameID
WHERE g.EMUID in ({TARGET_EMU_IDS}) 
and g.visible=1
and s.LastPlayed > DateTime('Now', 'LocalTime', '-' || ? || ' Day')
and g.GameType IS NOT 'EM'
ORDER BY TotalPlays DESC
```

...and repeat this for EMs, changing the GameType filter. The ability to customize is limited - there's no ability to horizon the data or get granular trends, which may be useful as the AI prompt matures. Ultimately, the goal will be to build a more robust prompt using the data; for that we'll need better analytics.
