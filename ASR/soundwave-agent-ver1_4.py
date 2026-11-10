#!/usr/bin/env python3
"""
Soundwave Voice Agent v1.4 - Voice chat with LLM and tools
Usage: python3 soundwave-agent-ver1_4.py [--device N]

Changes from v1.3:
  - FIX A: ASR correction stopword list + raised fuzzy cutoff (0.65→0.75)
  - FIX B: Rule-based email query builder (replaces LLM for Gmail queries)
  - FIX C: Empty-result guard — skips LLM summarisation when tools return nothing
  - FIX D: Personality scoped to greetings/goodbyes only; factual during tasks

Tools: Gmail, Google Calendar, Tavily Web Search, Qwen3-Coder
"""
import argparse
import json
import re
import time
from datetime import datetime
from difflib import get_close_matches
import pytz
import requests
import riva.client
import riva.client.audio_io

# ============================================================================
# Configuration - ClusterIPs for running from soundwave host
# ============================================================================
ASR_SERVER = "10.108.71.179:20051"
TTS_SERVER = "10.97.145.244:20052"
#LLM_SERVER = "http://10.96.166.68:11434"
LLM_SERVER = "http://10.101.166.67:8000"
CODER_LLM_SERVER = "http://10.104.45.35:22001"  # Qwen3-Coder on megatron
CODER_MODEL_NAME = "NVFP4/Qwen3-Coder-30B-A3B-Instruct-FP4"
GMAIL_URL = "http://10.101.226.72:8100/gmail"
GCAL_URL = "http://10.99.45.112:8200/google-calendar"
TAVILY_URL = "http://10.99.178.24:8400/tavily"

# MODEL_NAME = "qwen3:30b-a3b"
# MODEL_NAME = "mistral:7b-instruct-v0.3-q4_K_M"
MODEL_NAME = "openai/gpt-oss-120b"
TIMEZONE = "Europe/Amsterdam"

# ============================================================================
# FIX #3 — ASR Fuzzy Entity Correction
# ============================================================================
# Known entities the user frequently mentions. Add your own teams, names,
# cities, etc.  Keys are the canonical spelling; values are common ASR
# misspellings so we can also do an exact lookup before fuzzy matching.
KNOWN_ENTITIES = {
    # Brazilian football teams
    "Palmeiras":    ["palmyrez", "palmyras", "palmyra", "paomez", "palomeras",
                     "almeidas", "palmeras", "pomeras", "palm aires", "palmaris",
                     "palmeiraz", "palmerais"],
    "São Paulo":    ["sao paulo", "são paulo", "san paulo", "sao polo"],
    "Flamengo":     ["flamingo", "flamenco", "flamenko"],
    "Corinthians":  ["corinthians", "corintians", "korintians"],
    "Grêmio":       ["gremio", "gremia", "gramio"],
    "Cruzeiro":     ["cruzero", "cruseiro", "crusero"],
    "Botafogo":     ["botafogo", "botafago", "bota fogo"],
    "Fluminense":   ["fluminense", "fluminensi", "fluminenci"],
    "Vasco":        ["vasco", "vasko"],
    "Internacional":["internacional", "internacionale"],
    "Athletico":    ["atletico", "athletico", "atletiko"],
    "Santos":       ["santos", "santoz"],
    # Serie A / Brazilian championship
    "Brasileirão":  ["brasileirao", "brazilian championship", "serie a brazil",
                     "seri ah", "serie ah", "seria", "series a"],
    # Add more domains as needed — people, cities, tech terms, etc.
}

# Build a reverse lookup: misspelling -> canonical
_ENTITY_REVERSE = {}
_ENTITY_CANONICAL_LOWER = {}          # canonical_lower -> canonical
for _canon, _aliases in KNOWN_ENTITIES.items():
    _canon_low = _canon.lower()
    _ENTITY_CANONICAL_LOWER[_canon_low] = _canon
    for _alias in _aliases:
        _ENTITY_REVERSE[_alias.lower()] = _canon
    # Also map the canonical form itself
    _ENTITY_REVERSE[_canon_low] = _canon

# Collect all known surface forms for fuzzy matching
_ALL_SURFACE_FORMS = list(_ENTITY_REVERSE.keys())

# Common English words that should NEVER be fuzzy-corrected to entities.
# This prevents "please" → "Palmeiras", "the" → "Grêmio", etc.
_STOPWORDS = {
    "a", "an", "the", "is", "are", "was", "were", "be", "been", "being",
    "have", "has", "had", "do", "does", "did", "will", "would", "could",
    "should", "may", "might", "shall", "can", "need", "must",
    "i", "me", "my", "you", "your", "he", "she", "it", "we", "they",
    "him", "her", "us", "them", "this", "that", "these", "those",
    "and", "or", "but", "if", "so", "as", "at", "by", "for", "in",
    "of", "on", "to", "up", "out", "off", "from", "with", "about",
    "not", "no", "yes", "yeah", "ok", "okay", "please", "thanks",
    "thank", "hey", "hi", "hello", "bye", "man", "dude", "bro",
    "what", "who", "how", "when", "where", "which", "why",
    "just", "now", "then", "here", "there", "very", "really",
    "also", "too", "much", "more", "some", "any", "all", "each",
    "check", "get", "got", "give", "tell", "show", "find", "look",
    "know", "think", "want", "like", "make", "go", "come", "see",
    "take", "put", "let", "say", "said", "try", "keep", "start",
    "inbox", "email", "emails", "mail", "search", "internet", "web",
    "afternoon", "morning", "evening", "today", "yesterday", "last",
    "saturday", "sunday", "monday", "tuesday", "wednesday", "thursday",
    "friday", "game", "score", "result", "results", "match",
}


