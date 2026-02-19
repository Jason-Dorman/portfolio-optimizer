# Data Model — Formulas & Equations

## 4.1 Returns from Prices

**Simple return:**

$$r_{i,t} = \frac{P_{i,t}}{P_{i,t-1}} - 1$$

**Log return:**

$$r_{i,t} = \ln\left(\frac{P_{i,t}}{P_{i,t-1}}\right)$$

---

## 4.2 Annualization

Let $m$ = periods per year (252 for daily, 52 for weekly, 12 for monthly).

**Mean:**
$$\mu_i = m \cdot \bar{r}_i$$

**Volatility:**
$$\sigma_i = \sqrt{m} \cdot s(r_i)$$

**Covariance matrix:**
$$\Sigma = m \cdot \text{Cov}(r)$$

---

## 4.3 Correlation / Covariance Relationship

$$\rho_{ij} = \frac{\Sigma_{ij}}{\sigma_i \sigma_j}, \quad \Sigma_{ij} = \rho_{ij} \sigma_i \sigma_j$$

---

## 4.4 Portfolio Moments

Given weight vector $w$:

**Expected return:**
$$\mu_p = w^\top \mu$$

**Variance:**
$$\sigma_p^2 = w^\top \Sigma w$$

**Volatility:**
$$\sigma_p = \sqrt{w^\top \Sigma w}$$

**Sharpe ratio:**
$$S = \frac{\mu_p - r_f}{\sigma_p}$$

---

## 4.5 Optimization Problems

### Minimum Variance Portfolio (MVP)

$$\min_w \; w^\top \Sigma w \quad \text{s.t.} \; \mathbf{1}^\top w = 1$$

Plus optional constraints (see Section 4.6).

### Efficient Frontier Point (target return $R^*$)

$$\min_w \; w^\top \Sigma w \quad \text{s.t.} \; w^\top \mu = R^*, \; \mathbf{1}^\top w = 1$$

### Tangency Portfolio (Max Sharpe)

$$\max_w \frac{w^\top \mu - r_f}{\sqrt{w^\top \Sigma w}} \quad \text{s.t.} \; \mathbf{1}^\top w = 1$$

### Feasibility Checks

**Long-only frontier point:**
$$\mu_p \in [\min(\mu_i), \max(\mu_i)]$$

If $R^* > \max(\mu_i)$, no long-only solution exists. System returns INFEASIBLE with plain-language reason.

**Tangency portfolio:**

If $\max(\mu_i) \leq r_f$ (all excess returns non-positive), no meaningful tangency solution exists. System returns INFEASIBLE with reason: "No asset has expected return exceeding the risk-free rate; tangency portfolio undefined."

---

## 4.6 Constraints

| Constraint | Expression |
|---|---|
| Full investment | $\mathbf{1}^\top w = 1$ |
| Long-only | $w \geq 0$ |
| Per-asset bounds | $w_{\min} \leq w \leq w_{\max}$ |
| Leverage cap | $\sum \|w_i\| \leq L$ |
| Concentration cap | $\max(\|w_i\|) \leq c$ |
| Turnover cap | $\sum \|w_i - w_{i,\text{prev}}\| \leq T$ |

Where $w_{\text{prev}}$ comes from the current holdings snapshot if provided, otherwise from the previous optimization run. If neither exists, the turnover constraint is inapplicable and ignored.

---

## 4.7 Diversification & Risk Decomposition

Let $g = \Sigma w$.

**Marginal contribution to risk (MCR):**
$$\text{MCR}_i = \frac{g_i}{\sigma_p}$$

**Component contribution to risk (CRC):**
$$\text{CRC}_i = w_i \cdot \text{MCR}_i$$

**Percent risk contribution (PRC):**
$$\text{PRC}_i = \frac{\text{CRC}_i}{\sigma_p}$$

Note: $\sum_i \text{CRC}_i = \sigma_p$ and $\sum_i \text{PRC}_i = 1$.

**HHI concentration:**
$$\text{HHI} = \sum_i w_i^2$$

**Effective number of assets:**
$$N_\text{eff} = \frac{1}{\sum_i w_i^2} = \frac{1}{\text{HHI}}$$

---

## 4.8 Tail Risk & Drawdown

Using realized portfolio returns $r_{p,t} = w^\top r_t$ (or from backtest):

**Wealth index:**
$$V_t = V_{t-1}(1 + r_{p,t}), \quad V_0 = 1$$

**Drawdown:**
$$DD_t = \frac{V_t}{\max_{u \leq t} V_u} - 1$$

**Maximum drawdown:**
$$\text{MDD} = \min_t DD_t$$

**Historical VaR** at confidence level $\alpha$ (e.g., 0.05 for 95%):

Sort realized returns $r_{p,t}$. Then:
$$\text{VaR}_\alpha = -\text{Quantile}_\alpha(r_{p,t})$$

**Historical CVaR (Expected Shortfall):**

Let $q_\alpha = \text{Quantile}_\alpha(r_{p,t})$. Then:
$$\text{CVaR}_\alpha = -\mathbb{E}[r_{p,t} \mid r_{p,t} \leq q_\alpha]$$

Both computed at $\alpha \in \{0.05, 0.01\}$ (95% and 99% confidence).

---

## 4.9 Asset Screening Scores

The screening module scores each candidate asset $c$ against a reference portfolio $R$ (either current holdings or seed universe).

Let:
- $\mathcal{R}$ = set of assets in the reference portfolio with weights $w_r$
- $\sigma_R$ = current portfolio volatility $= \sqrt{w_R^\top \Sigma_R w_R}$
- $\delta$ = nominal add weight (default 0.05)

