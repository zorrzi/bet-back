# CLAUDE.md — betting-backend

Instruções para o agente. Leia antes de qualquer alteração. O brief completo
está em `../spec.md` (fora do repo); este arquivo é o resumo operacional.

## O que é este projeto

Plataforma de **análise de valor em apostas esportivas** (futebol). O objetivo
NÃO é prever partidas melhor que as casas — é estimar probabilidades próprias
e identificar seleções onde `model_prob > prob justa de mercado (de-vig)`,
ou seja, apostas com **EV positivo**. Se não há valor, o sistema **não
aposta** — e isso é um resultado válido.

**Métrica-mãe: CLV (Closing Line Value).** Apostar consistentemente a odd
melhor que a de fechamento (Pinnacle como referência sharp) é o indicador
antecedente de edge real. Todo relatório/tela reporta CLV ANTES de lucro.

## Stack

- FastAPI + SQLAlchemy 2.0 (typed) + Alembic, PostgreSQL (Railway em prod)
- Pydantic v2 + pydantic-settings (config 100% via env/.env)
- APScheduler (jobs in-process, gated por `SCHEDULER_ENABLED`)
- pytest (SQLite in-memory) · ruff (lint+format) · mypy strict
- Provedores: API-Football (fixtures/resultados) e The Odds API (odds).
  Sempre atrás das interfaces em `src/providers/base.py`.

## Estrutura (camadas — não misturar)

```
src/routers/       HTTP apenas; sem regra de negócio
src/services/      regra de negócio (ingestão, closing, ...)
src/repositories/  acesso a dados (queries SQLAlchemy)
src/models/        ORM (schema §4 da spec)
src/schemas/       Pydantic de request/response
src/providers/     integrações externas (base.py = interfaces)
src/config/        settings, security (X-API-Key), logging JSON
src/jobs/          scheduler APScheduler
alembic/           migrations (NUNCA alterar schema à mão)
tests/             unit/ + integration/ (SQLite in-memory)
```

## Comandos (Windows; venv em `.venv`)

```powershell
.\.venv\Scripts\python.exe -m pytest              # testes + cobertura
.\.venv\Scripts\python.exe -m ruff check .        # lint
.\.venv\Scripts\python.exe -m ruff format .       # format
.\.venv\Scripts\python.exe -m mypy                # type-check (strict)
.\.venv\Scripts\python.exe -m alembic upgrade head
.\.venv\Scripts\python.exe -m uvicorn src.app:app --reload
```

Tudo precisa estar verde antes de commit (CI roda os quatro + pip-audit).

## Guardrails de domínio (spec §12 — NÃO remover)

1. **`odds_snapshots` é APPEND-ONLY.** Nunca fazer UPDATE de preço. Cada
   captura = nova linha com `captured_at`. Única mutação permitida:
   `is_closing=true` no último snapshot pré-kickoff (job mark-closing).
2. **Sem valor → sem aposta.** Sinais só existem com `edge > min_edge`.
3. **CLV acima de lucro** em todo relatório, resposta de API e tela.
4. **Kelly fracionário sempre** (`kelly_multiplier` 0.25–0.5, teto
   `max_stake_pct`). Nunca Kelly cheio.
5. **Versionar modelo** (`model_version`) em toda previsão.
6. **`bets.placed_at` < kickoff** — validar; aposta pós-kickoff corrompe o CLV.
7. **Nunca usar informação do futuro** em backtest (odds com
   `captured_at < kickoff` apenas; out-of-sample para métricas).
8. **Paper trading antes de dinheiro real**, com CLV como critério.

## Nunca fazer

- Commitar segredo (chaves, DATABASE_URL). Tudo via env; `.env` no gitignore.
- SQL por string-building — só ORM/parametrizado.
- CORS `*` em produção.
- Prometer lucro em qualquer texto de UI/API.
- Constante mágica de domínio no código — `min_edge`, `kelly_multiplier`,
  `max_stake_pct` etc. vivem em `src/config/settings.py`.
