from src.utils.text import normalize_team_name


def test_strips_accents() -> None:
    assert normalize_team_name("São Paulo") == "sao paulo"
    assert normalize_team_name("Grêmio") == "gremio"
    assert normalize_team_name("Atlético-MG") == "atletico mg"


def test_collapses_case_and_whitespace() -> None:
    assert normalize_team_name("  FLAMENGO ") == "flamengo"
    assert normalize_team_name("Vasco  da   Gama") == "vasco da gama"


def test_equivalent_cross_provider_spellings_normalize_equal() -> None:
    assert normalize_team_name("Sao Paulo") == normalize_team_name("São Paulo")
