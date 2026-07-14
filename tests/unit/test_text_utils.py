from src.utils.text import canonical_team_key, normalize_team_name


def test_canonical_key_maps_known_cross_provider_variants() -> None:
    """Confirmed live 2026-07-13: The Odds API vs football-data.co.uk."""
    pairs = [
        ("Atletico-MG", "Atletico Mineiro"),
        ("Athletico-PR", "Atletico Paranaense"),
        ("Botafogo RJ", "Botafogo"),
        ("Bragantino", "Bragantino-SP"),
        ("Chapecoense-SC", "Chapecoense"),
        ("Flamengo RJ", "Flamengo"),
        ("Vasco", "Vasco da Gama"),
    ]
    for variant, canonical in pairs:
        assert canonical_team_key(variant) == canonical_team_key(canonical)


def test_canonical_key_is_identity_for_unaliased_names() -> None:
    assert canonical_team_key("São Paulo") == "sao paulo"
    assert canonical_team_key("Grêmio") == "gremio"


def test_strips_accents() -> None:
    assert normalize_team_name("São Paulo") == "sao paulo"
    assert normalize_team_name("Grêmio") == "gremio"
    assert normalize_team_name("Atlético-MG") == "atletico mg"


def test_collapses_case_and_whitespace() -> None:
    assert normalize_team_name("  FLAMENGO ") == "flamengo"
    assert normalize_team_name("Vasco  da   Gama") == "vasco da gama"


def test_equivalent_cross_provider_spellings_normalize_equal() -> None:
    assert normalize_team_name("Sao Paulo") == normalize_team_name("São Paulo")