- Fórmula financeira/estatística sem teste unitário validado à mão
  (de-vig, EV, Kelly, CLV, settle).

## Fluxo obrigatório com plugins/skills (spec §10.1)

- **`code-review`** — SEMPRE antes de commit/PR relevante: terminou
  incremento → review → corrigir → commitar.
- **`security-guidance`** — antes de deploy e ao mexer em auth, segredos,
  CORS, rotas públicas ou dependências novas.
- **`frontend-design`** — sempre que construir/redesenhar UI (repo
  bet-front).
- **`claude-md-management`** — para manter este arquivo e docs da §10 ao fim
  de cada fase.
- **`superpowers`** — planejamento de tarefas complexas (quebrar fases,
  planejar backtest).

## Convenções

- Conventional Commits (`feat:`, `fix:`, `chore:`, `docs:`, `test:`,
  `refactor:`); commits pequenos e incrementais, projeto sempre funcional;
  mensagens explicam o *porquê*.
- Timestamps sempre UTC (`timestamptz`). Atenção: SQLite (testes) devolve
  datetimes naive; Postgres devolve aware. Não comparar os dois em Python.
- Type hints em tudo; mypy strict; sem `Any` gratuito.
- Logging estruturado JSON (`src/config/logging_config.py`); nunca logar
  segredo.
- Idempotência de ingestão via `provider_id` (upsert), EXCETO
  `odds_snapshots` (sempre INSERT).

## Estado atual (atualizar ao fim de cada fase)

- **Fase 1 (fundação de dados): CONCLUÍDA no ambiente local** — schema §4
  completo, primeira captura real em 2026-07-13 (13 partidas do Brasileirão,
  979 snapshots, Pinnacle sharp). Tudo roda local por decisão do dono
  (Postgres via `docker compose up -d`; deploy adiado).
- **ADR-0004 (importante):** o plano free da API-Football NÃO acessa
  temporadas atuais (só 2022–2024). Partidas e resultados da temporada
  corrente vêm da The Odds API (autocreate de matches a partir de eventos de
  odds + job `/jobs/ingest/scores`). API-Football fica para histórico
  2022–2024 (calibração Fase 2).
- **Fase 2 (motor de modelagem): CONCLUÍDA** — de-vig (mult/Shin/power) em
  `src/services/devig.py`; Dixon-Coles (`dixoncoles_v1`) com decaimento
  temporal e janela de 4 anos em `src/services/modeling/`; histórico
  2012–2026 importado do football-data.co.uk com closings da Pinnacle
  (ADR-0005); aliases canônicos de times entre provedores em
  `src/utils/text.py::canonical_team_key` (usar SEMPRE para matching).
  13/13 jogos previstos na validação real.
- **Fase 3 (sinais + staking): CONCLUÍDA** — staking puro em
  `src/services/staking.py` (edge push-aware, Kelly fracionário, teto),
  geração de sinais em `value_bet_service.py` (fair sharp de-vigada,
  melhor odd, expira candidatos ao regenerar), apostas paper + settle com
  CLV em `bet_service.py`, banca em ledger append-only. 12 sinais reais
  gerados na validação.
- **Fase 4 (backtest): engine CONCLUÍDA e veredito emitido** —
  `backtest_service.py` (cronológico, refit mensal warm-start, sem
  informação do futuro, rotas /backtests assíncronas). **Run real:
  dixoncoles_v1 REFUTADO** (737 apostas OOS 2024–2026, ROI −22,7%,
  Sharpe −3,0; seleção adversa nos maiores "edges"). NENHUMA aposta (nem
  paper) com v1; feed de value_bets atual é inválido (ADR-0006).
- Próximo: `dixoncoles_v2` com calibração/shrinkage p/ mercado
  (w·modelo + (1−w)·fair), re-validado no mesmo harness; só então Fase 5.
- Fases 5–7: ver `docs/ROADMAP.md`. Decisões em `docs/decisions/` (ADRs);
  schema em `docs/DATA_MODEL.md`; glossário/fórmulas em `docs/DOMAIN.md`.
