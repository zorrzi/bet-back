# ADR-0004 — Fixtures e resultados via The Odds API (plano free da API-Football não vê temporadas atuais)

**Data:** 2026-07-13 · **Status:** aceito · **Revisa parcialmente:** ADR-0002/0003

## Contexto

Na primeira ingestão real descobrimos que o **plano Free da API-Football
restringe o acesso às temporadas 2022–2024** (`errors.plan: "Free plans do
not have access to this season, try from 2022 to 2024"`). A temporada 2026
do Brasileirão — alvo da Fase 1 — fica inacessível sem plano pago
(US$ 19/mês).

## Decisão

Dentro dos planos gratuitos, a **The Odds API passa a ser a fonte primária
de partidas e resultados da temporada corrente**:

1. **Partidas futuras**: quando um evento de odds não resolve para partida
   existente e `ODDS_AUTOCREATE_MATCHES=true` (default), a partida é criada
   a partir do próprio evento (liga `toa:<sport_key>`, times
   `toa:<nome normalizado>`, partida `toa:<event_id>`).
2. **Resultados**: novo job `POST /jobs/ingest/scores` usa o endpoint
   `/scores` (2 créditos/chamada) e aplica placares só de eventos
   `completed`, resolvendo por `provider_id` primeiro, nomes+kickoff como
   fallback.
3. **API-Football permanece** para histórico 2022–2024 (calibração do
   Dixon-Coles na Fase 2) e volta a ser fonte primária de fixtures se houver
   upgrade de plano (desligar autocreate nesse caso).

## Racional

- O evento de odds JÁ é a partida que interessa — só apostamos onde há
  mercado precificado.
- Não viola o ADR-0003 (nunca adivinhar associação): criar partida do
  próprio evento não é adivinhar — a resolução por id do evento é exata.
- Orçamento free (500 créditos/mês): odds 2cr a cada 6h (~240/mês) + scores
  2cr a cada 12h (~120/mês) ≈ 360/mês, com folga para disparos manuais.

## Consequências e riscos

- Times criados com namespace `toa:` não têm vínculo com IDs da
  API-Football; se/quando o plano pago entrar, será preciso uma migração de
  reconciliação (nome normalizado como ponte). Registrado como dívida
  consciente.
- Sem lineups/estatísticas detalhadas da temporada corrente até haver plano
  pago — irrelevante até a Fase 7 (props).
- `matches_autocreated` é reportado pelo job e logado para monitoramento.

## Validação

Primeira captura real (2026-07-13 22:35 UTC): 13 eventos → 13 partidas
autocriadas, 979 snapshots, 23 casas (Pinnacle marcada sharp), mercados 1X2
e OU (2.0–3.0).
