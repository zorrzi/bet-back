# ADR-0005 — Histórico via football-data.co.uk, closing sintético e aliases de times

**Data:** 2026-07-13 · **Status:** aceito

## Contexto

A Fase 2 precisa de resultados históricos para calibrar o Dixon-Coles e de
closing lines para o backtest (Fase 4). O plano free da API-Football só vê
2022–2024 (ADR-0004) e o histórico da The Odds API é pago. Os CSVs gratuitos
de football-data.co.uk cobrem o Brasileirão desde **2012**, com resultados e
**closing 1X2 da Pinnacle** (colunas PSCH/PSCD/PSCA), atualizados durante a
temporada — inclusive 2026.

## Decisões

1. **Importador dedicado** (`POST /jobs/import/history`): ~5.500 partidas
   com placares + ~15.800 snapshots de closing da Pinnacle.
2. **Timestamps sintéticos de closing:** o CSV não informa quando a odd foi
   capturada; os snapshots importados recebem `captured_at = kickoff − 1min`
   e `is_closing = true`. **Regra de honestidade:** snapshots sintéticos só
   são anexados a partidas criadas pelo próprio importador (`fdcuk:`);
   partidas acompanhadas ao vivo recebem apenas o resultado — misturar
   closing sintético com odds capturadas de verdade corromperia o CLV.
3. **Deduplicação de partidas:** mesma dupla de times num intervalo de ±1
   dia = mesma partida real (relógios divergem entre fontes).
4. **Aliases canônicos de times** (`canonical_team_key` em
   `src/utils/text.py`): a primeira importação real órfã 7 times por
   divergência de grafia entre provedores (`Flamengo RJ`↔`Flamengo`,
   `Atletico-MG`↔`Atletico Mineiro`, `Vasco`↔`Vasco da Gama`,
   `Botafogo RJ`↔`Botafogo`, `Bragantino`↔`Bragantino-SP`,
   `Chapecoense-SC`↔`Chapecoense`, `Athletico-PR`↔`Atletico Paranaense`).
   Tabela curada, com o lado The Odds API como canônico; novos casos entram
   guiados pelos logs `event_unmatched`.
5. **Hora do CSV é UK-local, armazenada como UTC** — aproximação aceita
   para pesos de decaimento e cortes de treino; nunca usada em decisão ao
   vivo.

## Validação

Reimportação pós-aliases: 5.496 partidas, 0 times órfãos, 13/13 jogos
futuros previstos pelo modelo (antes: 5/13).
