# ADR-0002 — Provedores: API-Football + The Odds API (+ football-data.co.uk p/ histórico)

**Data:** 2026-07-13 · **Status:** aceito

## Contexto

Fase 1 precisa de fixtures/resultados e de snapshots de odds com timestamp
incluindo uma referência sharp (Pinnacle). Verificação atual dos planos
(2026-07-13):

- **API-Football** (v3, `x-apisports-key`): free 100 req/dia; Pro US$19/mês
  7.500 req/dia. Todos os endpoints em todos os planos. **Limitação crítica:
  histórico de odds de só ~7 dias e roster de bookmakers sem Pinnacle
  confirmada** → não serve como fonte de odds.
- **The Odds API** (v4, `apiKey` query param): free 500 créditos/mês; custo =
  mercados × regiões por chamada. **Pinnacle confirmada** (key `pinnacle`,
  região `eu`); Brasileirão (`soccer_brazil_campeonato`) e EPL (`soccer_epl`)
  confirmados. Histórico de odds: apenas planos pagos.
- **football-data.co.uk**: CSVs grátis com closing 1X2 da Pinnacle
  (Brasileirão desde 2012; EPL com open+close, OU e AH). Sem API/tempo real.

## Decisão

1. **API-Football** para fixtures, resultados (e futuramente lineups/stats).
2. **The Odds API** para odds correntes (h2h + totals, região `eu`,
   Pinnacle incluída), viram `odds_snapshots` append-only.
3. **football-data.co.uk** como fonte de closing lines históricas para
   calibração/backtest (Fase 2/4) — sem custo.

## Consequências

- Free tier da The Odds API: 2 créditos/poll (2 mercados × 1 região) →
  polling default de 240 min (~360 créditos/mês), configurável. Closing line
  capturada com granularidade grosseira até haver plano pago — aceitável no
  MVP, documentado como limitação do CLV inicial.
- Ambos atrás de `FixtureProvider`/`OddsProvider`; troca de provedor não toca
  o núcleo.
- Upgrade de plano (The Odds API 20K/US$30) quando o paper trading exigir
  granularidade de closing melhor.
