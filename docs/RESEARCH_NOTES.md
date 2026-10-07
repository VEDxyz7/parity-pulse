# Research notes — Phase 0

Checked 2026-10-06. Research is a prior, not local validation. No model, backtest, baseline or agent was implemented.

## Cong et al., Tokenized Stocks

Lin William Cong, Wayne R. Landsman, Daniel Rabetti, Che Zhang, Wenqi Zhao, “Tokenized Stocks,” written December 1, 2025; SSRN 5937314, posted December 18, 2025, latest discoverable revision January 4, 2026. [SSRN record](https://papers.ssrn.com/sol3/Delivery.cfm/5937314.pdf?abstractid=5937314&mirid=1&type=2).

Question: price discovery and continuous fractional trading in equity tokens. Accessible abstract describes hundreds of stocks introduced from July 2025. Findings support session-aware tracking, off-hours divergence, weekend information incorporation and short-horizon reversal. They motivate local trust measurements.

Limit: complete manuscript/table access was not obtained; exact venues, sample dates, observations, regressions and the prompt's approximate 0.98/0.90 coefficients were not independently verified. Do not cite those coefficients as checked or use them as prediction multipliers. Current BNB issuer behavior needs local measurement.

Planned adaptation: normalization, session regimes, liquidity/persistence/news evidence, per-stock baselines and leak-free reopening evaluation. Not implemented: any strategy, profitability claim, fixed elasticity or universal issuer transfer.

## Luo et al., multi-agent portfolio paper

Yichen Luo, Yebo Feng, Jiahua Xu, Paolo Tasca, Yang Liu, “LLM-Powered Multi-Agent System for Automated Crypto Portfolio Management,” [arXiv 2501.00826v3](https://arxiv.org/html/2501.00826v3), June 16, 2026; version confirmed by [submission history](https://arxiv.org/abs/2501.00826).

Question: specialized agents combining market/news signals. V3 evaluates 15 L1-native crypto assets over 52 weeks of 2025. It compares hierarchical, collaborative and debate structures and several augmentation methods; market/news/trading agents use four-output rolling memory. Deterministic cosine retrieval offers historical grounding.

Limit: weekly crypto backtests, simplified costs and omitted slippage/impact cannot validate thin tokenized-stock routes. Model cutoff claims do not alone establish leakage-free data ingestion. Reported portfolio performance is not Parity Pulse performance.

Planned adaptation: six product roles, bounded hierarchical interpretation, structured evidence, memory, local analogues and ablation evaluation. Not implemented/copied: crypto portfolio rules, chain-of-thought storage, LLM risk authorization or paper returns.

## Additional current literature

[Tokenized stocks and tracking errors: Evidence on pricing efficiency](https://www.sciencedirect.com/science/article/pii/S1544612326007294), Finance Research Letters 106 (September 2026), article 110201, DOI 10.1016/j.frl.2026.110201. Publisher abstract associates tracking errors with volatility, uncertainty and weak integration. This is supplemental evidence for stock-specific controls. Full population/methodology unavailable; no coefficients adopted.

## Secondary overnight literature

The master prompt does not identify a particular thesis/dissertation. No uploaded reference is present. Identification remains unresolved; no arbitrary study is substituted. Weekday overnight blocking remains a product policy, not a newly verified universal research law.

## Evidence labels and evaluation

RESEARCH_PRIOR denotes literature rationale. LOCAL_EMPIRICAL_RESULT requires reproducible local data, sample counts, issuer/chain/regime coverage and out-of-sample evaluation. ENGINEERING_POLICY denotes safeguards such as 30 baseline/model episodes and three analogues. AGENT_INTERPRETATION denotes summaries.

Evaluate independent-price tracking, direction/magnitude error, confidence calibration, abstention quality, route cost and execution quality. News consistency is corroboration, not proof of causality. Historical decisions may use only available-time data. Changed future observations must not change earlier decisions.
