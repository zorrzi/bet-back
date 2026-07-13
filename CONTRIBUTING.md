# CONTRIBUTING.md

## Convenções de código

- Python 3.12+, type hints em tudo, `mypy` strict verde.
- `ruff check` + `ruff format` (configurados em `pyproject.toml`).
- Camadas: `routers → services → repositories → models` (+ `schemas`,
  `providers`). Regra de negócio nunca em router.
- Parâmetros de domínio em `src/config/settings.py`, nunca constantes
  mágicas.
- Fórmulas financeiras/estatísticas exigem teste unitário validado contra um
  caso calculado à mão (de-vig, EV, Kelly, CLV, settle).

## Commits

- **Conventional Commits**: `feat:`, `fix:`, `chore:`, `docs:`, `test:`,
  `refactor:`.
- Pequenos e incrementais; cada commit deixa o projeto funcional.
- Mensagem explica o **porquê**, não só o quê.
- Antes de commit relevante: rodar a skill `code-review`, corrigir, então
  commitar.

## Branches e PRs

- `main` sempre deployável (deploy automático após CI verde).
- Feature branches quando a mudança for grande ou arriscada.
- Checklist de PR:
  - [ ] `pytest`, `ruff check`, `ruff format --check`, `mypy` verdes
  - [ ] Testes para código novo (núcleo matemático: obrigatório e rigoroso)
  - [ ] Sem segredo/constante mágica
  - [ ] Guardrails de domínio respeitados (ver `CLAUDE.md` §Guardrails)
  - [ ] Docs afetados atualizados no mesmo commit (`CLAUDE.md`, `ROADMAP.md`,
        ADR se decisão nova)

## Migrations

- Sempre via Alembic (`alembic revision --autogenerate` + revisão manual).
- Nunca editar migration já aplicada em prod; criar nova.
- Upgrade e downgrade precisam passar em `tests/integration/test_migrations.py`.
