# DATA_MODEL.md — schema e racional

Schema completo em `alembic/versions/` (fonte da verdade) e
`src/models/`. Timestamps sempre `timestamptz` (UTC). IDs internos são
surrogate keys; `provider_id` guarda o ID do provedor externo e é a chave de
idempotência da ingestão.

## Domínio esportivo

| Tabela | Racional |
|---|---|
| `leagues` | liga+temporada (`UNIQUE(provider_id, season)`), 1 liga no MVP |
| `teams` | `UNIQUE(provider_id)` — IDs da API-Football são globais |
| `players` | `team_id` nullable (jogador troca de time). Base p/ props (Fase 7) |
| `matches` | fixture; `status` normalizado (scheduled/live/finished/postponed); resultado preenchido pós-jogo pela própria ingestão de fixtures. Índices em `kickoff_utc` e `status` |
| `match_stats` | agregados pós-jogo por time (`UNIQUE(match_id, team_id)`) |
| `player_match_stats` | por jogador por jogo — matéria-prima das props |
| `lineups` | quem jogou e quem foi titular — props dependem de minutos esperados |

## Odds — o coração do sistema

| Tabela | Racional |
|---|---|
| `bookmakers` | `is_sharp=true` marca a referência de de-vig/CLV (Pinnacle) |
| `markets` | `code` único; a linha faz parte do código (`OU_2_5`, `AH_-0_5`) — um mercado = um grupo de de-vig; `n_selections` alimenta o de-vig |
| `odds_snapshots` | **APPEND-ONLY.** Cada captura = linha nova com `captured_at`. `is_closing=true` no último snapshot pré-kickoff por (bookmaker, market, selection, line) |

**Por que append-only é inegociável:** CLV = comparar a odd tomada com a odd
de fechamento; backtest honesto = reconstruir o que era visível em qualquer
instante T (`captured_at < T`). Qualquer UPDATE de preço destrói essas duas
capacidades permanentemente. O `OddsRepository` nem expõe update de preço.

**Cálculo do CLV** (spec §6.2): para aposta a `taken_odds` com fechamento
`closing_odds` na MESMA seleção: `clv = taken_odds/closing_odds − 1` (bruto)
ou comparação de fair_probs de-vigadas (preferível). Ver `docs/DOMAIN.md`.

## Modelo, sinais e apostas

| Tabela | Racional |
|---|---|
| `model_predictions` | prob do NOSSO modelo por seleção; `model_version` sempre preenchido para comparar versões em backtest |
| `value_bets` | sinal gerado quando `model_prob × offered_odds − 1 > min_edge`; guarda `fair_prob` (de-vig da linha sharp), `edge`, `kelly_fraction`, `suggested_stake`; `status`: candidate/placed/skipped/expired |
| `bets` | aposta registrada (paper ou real). `placed_at` DEVE ser < kickoff (validado no service). Pós-resultado: `result` (win/loss/push/void), `pnl`, `closing_odds`, `clv` |
| `bankroll_history` | trilha de auditoria do saldo; cada movimento tem `reason` e opcionalmente `bet_id` |
| `backtest_runs` | metadados + métricas de cada run; `params` JSONB; **`avg_clv` e `pct_positive_clv` são as métricas principais**, ROI/P&L secundárias |

## Convenções

- `Numeric` para dinheiro/odds/probabilidades (nunca float em coluna).
- Seleções: texto padronizado `HOME|DRAW|AWAY|OVER|UNDER|<player_id>`.
- Migrations via Alembic somente; upgrade E downgrade testados
  (`tests/integration/test_migrations.py`).