def correct_asr_transcript(text: str) -> str:
    """
    Fix common ASR misspellings using exact + fuzzy matching against
    KNOWN_ENTITIES.  Returns the corrected transcript.

    Guards:
      - Single words in _STOPWORDS are never fuzzy-matched.
      - Fuzzy cutoff raised to 0.75 (was 0.65) to avoid false positives.
      - Single-word fuzzy requires >= 5 chars.
    """
    words = text.split()
    corrected_words = []
    i = 0
    while i < len(words):
        matched = False
        # Try 3-word, 2-word, then 1-word windows (longest match first)
        for window in (3, 2, 1):
            if i + window > len(words):
                continue
            chunk = " ".join(words[i:i + window]).lower()
            # Strip trailing punctuation for matching (keep original for output)
            chunk_clean = chunk.rstrip(".,!?;:")

            # Skip stopwords for single-word fuzzy (exact match still allowed)
            is_single_stopword = (window == 1 and chunk_clean in _STOPWORDS)

            # Exact hit in reverse map (always allowed, even stopwords)
            if chunk_clean in _ENTITY_REVERSE:
                # But NOT if it's a common English stopword with an exact
                # collision — only match if it's clearly an entity alias
                if not is_single_stopword:
                    corrected_words.append(_ENTITY_REVERSE[chunk_clean])
                    i += window
                    matched = True
                    break

            # Fuzzy match — guarded
            if not is_single_stopword and len(chunk_clean) >= 5:
                candidates = get_close_matches(chunk_clean, _ALL_SURFACE_FORMS,
                                               n=1, cutoff=0.75)
                if candidates:
                    corrected_words.append(_ENTITY_REVERSE[candidates[0]])
                    i += window
                    matched = True
                    break
        if not matched:
            corrected_words.append(words[i])
            i += 1
    result = " ".join(corrected_words)
    if result != text:
        print(f"   🔤 ASR correction: \"{text}\" → \"{result}\"")
    return result