### Signal 1 — Average Pairwise Correlation

$$\text{AvgCorr}(c) = \frac{1}{|\mathcal{R}|} \sum_{r \in \mathcal{R}} \rho_{c,r}$$

Lower is better. Normalized to $[0,1]$ using inverted min-max scaling across all candidates:

$$\widetilde{\text{AvgCorr}}(c) = 1 - \frac{\text{AvgCorr}(c) - \min_k \text{AvgCorr}(k)}{\max_k \text{AvgCorr}(k) - \min_k \text{AvgCorr}(k)}$$

After normalization: 0 = most correlated candidate, 1 = least correlated candidate.

### Signal 2 — Marginal Volatility Reduction

Construct a pro-forma portfolio: scale down reference weights by $(1 - \delta)$ and add candidate at weight $\delta$.

$$w_\text{pro} = (1-\delta) \cdot w_R \cup \{\delta \text{ for } c\}$$

$$\text{MVR}(c) = \sigma_R - \sqrt{w_\text{pro}^\top \Sigma_\text{pro} \, w_\text{pro}}$$

Higher is better (larger reduction = more beneficial). Normalized to $[0,1]$ via standard min-max scaling:

$$\widetilde{\text{MVR}}(c) = \frac{\text{MVR}(c) - \min_k \text{MVR}(k)}{\max_k \text{MVR}(k) - \min_k \text{MVR}(k)}$$

### Signal 3 — Sector / Asset Class Gap Score

Define the set of asset classes already represented in $\mathcal{R}$ with weight $\geq \theta$ (default $\theta = 0.02$):

$$\mathcal{A}_R = \{a \mid \sum_{r \in \mathcal{R}, \text{class}(r)=a} w_r \geq \theta\}$$

Sector is defined as the GICS sector (11 sectors: Energy, Materials, Industrials, Consumer Discretionary, Consumer Staples, Health Care, Financials, Information Technology, Communication Services, Utilities, Real Estate). For non-equity assets, sector is null.

$$\text{GapScore}(c) = \begin{cases} 1 & \text{if class}(c) \notin \mathcal{A}_R \\ 0.5 & \text{if class}(c) \in \mathcal{A}_R \text{ but sector}(c) \notin \text{sectors of } \mathcal{R} \\ 0 & \text{otherwise} \end{cases}$$

Gap score is already bounded to $[0,1]$ and requires no further normalization.

### Signal 4 — HHI Reduction

$$\text{HHI}_\text{pro}(c) = \sum_i w_{\text{pro},i}^2$$

$$\text{HHIRed}(c) = \text{HHI}_R - \text{HHI}_\text{pro}(c)$$

Higher is better. Normalized to $[0,1]$ via standard min-max scaling:

$$\widetilde{\text{HHIRed}}(c) = \frac{\text{HHIRed}(c) - \min_k \text{HHIRed}(k)}{\max_k \text{HHIRed}(k) - \min_k \text{HHIRed}(k)}$$

### Composite Score

$$\text{Score}(c) = \lambda_1 \cdot \widetilde{\text{AvgCorr}}(c) + \lambda_2 \cdot \widetilde{\text{MVR}}(c) + \lambda_3 \cdot \text{GapScore}(c) + \lambda_4 \cdot \widetilde{\text{HHIRed}}(c)$$

Where $\lambda_1 + \lambda_2 + \lambda_3 + \lambda_4 = 1$.

Default weights: $\lambda_1 = 0.40$, $\lambda_2 = 0.30$, $\lambda_3 = 0.15$, $\lambda_4 = 0.15$.

Scores are stored per candidate per screening run. Rankings are ordinal (rank 1 = highest composite score).

---

## 4.10 Rebalancing Simulation

On rebalancing dates:

**New target weights** $w^*$ computed from optimizer.

**Turnover:**
$$\text{TO} = \sum_i |w_i^* - w_{i,\text{prev}}|$$

**Transaction cost:**
$$\text{cost} = c \cdot \text{TO}$$

where $c$ is cost per unit turnover (expressed in decimal; e.g., 0.001 = 10 bps).

**Net return:**
$$r_{p,t}^\text{net} = r_{p,t} - \text{cost}$$

---

## 4.11 Drift Detection

After optimization produces target weights $w^*$, drift is computed at a later date using updated prices.

> **Note:** Drift detection always uses simple returns for wealth compounding, regardless of the return type used in estimation. This ensures correct multiplicative wealth accumulation.

**Implied current weight** for asset $i$ at check date:

$$w_{i,t} = \frac{w_i^* \cdot \prod_{\tau} (1 + r_{i,\tau})}{\sum_j w_j^* \cdot \prod_{\tau} (1 + r_{j,\tau})}$$

Where the product runs over periods since the last rebalance, and $r_{i,\tau}$ are simple returns.

**Absolute drift:**
$$\Delta_i = |w_{i,t} - w_i^*|$$

**Breach condition:**
$$\text{breach}_i = \Delta_i > \theta_\text{drift}$$

Default threshold $\theta_\text{drift} = 0.05$ (5 percentage points).

**Portfolio-level drift trigger (threshold rebalancing):**
$$\text{rebalance} = \max_i \Delta_i > \theta_\text{drift}$$

---

## 4.12 Benchmark Comparison Metrics

Let $r_p$ and $r_b$ be the vectors of portfolio and benchmark period returns over the backtest.

**Active return:**
$$\alpha_t = r_{p,t} - r_{b,t}$$

**Annualized tracking error:**
$$\text{TE} = \sqrt{m} \cdot s(\alpha_t)$$

**Information ratio:**
$$\text{IR} = \frac{\bar{\alpha} \cdot m}{\text{TE}}$$