# DOMAIN.md — glossário e fórmulas

Referência canônica dos conceitos. Se um termo aqui for usado errado no
código, o bug é silencioso e corrompe tudo — leia antes de mexer no núcleo.

## Conceitos

- **Odd decimal (`d`)** — retorno total por unidade apostada. Prob implícita
  bruta: `1/d`.
- **Vig / overround** — margem da casa. `Σ(1/d_i)` sobre as seleções de um
  mercado dá > 1; o excesso é o vig (~5% num 1X2 líquido, 15–30% em props).
- **De-vig** — remover a margem para obter a **probabilidade justa** do
  mercado:
  - **Multiplicativo (padrão):** `fair_prob_i = (1/d_i) / Σ(1/d_j)`
  - **Shin / power** (opções futuras, configuráveis): corrigem o viés
    favorito-azarão.
  - Sempre que possível, de-vig sobre a **linha da Pinnacle** (sharp book) —
    melhor estimativa disponível da "verdade" do mercado.
- **EV / edge** — valor esperado por unidade: `edge = p_modelo × d − 1`.
  Sinal (`value_bet`) só existe se `edge > min_edge` (config; 0.02–0.05).
- **Kelly** — fração ótima da banca: `f* = (p·d − 1) / (d − 1)`.
  Se `f* ≤ 0`, não aposte. Usamos **Kelly fracionário**:
  `stake = bankroll × kelly_multiplier × f*` com `kelly_multiplier` 0.25–0.5
  e teto `max_stake_pct` por aposta. Kelly cheio com `p` superestimado quebra
  a banca.
- **Closing line** — última odd disponível antes do kickoff. A closing da
  Pinnacle é o melhor preditor conhecido do resultado real.
- **CLV (Closing Line Value)** — a métrica-mãe:
  - **Preço (bruto):** `clv = taken_odds / closing_odds − 1`
  - **Probabilidade (de-vigado, preferível):** comparar a fair_prob da linha
    sharp no momento da aposta vs no fechamento. Menos ruidoso.
  - CLV médio positivo com amostra grande ⇒ evidência de edge real, muito
    antes de o P&L provar qualquer coisa. CLV negativo ⇒ lucro é sorte e vai
    reverter.
- **Sharp book** — casa com limites altos e clientes profissionais
  (Pinnacle); sua linha agrega informação e serve de referência.
- **Push / void** — aposta devolvida (ex.: handicap exato, jogo adiado).
  `pnl = 0`, não conta como win nem loss.

## Regras de leitura de resultados

1. CLV primeiro (`avg_clv`, `pct_positive_clv`), lucro depois (ROI, P&L,
   drawdown).
2. Backtest só vale out-of-sample; lucro de backtest é ferramenta de
   depuração, não prova.
3. Nunca usar informação do futuro: na decisão valem apenas dados com
   timestamp anterior ao kickoff.