# ============================================================================
# Tool Definitions (unchanged — still passed to Ollama for the fallback path)
# ============================================================================
TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "search_emails",
            "description": "Search Gmail for emails matching a query. Use Gmail search syntax like 'is:inbox', 'from:someone', 'after:2026-03-20'",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Gmail search query"},
                    "maxResults": {"type": "integer", "description": "Max emails to return (default 5)"}
                },
                "required": ["query"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "read_email",
            "description": "Read the full content of a specific email by its ID",
            "parameters": {
                "type": "object",
                "properties": {
                    "id": {"type": "string", "description": "Email ID from search results"}
                },
                "required": ["id"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "list_events",
            "description": "List upcoming calendar events",
            "parameters": {
                "type": "object",
                "properties": {
                    "maxResults": {"type": "integer", "description": "Max events to return (default 10)"}
                }
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "web_search",
            "description": "Search the web for current information using Tavily",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Search query"}
                },
                "required": ["query"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_time",
            "description": "Get the current date and time",
            "parameters": {
                "type": "object",
                "properties": {}
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "ask_coder",
            "description": "REQUIRED for ALL coding questions. Ask the expert programmer (Qwen3-Coder 30B) for code generation, algorithms, debugging, scripts, technical explanations, or any programming task. You MUST use this tool for any code-related request.",
            "parameters": {
                "type": "object",
                "properties": {
                    "question": {"type": "string", "description": "The coding or technical question to ask the expert"}
                },
                "required": ["question"]
            }
        }
    }
]


# ============================================================================
# Keyword Detectors
# ============================================================================
def is_coding_request(text: str) -> bool:
    """Detect if user is asking for code/programming help."""
    text_lower = text.lower()
    coding_keywords = [
        "code", "script", "program", "algorithm", "function", "class",
        "python", "javascript", "java", "bash", "sql", "html", "css",
        "go script", "golang", "sorting", "binary search", "recursion",
        "terraform", "ansible", "bash shell", "C++ programming",
        "debug", "fix this", "write a", "create a", "implement", "generate",
        "coder", "coding", "developer", "programming"
    ]
    return any(kw in text_lower for kw in coding_keywords)


def is_email_request(text: str) -> bool:
    """Detect if user is asking about emails."""
    text_lower = text.lower()
    email_keywords = [
        "email", "emails", "inbox", "gmail", "mail", "mails",
        "message", "messages", "unread", "received", "sent",
        "from linkedin", "from amazon", "from google"
    ]
    # Exclude if it looks like a web search phrasing
    if any(w in text_lower for w in ["search the web", "search internet",
                                      "search online", "look up online",
                                      "web search"]):
        return False
    return any(kw in text_lower for kw in email_keywords)


def is_calendar_request(text: str) -> bool:
    """Detect if user is asking about calendar/schedule."""
    text_lower = text.lower()
    calendar_keywords = [
        "calendar", "schedule", "meeting", "meetings", "appointment",
        "appointments", "event", "events", "agenda", "busy", "free",
        "tomorrow", "today's schedule", "this week", "next week"
    ]
    if "news" in text_lower or "search" in text_lower:
        return False
    return any(kw in text_lower for kw in calendar_keywords)


# FIX #1 — New web search keyword detector
def is_web_search_request(text: str) -> bool:
    """Detect if user wants to search the web / look something up."""
    text_lower = text.lower()
    search_keywords = [
        "search the web", "search the internet", "search internet",
        "search online", "web search", "look up", "look it up",
        "google", "find out", "check online", "check the internet",
        "check internet", "search for", "what's the score",
        "what is the score", "who won", "what was the result",
        "result of", "results of", "score of", "news about",
        "latest news", "current", "recent news",
        "did they win", "how did they do", "match result",
        "game result", "search tavily", "tavily",
        "championship", "standings", "league table",
    ]
    return any(kw in text_lower for kw in search_keywords)


# ============================================================================
# Direct Tool Callers (bypass LLM for tool selection)
# ============================================================================
def ask_coder_directly(question: str) -> str:
    """Directly call Qwen3-Coder without going through Mistral."""
    print(f"   🧑‍💻 Pinging Qwen3-Coder: {question[:50]}...")
    try:
        resp = requests.post(
            f"{CODER_LLM_SERVER}/v1/chat/completions",
            json={
                "model": CODER_MODEL_NAME,
                "messages": [
                    {"role": "system", "content": "You are an expert programmer. Provide clear, working code with brief explanations. /no_think"},
                    {"role": "user", "content": question}
                ],
                "max_tokens": 1500,
                "temperature": 0.3
            },
            timeout=120
        )
        if resp.status_code == 200:
            result = resp.json()
            coder_response = result["choices"][0]["message"]["content"]
            print(f"\n{'='*60}")
            print("📜 QWEN3-CODER OUTPUT (check it out, dude):")
            print(f"{'='*60}")
            print(coder_response)
            print(f"{'='*60}\n")
            return coder_response
        else:
            return f"Error calling coder: {resp.status_code}"
    except Exception as e:
        return f"Error: {str(e)}"


def search_emails_directly(query: str = "is:inbox", max_results: int = 5) -> str:
    """Directly call Gmail MCP to search emails."""
    print(f"   📧 Searching Gmail: {query}")
    try:
        resp = requests.post(
            f"{GMAIL_URL}/search_emails",
            json={"query": query, "maxResults": max_results},
            timeout=30
        )
        if resp.status_code == 200:
            result = resp.text
            print(f"\n{'='*60}")
            print("📧 GMAIL RESULTS:")
            print(f"{'='*60}")
            print(result[:2000] if len(result) > 2000 else result)
            print(f"{'='*60}\n")
            return result
        else:
            return f"Error searching emails: {resp.status_code}"
    except Exception as e:
        return f"Error: {str(e)}"


def list_calendar_directly(max_results: int = 10) -> str:
    """Directly call GCal MCP to list events."""
    print(f"   📅 Checking calendar...")
    try:
        resp = requests.post(
            f"{GCAL_URL}/list_events",
            json={"maxResults": max_results},
            timeout=30
        )
        if resp.status_code == 200:
            result = resp.text
            print(f"\n{'='*60}")
            print("📅 CALENDAR EVENTS:")
            print(f"{'='*60}")
            print(result[:2000] if len(result) > 2000 else result)
            print(f"{'='*60}\n")
            return result
        else:
            return f"Error listing events: {resp.status_code}"
    except Exception as e:
        return f"Error: {str(e)}"


# FIX #1 — New direct web search caller
def web_search_directly(query: str) -> str:
    """Directly call Tavily MCP to search the web."""
    print(f"   🌐 Searching web (Tavily): {query}")
    try:
        resp = requests.post(
            f"{TAVILY_URL}/search",
            json={"query": query},
            timeout=30
        )
        if resp.status_code == 200:
            result = resp.text
            print(f"\n{'='*60}")
            print("🌐 WEB SEARCH RESULTS:")
            print(f"{'='*60}")
            print(result[:3000] if len(result) > 3000 else result)
            print(f"{'='*60}\n")
            return result
        else:
            return f"Error searching web: {resp.status_code}"
    except Exception as e:
        return f"Error: {str(e)}"


# ============================================================================
# FIX C — Empty Result Guard
# ============================================================================
def is_empty_result(result: str) -> bool:
    """
    Check if a tool result is empty / useless.  If True, we skip LLM
    summarisation entirely and give the user a direct message.
    """
    if not result:
        return True
    stripped = result.strip().strip('"').strip("'").strip()
    if not stripped or stripped in ("[]", "{}", "null", "None", "''", '""'):
        return True
    # Gmail MCP sometimes returns just whitespace or empty JSON arrays
    if len(stripped) < 5:
        return True
    return False


# ============================================================================
# FIX #5 — Query Construction (rule-based for email, LLM-assisted for web)
# ============================================================================
def build_email_query(transcript: str) -> str:
    """
    Build a Gmail search query from the transcript using rules + current date.
    This avoids the LLM hallucinating placeholder templates like
    'from:[user's email] after:2022/MM/DD'.
    """
    text_lower = transcript.lower()
    tz = pytz.timezone(TIMEZONE)
    now = datetime.now(tz)

    parts = []

    # Time-based filters
    if "today" in text_lower or "this afternoon" in text_lower or "this morning" in text_lower:
        parts.append(f"after:{now.strftime('%Y/%m/%d')}")
    elif "yesterday" in text_lower:
        from datetime import timedelta
        yesterday = (now - timedelta(days=1)).strftime('%Y/%m/%d')
        parts.append(f"after:{yesterday}")
    elif "this week" in text_lower:
        from datetime import timedelta
        week_ago = (now - timedelta(days=7)).strftime('%Y/%m/%d')
        parts.append(f"after:{week_ago}")
    elif "last week" in text_lower:
        from datetime import timedelta
        two_weeks_ago = (now - timedelta(days=14)).strftime('%Y/%m/%d')
        one_week_ago = (now - timedelta(days=7)).strftime('%Y/%m/%d')
        parts.append(f"after:{two_weeks_ago} before:{one_week_ago}")

    # Read-state filters
    if "unread" in text_lower:
        parts.append("is:unread")

    # Sender filters
    sender_patterns = {
        "linkedin": "from:linkedin",
        "amazon": "from:amazon",
        "google": "from:google",
        "github": "from:github",
        "microsoft": "from:microsoft",
        "netflix": "from:netflix",
        "spotify": "from:spotify",
    }
    for keyword, gmail_filter in sender_patterns.items():
        if keyword in text_lower:
            parts.append(gmail_filter)

    # Default: inbox
    if not any(p.startswith("from:") for p in parts):
        parts.insert(0, "is:inbox")

    query = " ".join(parts) if parts else "is:inbox"
    print(f"   📋 Rule-based email query: \"{query}\"")
    return query


def build_search_query_via_llm(transcript: str) -> str:
    """
    Ask Mistral to extract a clean web search query from the transcript.
    Provides current date context so the model doesn't hallucinate dates.
    """
    tz = pytz.timezone(TIMEZONE)
    now = datetime.now(tz)
    date_str = now.strftime("%A, %B %d, %Y")

    extraction_prompt = (
        f"Today is {date_str}. "
        "Extract a concise web search query from the user's spoken request below. "
        "Return ONLY the search query string — no explanation, no quotes, no extra text. "
        "Include the year or specific date if the user mentioned one. "
        "Fix any obvious typos or misspellings.\n\n"
        f"User said: {transcript}"
    )

    try:
        resp = requests.post(
            f"{LLM_SERVER}/v1/chat/completions",
            json={
                "model": MODEL_NAME,
                "messages": [
                    {"role": "system", "content": "You are a helpful assistant. Reply with ONLY the requested query. No preamble, no explanation, no quotes. /no_think"},
                    {"role": "user", "content": extraction_prompt}
                ],
                "max_tokens": 60,
                "temperature": 0.1,
                "stream": False,
            },
            timeout=15
        )
        if resp.status_code == 200:
            query = resp.json()["choices"][0]["message"]["content"].strip()
            query = query.strip("\"'`")
            # Sanity check: reject if it contains placeholder brackets or is too long
            if query and "[" not in query and len(query) < 150:
                print(f"   🧠 LLM-built query: \"{query}\"")
                return query
            else:
                print(f"   ⚠️  LLM query rejected (placeholder/garbage): \"{query}\"")
    except Exception as e:
        print(f"   ⚠️  LLM query builder failed ({e}), using transcript directly")

    # Fallback: return the raw transcript
    return transcript


# ============================================================================
# Tool Execution (fallback path — when LLM emits tool calls)
# ============================================================================
def execute_tool(name: str, args: dict) -> str:
    """Execute a tool and return the result as a string."""
    print(f"   🔧 Executing: {name}({args})")

    try:
        if name == "search_emails":
            query = args.get("query", "is:inbox")
            max_results = args.get("maxResults", 5)
            resp = requests.post(
                f"{GMAIL_URL}/search_emails",
                json={"query": query, "maxResults": max_results},
                timeout=30
            )
            return resp.text if resp.status_code == 200 else f"Error: {resp.status_code}"

        elif name == "read_email":
            email_id = args.get("id", "")
            resp = requests.post(
                f"{GMAIL_URL}/read_email",
                json={"id": email_id},
                timeout=30
            )
            return resp.text if resp.status_code == 200 else f"Error: {resp.status_code}"

        elif name == "list_events":
            max_results = args.get("maxResults", 10)
            resp = requests.post(
                f"{GCAL_URL}/list_events",
                json={"maxResults": max_results},
                timeout=30
            )
            return resp.text if resp.status_code == 200 else f"Error: {resp.status_code}"

        elif name == "web_search":
            query = args.get("query", "")
            resp = requests.post(
                f"{TAVILY_URL}/search",
                json={"query": query},
                timeout=30
            )
            return resp.text if resp.status_code == 200 else f"Error: {resp.status_code}"

        elif name == "get_time":
            tz = pytz.timezone(TIMEZONE)
            now = datetime.now(tz)
            return json.dumps({
                "timezone": TIMEZONE,
                "datetime": now.isoformat(),
                "formatted": now.strftime("%A, %B %d, %Y at %H:%M:%S"),
                "date": now.strftime("%Y-%m-%d"),
                "time": now.strftime("%H:%M")
            })

        elif name == "ask_coder":
            question = args.get("question", "")
            print(f"   🧑‍💻 Asking Qwen3-Coder: {question[:50]}...")
            resp = requests.post(
                f"{CODER_LLM_SERVER}/v1/chat/completions",
                json={
                    "model": CODER_MODEL_NAME,
                    "messages": [
                        {"role": "system", "content": "You are an expert programmer. Provide concise, accurate answers. For code, include brief explanations. /no_think"},
                        {"role": "user", "content": question}
                    ],
                    "max_tokens": 1000,
                    "temperature": 0.3
                },
                timeout=120
            )
            if resp.status_code == 200:
                result = resp.json()
                coder_response = result["choices"][0]["message"]["content"]
                print(f"\n{'='*60}")
                print("📜 CODER RESPONSE (full):")
                print(f"{'='*60}")
                print(coder_response)
                print(f"{'='*60}\n")
                return coder_response
            else:
                return f"Error calling coder: {resp.status_code}"

        else:
            return f"Unknown tool: {name}"

    except Exception as e:
        return f"Error executing {name}: {str(e)}"


# ============================================================================
# FIX #2 — Improved Tool-Call Parser (added slash-command format)
# ============================================================================
def parse_tool_calls(content: str) -> list:
    """Parse tool calls from Mistral's response (multiple formats)."""
    tool_calls = []

    # Format 1: JSON array [{"name": "...", "arguments": {...}}]
    try:
        match = re.search(r'\[\s*\{[^]]+\}\s*\]', content, re.DOTALL)
        if match:
            calls = json.loads(match.group())
            for call in calls:
                if "name" in call:
                    tool_calls.append({
                        "name": call["name"],
                        "arguments": call.get("arguments", {})
                    })
            if tool_calls:
                return tool_calls
    except json.JSONDecodeError:
        pass

    # Format 2: Single JSON object {"name": "...", "arguments": {...}}
    if not tool_calls:
        try:
            match = re.search(r'\{\s*"name"\s*:', content)
            if match:
                start = match.start()
                depth = 0
                end = start
                for i, c in enumerate(content[start:]):
                    if c == '{':
                        depth += 1
                    elif c == '}':
                        depth -= 1
                        if depth == 0:
                            end = start + i + 1
                            break
                obj = json.loads(content[start:end])
                if "name" in obj:
                    tool_calls.append({
                        "name": obj["name"],
                        "arguments": obj.get("arguments", {})
                    })
                    return tool_calls
        except Exception:
            pass

    # Format 3: Python-style function call: tool_name("argument")
    tool_names = ["search_emails", "read_email", "list_events",
                  "web_search", "get_time", "ask_coder"]
    for tool in tool_names:
        pattern = rf'`?{tool}\s*\(\s*["\']([^"\']+)["\']\s*\)`?'
        match = re.search(pattern, content, re.IGNORECASE)
        if match:
            arg_value = match.group(1)
            if tool == "search_emails":
                tool_calls.append({"name": tool, "arguments": {"query": arg_value}})
            elif tool == "read_email":
                tool_calls.append({"name": tool, "arguments": {"id": arg_value}})
            elif tool == "web_search":
                tool_calls.append({"name": tool, "arguments": {"query": arg_value}})
            elif tool == "ask_coder":
                tool_calls.append({"name": tool, "arguments": {"question": arg_value}})
            elif tool == "list_events":
                tool_calls.append({"name": tool, "arguments": {}})
            elif tool == "get_time":
                tool_calls.append({"name": tool, "arguments": {}})
            return tool_calls

    # ------------------------------------------------------------------
    # FIX #2 — Format 4: Slash-command style that Mistral actually emits
    #   /web_search query: "Palmeiras vs Sao Paulo match result march 20"
    #   /search_emails query: "Palmeiras vs Sao Paulo" after:2023-03-20
    # ------------------------------------------------------------------
    for tool in tool_names:
        # Match: /tool_name  key: "value"  or  /tool_name key: value
        pattern = (
            rf'/?{tool}\s+'                       # tool name (optional leading /)
            rf'(?:query|id|question)\s*[:=]\s*'    # parameter name
            rf'["\']?(.+?)["\']?\s*$'              # value (optionally quoted)
        )
        match = re.search(pattern, content, re.IGNORECASE | re.MULTILINE)
        if match:
            arg_value = match.group(1).strip().strip("\"'")
            if tool in ("search_emails", "web_search"):
                tool_calls.append({"name": tool, "arguments": {"query": arg_value}})
            elif tool == "read_email":
                tool_calls.append({"name": tool, "arguments": {"id": arg_value}})
            elif tool == "ask_coder":
                tool_calls.append({"name": tool, "arguments": {"question": arg_value}})
            elif tool in ("list_events", "get_time"):
                tool_calls.append({"name": tool, "arguments": {}})
            return tool_calls

    # Format 5: Bare slash-command with no named parameter
    #   /web_search "some query"   or   /list_events
    for tool in tool_names:
        pattern = rf'/?{tool}\s*["\'](.+?)["\']'
        match = re.search(pattern, content, re.IGNORECASE)
        if match:
            arg_value = match.group(1).strip()
            if tool in ("search_emails", "web_search"):
                tool_calls.append({"name": tool, "arguments": {"query": arg_value}})
            elif tool == "read_email":
                tool_calls.append({"name": tool, "arguments": {"id": arg_value}})
            elif tool == "ask_coder":
                tool_calls.append({"name": tool, "arguments": {"question": arg_value}})
            return tool_calls
        # No-arg tools
        bare = re.search(rf'/?{tool}\s*$', content, re.IGNORECASE | re.MULTILINE)
        if bare and tool in ("list_events", "get_time"):
            tool_calls.append({"name": tool, "arguments": {}})
            return tool_calls

    return tool_calls


# ============================================================================
# LLM Interaction
# ============================================================================
def chat_completion(messages: list, use_tools: bool = True) -> tuple:
    """
    Send messages to LLM and get response.
    Returns (content, tool_calls)
    """
    payload = {
        "model": MODEL_NAME,
        "messages": messages,
        "max_tokens": 500,
        "temperature": 0.7,
        "stream": False,
    }

    if use_tools:
        payload["tools"] = TOOLS

    response = requests.post(
        f"{LLM_SERVER}/v1/chat/completions",
        json=payload,
        timeout=60
    )
    response.raise_for_status()

    result = response.json()
    message = result["choices"][0]["message"]
    content = message.get("content", "")

    # Check for native tool_calls (Ollama may populate this)
    tool_calls = message.get("tool_calls", [])

    # If no native tool_calls, parse from content
    if not tool_calls and content:
        parsed = parse_tool_calls(content)
        if parsed:
            tool_calls = parsed

    return content, tool_calls


# FIX #7 — Improved process_with_tools with proper message roles
def process_with_tools(messages: list) -> str:
    """Process a conversation, handling tool calls if needed."""
    max_iterations = 3

    for i in range(max_iterations):
        content, tool_calls = chat_completion(messages)

        if not tool_calls:
            return content

        # Execute tool calls (only first one to be safe)
        tc = tool_calls[0]
        if isinstance(tc, dict):
            name = tc.get("name") or tc.get("function", {}).get("name", "")
            args = tc.get("arguments") or tc.get("function", {}).get("arguments", {})
        else:
            continue

        if not name:
            return content

        # Execute the tool
        result = execute_tool(name, args if isinstance(args, dict) else json.loads(args))

        # FIX #7 — Use assistant + system messages instead of fake "user"
        # messages.  This avoids confusing small models with tool results
        # masquerading as user utterances.
        messages.append({
            "role": "assistant",
            "content": f"I used the {name} tool."
        })
        messages.append({
            "role": "system",
            "content": (
                f"[Tool Result — {name}]:\n{result[:2000]}\n\n"
                "Summarise this information for the user in a short, conversational way. "
                "Do NOT list your tools. Do NOT make up data — only use what the tool returned."
            )
        })

    # If we hit max iterations, get final response without tools
    content, _ = chat_completion(messages, use_tools=False)
    return content


# ============================================================================
# Text-to-Speech
# ============================================================================
def speak_text(tts_service, text: str, sample_rate: int = 22050):
    """Convert text to speech and play it."""
    clean_text = re.sub(r'https?://\S+', '', text)
    clean_text = re.sub(r'\[.*?\]', '', clean_text)
    clean_text = re.sub(r'\*+', '', clean_text)
    clean_text = re.sub(r'#+\s*', '', clean_text)
    clean_text = re.sub(r'\n+', '. ', clean_text)
    clean_text = re.sub(r'\s+', ' ', clean_text).strip()

    if not clean_text:
        return

    try:
        responses = tts_service.synthesize_online(
            text=clean_text,
            voice_name="English-US.Male-1",
            language_code="en-US",
            sample_rate_hz=sample_rate,
        )

        audio_stream = riva.client.audio_io.SoundCallBack(
            output_device_index=None,
            nchannels=1,
            sampwidth=2,
            framerate=sample_rate,
        )

        for response in responses:
            audio_stream(response.audio)

        time.sleep(0.5)

    except Exception as e:
        print(f"   ⚠️  TTS error: {e}")


# ============================================================================
# Main
# ============================================================================
def get_current_time_str() -> str:
    """Get current time string for system prompt."""
    tz = pytz.timezone(TIMEZONE)
    now = datetime.now(tz)
    return now.strftime("%A, %B %d, %Y at %H:%M")


def main():
    parser = argparse.ArgumentParser(description="Soundwave Voice Agent v1.4")
    parser.add_argument("--device", type=int, default=23, help="Audio input device index")
    parser.add_argument("--silence-timeout", type=float, default=2.0, help="Seconds of silence before sending")
    parser.add_argument("--no-tts", action="store_true", help="Disable text-to-speech")
    parser.add_argument("--no-tools", action="store_true", help="Disable tool calling")
    parser.add_argument("--list-devices", action="store_true", help="List audio devices and exit")
    args = parser.parse_args()

    # List audio devices if requested
    if args.list_devices:
        import pyaudio
        p = pyaudio.PyAudio()
        print("\n🎤 Available Audio Input Devices:\n")
        for i in range(p.get_device_count()):
            info = p.get_device_info_by_index(i)
            if info['maxInputChannels'] > 0:
                print(f"  [{i}] {info['name']}")
        p.terminate()
        return

    # Setup ASR
    print("🔌 Connecting to services...")
    asr_auth = riva.client.Auth(uri=ASR_SERVER, use_ssl=False)
    asr_service = riva.client.ASRService(asr_auth)
    print(f"   ✅ ASR: {ASR_SERVER}")

    asr_config = riva.client.StreamingRecognitionConfig(
        config=riva.client.RecognitionConfig(
            encoding=riva.client.AudioEncoding.LINEAR_PCM,
            language_code="en-US",
            max_alternatives=1,
            enable_automatic_punctuation=True,
            sample_rate_hertz=16000,
            audio_channel_count=1,
        ),
        interim_results=True,
    )

    # Setup TTS
    tts_service = None
    if not args.no_tts:
        try:
            tts_auth = riva.client.Auth(uri=TTS_SERVER, use_ssl=False)
            tts_service = riva.client.SpeechSynthesisService(tts_auth)
            print(f"   ✅ TTS: {TTS_SERVER}")
        except Exception as e:
            print(f"   ⚠️  TTS unavailable: {e}")

    # Test LLM connection
    try:
        resp = requests.get(f"{LLM_SERVER}/api/tags", timeout=5)
        print(f"   ✅ LLM: {LLM_SERVER} ({MODEL_NAME})")
    except Exception:
        print(f"   ⚠️  LLM: {LLM_SERVER} (connection test failed)")

    # Test Coder LLM connection
    try:
        resp = requests.get(f"{CODER_LLM_SERVER}/health", timeout=5)
        print(f"   ✅ Coder: {CODER_LLM_SERVER} ({CODER_MODEL_NAME})")
    except Exception:
        print(f"   ⚠️  Coder: {CODER_LLM_SERVER} (unavailable)")

    # Test tool endpoints
    if not args.no_tools:
        for name, url in [("Gmail", GMAIL_URL), ("GCal", GCAL_URL), ("Tavily", TAVILY_URL)]:
            try:
                resp = requests.get(f"{url}/openapi.json", timeout=5)
                print(f"   ✅ {name}: {url}")
            except Exception:
                print(f"   ⚠️  {name}: {url} (unavailable)")

    # Banner
    print(f"""
╔══════════════════════════════════════════════════════════════╗
║         🤖 SOUNDWAVE v1.4 — Cybertronian Voice Agent         ║
╠══════════════════════════════════════════════════════════════╣
║  Speak naturally and pause {args.silence_timeout:.1f}s when done.                  ║
║  Tools: Gmail, Calendar, Web Search, Time, Coder (Qwen3)     ║
║  ASR fuzzy correction: ON                                     ║
║  Press Ctrl+C to exit                                        ║
╚══════════════════════════════════════════════════════════════╝
""")

    # ----------------------------------------------------------------
    # FIX #4 + FIX #6 — Hardened system prompt
    # ----------------------------------------------------------------
    system_prompt = f"""You are Soundwave, a Cybertronian AI voice assistant. Your responses are read aloud via text-to-speech.

PERSONALITY — use ONLY for greetings, goodbyes, and casual chat:
- Chill, laid-back surf-dude vibe. Use words like "dude", "totally", "no worries", "rad".
- You can drop a subtle Transformers reference occasionally.
- Be positive and encouraging.

TASK MODE — use when answering questions, reporting tool results, or doing work:
- Be factual, concise, and direct. No roleplay, no character voice, no emojis.
- Report exactly what the data says. Do NOT embellish, invent, or add fictional details.
- Keep it short: 1-3 sentences unless the user asks for more.

STRICT RULES — follow always:
1. Keep responses under 35 words unless the user asks for details or it involves code.
2. Use short, clear sentences. No bullet points, markdown, or special characters — they break TTS.
3. NEVER guess, fabricate, or make up factual information such as scores, dates, prices, statistics, emails, events, or news. If you do not have the data, say "I don't have that info right now" — do NOT invent an answer.
4. NEVER list your tools or capabilities unless the user explicitly asks "what can you do". Just act on the request.
5. If a proper noun sounds misspelled by speech recognition, ask ONE short clarifying question before acting.
6. If a question is ambiguous, ask one short clarifying question.

Current time: {get_current_time_str()}
Timezone: {TIMEZONE}

You have access to tools (email, calendar, web search, coder, time). They are called automatically — just focus on answering the user.
/no_think"""

    conversation = [{"role": "system", "content": system_prompt}]

    # ================================================================
    # Main Loop
    # ================================================================
    while True:
        print("\n🎤 Listening... (speak now)")

        transcript = ""
        last_update = time.time()

        with riva.client.audio_io.MicrophoneStream(
            rate=16000,
            chunk=int(16000 * 0.1),
            device=args.device,
        ) as audio_stream:
            try:
                responses = asr_service.streaming_response_generator(
                    audio_chunks=audio_stream,
                    streaming_config=asr_config,
                )

                for response in responses:
                    for result in response.results:
                        if result.is_final:
                            transcript = result.alternatives[0].transcript
                            print(f"\r\033[K📝 You: {transcript}")
                            last_update = time.time()
                        else:
                            partial = result.alternatives[0].transcript
                            print(f"\r\033[K   {partial}...", end="", flush=True)
                            last_update = time.time()

                    if transcript and (time.time() - last_update) > args.silence_timeout:
                        break

            except KeyboardInterrupt:
                print("\n\n🤙 Catch you on the flip side, dude. Till All ARE One. Soundwave out!")
                return

        if not transcript.strip():
            continue

        # ==============================================================
        # FIX #3 — Apply ASR fuzzy correction before any routing
        # ==============================================================
        transcript = correct_asr_transcript(transcript)

        # ==============================================================
        # Keyword-based tool routing (bypass LLM for tool selection)
        # ==============================================================

        # --- CODING ---
        if is_coding_request(transcript):
            print("\n🧑‍💻 Coding request detected — routing to Qwen3-Coder...")
            try:
                coder_response = ask_coder_directly(transcript)
                if is_empty_result(coder_response):
                    summary = "The coder service didn't return anything. Try again or rephrase your question."
                else:
                    summary_messages = [
                        {"role": "system", "content": "Summarise this code output in 1-2 short sentences for a voice assistant. Say the code is in the terminal and briefly describe what it does. Be concise and factual. /no_think"},
                        {"role": "user", "content": f"Summarise: {coder_response[:500]}"}
                    ]
                    summary, _ = chat_completion(summary_messages, use_tools=False)
                print(f"\n💬 Soundwave: {summary}")
                if tts_service:
                    print("\n🔊 Speaking...")
                    speak_text(tts_service, summary)
            except Exception as e:
                print(f"\n❌ Error: {e}")
            continue

        # --- WEB SEARCH (FIX #1 — keyword bypass) ---
        if is_web_search_request(transcript):
            print("\n🌐 Web search detected — querying Tavily...")
            try:
                search_query = build_search_query_via_llm(transcript)
                search_results = web_search_directly(search_query)

                if is_empty_result(search_results):
                    summary = "The web search came back empty. Try rephrasing or being more specific."
                else:
                    summary_messages = [
                        {"role": "system", "content": (
                            "Summarise these web search results in 2-3 short sentences for a voice assistant. "
                            "Only state facts found in the results. "
                            "If the results don't contain the answer, say so. "
                            "Do NOT invent or guess any data. Be factual and concise. /no_think"
                        )},
                        {"role": "user", "content": f"Summarise for voice:\n{search_results[:2000]}"}
                    ]
                    summary, _ = chat_completion(summary_messages, use_tools=False)
                print(f"\n💬 Soundwave: {summary}")
                if tts_service:
                    print("\n🔊 Speaking...")
                    speak_text(tts_service, summary)
            except Exception as e:
                print(f"\n❌ Error: {e}")
            continue

        # --- EMAIL (FIX B — rule-based query builder) ---
        if is_email_request(transcript):
            print("\n📧 Email request detected — checking Gmail...")
            try:
                query = build_email_query(transcript)
                email_results = search_emails_directly(query)

                if is_empty_result(email_results):
                    summary = "No emails matched that search. Your inbox might be empty for that filter, or try a different query."
                else:
                    summary_messages = [
                        {"role": "system", "content": (
                            "Summarise these email results in 2-3 short sentences for a voice assistant. "
                            "Mention sender and subject of each email. Be factual and concise. "
                            "Do NOT invent emails that are not in the data. "
                            "If the data is empty or has no emails, say so. /no_think"
                        )},
                        {"role": "user", "content": f"Summarise these emails for voice:\n{email_results[:1500]}"}
                    ]
                    summary, _ = chat_completion(summary_messages, use_tools=False)
                print(f"\n💬 Soundwave: {summary}")
                if tts_service:
                    print("\n🔊 Speaking...")
                    speak_text(tts_service, summary)
            except Exception as e:
                print(f"\n❌ Error: {e}")
            continue

        # --- CALENDAR ---
        if is_calendar_request(transcript):
            print("\n📅 Calendar request detected — checking schedule...")
            try:
                calendar_results = list_calendar_directly()

                if is_empty_result(calendar_results):
                    summary = "No upcoming events found on your calendar."
                else:
                    summary_messages = [
                        {"role": "system", "content": (
                            "Summarise these calendar events in 2-3 short sentences for a voice assistant. "
                            "Mention event times and titles. Be factual and concise. "
                            "Do NOT invent events that are not in the data. /no_think"
                        )},
                        {"role": "user", "content": f"Summarise these calendar events for voice:\n{calendar_results[:1500]}"}
                    ]
                    summary, _ = chat_completion(summary_messages, use_tools=False)
                print(f"\n💬 Soundwave: {summary}")
                if tts_service:
                    print("\n🔊 Speaking...")
                    speak_text(tts_service, summary)
            except Exception as e:
                print(f"\n❌ Error: {e}")
            continue

        # ==============================================================
        # General conversation (fallback — LLM may still trigger tools)
        # ==============================================================
        print("\n⚙️  Soundwave's processing...")
        conversation.append({"role": "user", "content": transcript})

        try:
            if args.no_tools:
                response, _ = chat_completion(conversation, use_tools=False)
            else:
                response = process_with_tools(conversation)

            conversation.append({"role": "assistant", "content": response})
            print(f"\n💬 Soundwave: {response}")

            if tts_service:
                print("\n🔊 Speaking...")
                speak_text(tts_service, response)

        except Exception as e:
            print(f"\n❌ Error: {e}")
            conversation.pop()  # Remove failed user message


if __name__ == "__main__":
    main()
