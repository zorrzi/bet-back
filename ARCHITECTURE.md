# ARCHITECTURE.md

## Camadas (por quê, não só o quê)

```
HTTP ──► src/routers ──► src/services ──► src/repositories ──► src/models (ORM)
                │               │
                ▼               ▼
          src/schemas     src/providers (APIs externas)
```

- **routers/** — só tradução HTTP↔domínio (validação Pydantic, status codes,
  paginação). Sem regra de negócio: regras testáveis não podem depender de
  request/response.
- **services/** — regra de negócio pura sobre sessões SQLAlchemy. São a
  unidade chamada tanto pelas rotas de jobs quanto pelo scheduler — um único
  caminho de código para ingestão manual e agendada.
- **repositories/** — todas as queries. Isola o ORM para que mudanças de
  schema/índice não vazem para os services.
- **providers/** — cada fonte externa atrás de `FixtureProvider`/`OddsProvider`
  (`base.py`). O núcleo nunca vê o formato de wire dos provedores; trocar de
  provedor = escrever um adaptador novo.
- **config/** — `Settings` (pydantic-settings) é a única porta para o
  ambiente; parâmetros de domínio (`min_edge`, `kelly_multiplier`,
  `max_stake_pct`) vivem aqui porque serão calibrados sem redeploy de código.

## Fluxo de dados (Fase 1)

```
API-Football ─fixtures/resultados─► FixtureIngestionService ─upsert─► leagues/teams/matches
The Odds API ─odds correntes──────► OddsIngestionService ───INSERT──► odds_snapshots (append-only)
relógio ──────────────────────────► ClosingService ─────► is_closing=true no último snapshot pré-kickoff
```

Fases seguintes (ver `docs/ROADMAP.md`): modelagem Dixon-Coles → de-vig →
sinais EV/Kelly → backtest com CLV → paper trading → frontend.

## Decisões estruturais e porquês

- **Odds são histórico imutável (append-only).** CLV e backtest honesto
  exigem reconstruir "que preço estava disponível no instante T". Um UPDATE
  destruiria essa capacidade para sempre. Por isso o repositório de odds nem
  expõe método de update de preço.
- **Resolução de eventos entre provedores é conservadora.** The Odds API e
  API-Football não compartilham IDs. Um evento de odds só é aceito se kickoff
  e nomes dos dois times baterem exatamente (case-insensitive); caso
  contrário é logado e pulado. Preferimos perder um snapshot a atribuir odds
  à partida errada (ver ADR-0003).
- **Scheduler in-process (APScheduler)** — MVP de um usuário; Celery/Redis
  só se o volume exigir (spec §2). Jobs são wrappers finos sobre os services,
  com sessão própria por execução.
- **Idempotência**: upsert por `provider_id` em tudo, exceto
  `odds_snapshots` (sempre INSERT — duplicar captura é aceitável, sobrescrever
  não).
- **Migrations = fonte da verdade do schema.** `alembic upgrade head` roda no
  deploy (railway.json). Testes verificam upgrade E downgrade.
- **Testes em SQLite in-memory** para velocidade e isolamento; os tipos dos
  models são portáveis de propósito (JSON com variant JSONB, Numeric,
  DateTime tz-aware). Cuidado documentado: SQLite devolve datetimes naive.
