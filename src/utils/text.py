"""Text normalization for cross-provider entity matching.

The Odds API and API-Football spell team names differently ('Sao Paulo' vs
'São Paulo', 'Atletico-MG'). Matching on raw names silently drops odds
events — and lost snapshots are unrecoverable. Comparison always goes
through this normal form; stored names keep the provider's original spelling.
"""

import re
import unicodedata
from decimal import Decimal


def format_market_line(line: Decimal) -> str:
    """Market-code fragment for a line: 2.5 -> '2_5'; -0.5 -> '-0_5'
    (spec §4.2 codes like 'OU_2_5', 'AH_-0_5')."""
    text = format(line.normalize(), "f")
    return text.replace(".", "_")


def normalize_team_name(name: str) -> str:
    """Accent-strip, lowercase, and collapse separators.

    'São Paulo' -> 'sao paulo'; 'Atlético-MG ' -> 'atletico mg'.
    """
    decomposed = unicodedata.normalize("NFKD", name)
    ascii_only = decomposed.encode("ascii", "ignore").decode("ascii")
    return re.sub(r"[^a-z0-9]+", " ", ascii_only.lower()).strip()


# Curated variant -> canonical map for names that normalize differently
# across providers (canonical side = The Odds API spelling, because those
# team rows are created first by live ingestion). Confirmed live against
# football-data.co.uk BRA.csv on 2026-07-13; extend when the unmatched-event
# logs surface new variants.
_TEAM_ALIASES = {
    "atletico mg": "atletico mineiro",
    "athletico pr": "atletico paranaense",
    "atletico pr": "atletico paranaense",
    "botafogo rj": "botafogo",
    "bragantino": "bragantino sp",
    "rb bragantino": "bragantino sp",
    "red bull bragantino": "bragantino sp",
    "chapecoense sc": "chapecoense",
    "flamengo rj": "flamengo",
    "vasco": "vasco da gama",
    "america mg": "america mineiro",
}


def canonical_team_key(name: str) -> str:
    """Cross-provider identity key: normalized name mapped through the
    alias table. All team matching/bridging must go through this."""
    normalized = normalize_team_name(name)
    return _TEAM_ALIASES.get(normalized, normalized)
