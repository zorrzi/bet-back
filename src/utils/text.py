"""Text normalization for cross-provider entity matching.

The Odds API and API-Football spell team names differently ('Sao Paulo' vs
'São Paulo', 'Atletico-MG'). Matching on raw names silently drops odds
events — and lost snapshots are unrecoverable. Comparison always goes
through this normal form; stored names keep the provider's original spelling.
"""

import re
import unicodedata


def normalize_team_name(name: str) -> str:
    """Accent-strip, lowercase, and collapse separators.

    'São Paulo' -> 'sao paulo'; 'Atlético-MG ' -> 'atletico mg'.
    """
    decomposed = unicodedata.normalize("NFKD", name)
    ascii_only = decomposed.encode("ascii", "ignore").decode("ascii")
    return re.sub(r"[^a-z0-9]+", " ", ascii_only.lower()).strip()
