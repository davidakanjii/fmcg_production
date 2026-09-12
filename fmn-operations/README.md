# FMN Operations

Two local business apps for the FMN AI Engineer Internship assessment: **Supply Chain Outlook** and **Plant Health Outlook**. They share a Python backend, a browser interface and a runtime LLM integration.

## Start here

The supplied data, trained model artifacts, evaluation predictions and presentation are included. Open the apps after starting the server:

- Supply chain: http://127.0.0.1:8765/supply
- Manufacturing: http://127.0.0.1:8765/manufacturing
- Validation and data checks: http://127.0.0.1:8765/validation

**Delivery status:** local implementation with clear run instructions. No public deployment or remote GitHub/GitLab repository has been created. Runtime LLM requests are implemented, but a live provider call has not been verified because no API key was configured during development. The apps display an explicit unavailable state until configured. Mock transport tests do not establish live LLM quality.

## Problem understanding

The supply sponsor needs an actionable view of future sales pressure relative to stock and replenishment lead time. A forecast alone does not answer which item needs action. The app connects each forecast to available stock, expected lead-time sales and a reserve, then presents a prioritized list and item drilldown.

The plant sponsor needs advance warning with evidence and a trend. The app defines “soon” as **a recorded failure within the next 24 hours**. It ranks machines, shows sensor values and model contributions, and displays the same model's scores over the preceding 72 hours. It does not claim to identify a physical failure cause.

The assessment document supplied the functional requirements. It was not treated as authorization to email a submission, publish the datasets, create external accounts or claim completion of a live presentation.

## Setup and run

Use Python 3.12 or later. Development validation used Python 3.12.14, NumPy 2.3.5 and pandas 3.0.1. Only NumPy and pandas are required; the HTTP server, JSON client and tests use the Python standard library. The browser UI has no build step, CDN or JavaScript dependencies.

### Windows PowerShell

From this repository folder:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-lock.txt
Copy-Item .env.example .env
```

Edit `.env` locally. Set `OPENAI_API_KEY` to your API key and `OPENAI_MODEL` to a Responses-compatible model available to your account. The example uses `gpt-4.1-mini`; model access depends on the account. Keep the key out of source control and screenshots. Environment variables take precedence over `.env`.

```powershell
.\.venv\Scripts\python.exe train.py
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
.\.venv\Scripts\python.exe server.py
```

Training can be skipped for the first demo because the generated artifacts are included. Run it after replacing a dataset, then restart the server. Stop the server with Ctrl+C. Set `PORT` in `.env` if 8765 is occupied. The server intentionally binds only to localhost.

### macOS / Linux

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements-lock.txt
cp .env.example .env
# Edit .env locally to configure the API key and model.
.venv/bin/python train.py
.venv/bin/python -m unittest discover -s tests -v
.venv/bin/python server.py
```

### Verify the live AI integration

After configuring a key, run `python smoke_llm.py` with the same Python environment. It performs three real, billable provider calls: one SKU explanation, one machine explanation and one free-text fleet answer. It checks returned references and prints the generated answers for manual review. Alternatively use the buttons in the two apps. Validate that the wording agrees with the visible numbers, not just that the request succeeds.

API reference: [OpenAI Responses API](https://developers.openai.com/api/reference/resources/responses/methods/create). Calls go to `https://api.openai.com/v1/responses` with `store: false`. This flag does not by itself establish a provider-wide zero-retention agreement. The relevant measurements and question are sent to OpenAI only when the AI feature is requested (automatically when a flagged item is opened with a configured key, or through a button).

## How a business user operates the apps

### Supply chain

1. Read the snapshot date: the data ends **29 June 2026**. Forecasts cover 30 June–29 July, not today's live operations.
2. Filter by category or status, or search an exact SKU ID.
3. Select an item to inspect stock, lead-time sales, the 30-day forecast and sales history. Missing observed sales appear as chart gaps.
4. Review the suggested replenishment quantity and first projected stockout date under the **no future receipts** assumption. Quantities are estimates, not purchase orders.
5. Generate the runtime AI explanation or ask a free-text question. “Why is SKU-1004 flagged?” should be answered by noting that it is actually **Healthy** in this snapshot.
6. Export the current full snapshot as CSV. Table filters do not restrict the export.

The latest snapshot has **13 shortage flags, 2 reserve-driven reorder flags and 13 healthy SKUs**. No SKU meets the chosen excess-stock rule in this snapshot. That is a result of the stated policy, not an omitted status implementation.

### Manufacturing

1. The latest snapshot ends **30 April 2026 at 23:00**. No machine exceeds the locked 0.47 threshold at that timestamp.
2. Use **Historical replay** to inspect 13 April 00:00 or 24 April 12:00. These are illustrative past operational states, selected to demonstrate drilldowns, not separate validation samples. Future readings do not enter replay features or trends. Replay views contain only machines already commissioned.
3. Select a machine, inspect its latest readings and 72-hour score trend, then read the feature contributions. The dashed line marks the action threshold.
4. Open a flagged machine to generate an explanation automatically when AI is configured. The explanation, Q&A and CSV export use the selected replay timestamp consistently.
5. Switch back to the latest snapshot to inspect new machines MCH-300 and MCH-301, each with 72 hours of history.

A “Monitor” status means below this model's action threshold. It is not a guarantee that a machine will not fail. Suggested inspections require plant judgment.

## Approach and architecture

`CSV files -> schema checks / cleaning -> time-based model evaluation -> JSON model and evidence artifacts -> local HTTP API -> browser UI`

AI follows a separate path: `selected ID or free-text question -> server-side evidence retrieval -> runtime Responses API call -> JSON and source-ID checks -> answer with evidence references`.

The model computes the flag and the quantities. The LLM explains the recorded evidence; it does not calculate the operational risk score, select an alert threshold or operate equipment.

| File or directory | Responsibility |
| --- | --- |
| `data/` | Unmodified supplied CSVs |
| `src/data.py` | Schema, duplicate, category and temporal-grid checks |
| `src/supply.py` | Forecast candidates, rolling backtests, cold start, inventory policy |
| `src/manufacturing.py` | Causal features, future-event labels, logistic fit, evaluation, score contributions |
| `src/llm.py` | Evidence retrieval, prompt, real API call, response validation, in-memory cache |
| `train.py` | Rebuild models, snapshots and prediction-level evaluations |
| `server.py` | Local serving, evidence APIs, CSV export and AI endpoints |
| `web/` | Responsive HTML/CSS/JavaScript apps |
| `tests/` | Model, retrieval, provider-contract and HTTP checks |
| `artifacts/` | Models, snapshots, source hashes and backtest CSVs |
| `presentation/` | Seven-slide presentation and actual demo screenshots |

## Data quality

| Check | Supply | Manufacturing |
| --- | ---: | ---: |
| Raw rows | 4,551 | 43,354 |
| Exact duplicates removed | 15 | 10 |
| Clean rows | 4,536 | 43,344 |
| Entities | 28 SKUs | 17 machines |
| Missing sales / temperature | 90 | 648 |
| Missing stock / vibration | 46 | 432 |

Supply category labels normalize from 10 capitalization variants to 5 categories. The inputs contain no conflicting entity/timestamp keys after exact deduplication, and no gaps in each entity's daily/hourly grid. The loader rejects conflicting keys, invalid labels, infinities, negative stock/sales/vibration and irregular grids rather than guessing how to repair them. SHA-256 hashes record the exact source bytes in `artifacts/dashboard.json`.

Missing sales remain missing for scoring. Historical sales summaries ignore missing values. A missing final stock is reconstructed only if an earlier observed stock and every subsequent receipt and sale are known. Otherwise it becomes “Check stock.” Sensor features forward-fill at most three hours within a machine, then use medians fitted on training data. Missingness indicators preserve evidence of absent sensors. No backward fill is used.

## Supply model selection and validation

Three small-data candidates compete on tuning WAPE:

- **Mean28:** average of the preceding 28 calendar days of observed sales.
- **Seasonal7:** repeat the previous week's weekday values, with a historical-mean fallback for missing values.
- **Weekday shrinkage:** estimate weekday effects from the preceding 56 days, shrink each weekday toward the overall mean with three pseudo-observations, then scale by the most recent 28-day level.

The selected method is **weekday shrinkage**. This captures weekly patterns without fitting a large model to six months of sales. Trend, promotions and price effects are not identifiable from the supplied columns, so they are not invented.

Tuning origins are **1, 15 and 29 April**. Held-out rolling origins are **13 and 27 May, and 10 June**. Each origin predicts the next 14 days. Later test origins may use sales that have become observed since earlier origins, as a deployed rolling forecaster would. Model choice and residual-band calibration use only the earlier tuning results. Test forecasts cover 14 May–24 June, with 1,028 nonmissing SKU-day targets.

| Model | Tuning WAPE | Test WAPE | Test MAE (units/day) |
| --- | ---: | ---: | ---: |
| Mean28 | 19.97% | 19.80% | 59.55 |
| Seasonal7 | 24.28% | 24.10% | 72.49 |
| **Weekday shrinkage** | **18.38%** | **17.58%** | **52.87** |

WAPE = sum of absolute prediction errors / sum of observed sales. MAE = average absolute error per observed SKU-day. The selected model's test signed bias is −0.07%. WAPE weights high-volume items more strongly, so per-SKU metrics are also included in the JSON artifact.

**Cold start:** fewer than 28 observed days uses `w * item mean + (1-w) * peer median`, where `w=n/(n+14)`. Peers are same-category SKUs, excluding the item, using only dates already observed. The three actual launches each have 12 days of data. A simulation truncating established SKU histories to 12 days gives **31.19% test WAPE**. This weaker performance makes the limitation visible; it is not an estimate of launch-specific accuracy. New launches have no post-snapshot outcome data.

**Bands:** each established SKU's tuning 90th-percentile absolute residual defines a symmetric daily band, clipped at zero. Test daily coverage is **87.94%**. This is an empirical daily range, not a calibrated multi-day stockout probability. New-SKU bands use a deliberately broad heuristic of 80% of forecast daily sales. The UI's 30-day extension is exploratory; rigorous backtesting here covers 14-day horizons only.

### Inventory policy

Let `D_L` be expected sales over lead time L, `q` the residual band width, and `S` the latest usable stock.

- Reserve = `q * sqrt(L)`, an explicit heuristic, not a proven service-level formula.
- Shortage: `S < D_L`.
- Reorder soon: `D_L <= S < D_L + reserve`.
- Excess stock: no shortage/reorder condition, and `S / mean forecast > L + 30` days of cover.
- Suggested replenishment = `max(0, D_L + reserve - S)`.
- Projected stock = `S - cumulative forecast sales`. The first negative projection identifies an expected stockout under the no-receipts scenario. Zero current stock remains visible as an immediate problem.

Open purchase orders, costs, pack sizes, lost sales, service targets and variable lead times are absent. These rules require sponsor review before operational use. Observed sales can be censored by stockouts; the app does not equate them with unconstrained demand.

## Manufacturing model selection and validation

The label is any recorded failure during hours **t+1 through t+24**, excluding a failure at t. The final 24 hours of each machine have unknown full-window outcomes and are censored. Current failure rows are excluded from training/scoring metrics. The UI can still identify a failure recorded at a replay timestamp.

The model is L2-regularized logistic regression, fitted with a compact NumPy Newton/IRLS optimizer and backtracking. Features: temperature, vibration, hours since maintenance, six-hour means, six-hour changes and two missingness flags. Features use only current/past readings. Entity IDs are not predictors, allowing the shared model to score newly commissioned machines. Training-only medians, means and scales are serialized with coefficients.

With only **17 independent failures**, a deep model would add capacity without enough event evidence. An interpretable fleet model and a maintenance-age-only logistic baseline provide a defensible comparison. Class weighting is not used. The threshold provides the recall/precision tradeoff.

| Split | Eligible timestamps | Purpose |
| --- | --- | --- |
| Train | 1 January–27 February 23:00 | Fit preprocessing and coefficients |
| Validation | 1 March–30 March 23:00 | Select L2 penalty and F2 threshold |
| Test | 1 April–29 April 23:00 | Locked held-out evaluation |

The 24-hour purges before March and April prevent future-event labels crossing split boundaries. Candidate penalties 1, 10 and 100 are compared with the maintenance-only baseline by validation **average precision** (stepwise precision-recall area). Penalty 100 wins at 0.1152 validation AP. The threshold 0.47 maximizes validation F2 over a fixed grid plus validation-score quantiles. F2 places more weight on recall. The threshold and model remain frozen for testing, latest snapshots and replay; the model is not silently retrained on the test labels.

| Held-out metric | Sensor model | Maintenance-only baseline |
| --- | ---: | ---: |
| Average precision | 0.3095 | 0.1695 |
| Hourly precision | 21.39% | 5.65% |
| Hourly recall | 45.74% | 48.94% |
| F2 | 0.3726 | 0.1933 |
| False positive hours | 316 | 1,536 |

Test set: 10,529 eligible hours, 188 positive hours, 1.79% prevalence. Each model uses its own validation-selected threshold. Hourly examples overlap and are not independent events.

The selected model detects **4 of 7 failures with a complete 24-hour warning window in the evaluated test rows**. The 30 April MCH-203 failure has only a partial evaluable warning window after tail censoring and is excluded from this event denominator. First warning lead times for detected complete-window events are 24, 9, 24 and 24 hours. There are 16 contiguous alert episodes, and 0.72 false alert hours per evaluated machine-day. False alert hours are not the same as maintenance work orders or independent false alarms.

**Calibration is poor:** test Brier score is 0.0329, worse than an always-zero score's 0.0179 on this rare-event test set. The model has useful ranking signal but its output must not be advertised as a calibrated failure probability. More events, calibration on a separate temporal sample, event-level confidence intervals and cost-aware threshold selection are needed. New machines supply only 96 eligible test hours and zero positive events, so their recall is not estimable. They are explicitly marked as limited-history cases.

The drilldown reports signed standardized-feature contributions to log odds. They explain the model relative to training means. Correlated temperature/vibration features may divide contribution, and none proves a causal failure mechanism.

## Runtime LLM explanations and grounded Q&A

Both apps have a runtime explanation button and a free-text question box. A configured flagged-item drilldown automatically requests an explanation. There are no prewritten explanations masquerading as LLM results.

Exact IDs retrieve their full evidence records. Fleet questions retrieve all 28 SKU or 17 latest machine summaries (15 in earlier replays), avoiding an arbitrary top-k cutoff that could hide an item. Context also includes the dataset timestamp, validation evidence and operational assumptions. For this small fleet, deterministic retrieval is simpler and more complete than a vector database. The model can answer comparisons and numerical “why” questions from the supplied context, but cannot query live systems or fetch external facts.

The prompt instructs the model to treat question/record strings as data, cite entity IDs, use actual measurements, reject unsupported claims and state uncertainty. Structured output requires an answer and source IDs. The server verifies that cited IDs exist in retrieved evidence and that IDs mentioned in prose are cited. This validates references, **not every numerical or semantic claim**. Manual grounding review is still required. Prompt injection remains a residual risk; no tools or executable commands are given to the LLM.

Requests have a 45-second timeout, a 1,200 output-token cap, bounded question/body length and two concurrent provider calls maximum. Successful identical responses are cached in memory for 15 minutes. Errors produce a visible unavailable state. Responses are inserted as plain text to avoid model-generated HTML execution. Keys stay server-side, secret files are not served, and AI POST requests require a session CSRF token. The app has no external action tools.

## Validation and reproducibility

Run `python -m unittest discover -s tests -v`. Automated checks cover:

- Input cleaning, conflicting keys, future-input rejection and missing target exclusion.
- Stock reconstruction and lead-time/replenishment arithmetic.
- Future-event labels, censoring, causal sensor features and temporal split purges.
- Logistic numerical behavior, exact additive contributions and AP tie handling.
- Exact-ID and complete-fleet retrieval, unknown IDs, absent API keys and invalid references.
- Mocked provider request format, provider errors and successful-response cache behavior.
- HTTP pages, CSV export, secret-file denial and CSRF enforcement.

Browser checks cover both apps, filtering, short-history details, replay state, validation view, Q&A error handling and a mobile viewport. Live provider success remains unverified until the key is configured. Actual generated AI answers should be reviewed with `smoke_llm.py` before presenting.

`artifacts/supply_backtest.csv` contains forecasts for all candidate methods. `artifacts/machine_backtest.csv` contains held-out scores and labels. `artifacts/dashboard.json` contains evaluation summaries, per-SKU metrics, source hashes and the served evidence. Retraining on unchanged input is deterministic apart from the artifact generation timestamp.

## Presentation and demo sequence

Use `presentation/FMN_Operations_Assessment.pptx` (7 slides). Screenshots show the implemented app, not an imagined interface.

Suggested demo: open supply chain, inspect SKU-1000 and new SKU-2000, explain the no-receipts assumption, then ask why SKU-1004 is flagged to demonstrate correcting a false premise. Open manufacturing, select the 13 April replay and inspect MCH-207, then switch to the latest snapshot to discuss the new machines. Finish on Model & data review and acknowledge missed failures and calibration limits.

For code walkthrough, start with `train.py`, follow supply forecasts or manufacturing labels, then open `src/llm.py` to show the evidence payload and actual runtime HTTP call. Explain why preprocessing is fitted only on training data and why the last 24 hours are not labeled as non-failures.

## Limitations and next steps

This is a local assessment prototype. It does not connect to live ERP/plant systems, authenticate multiple users, run scheduled ingestion, place orders or create maintenance jobs. The standard-library server is intended for a local demo. It should not be exposed publicly without a production server, authentication, TLS, access controls and a provider-budget policy.

The next modeling work is more event data and temporal/held-out-machine validation, calibration, uncertainty at the event level, and business cost-based thresholds. Supply needs purchase orders, pack sizes, stockout-adjusted demand, promotion/price variables and agreed service levels. Larger datasets would justify more advanced models only if they improve temporal holdouts and operational usefulness.

Before submission, configure and verify live AI, rehearse the code walkthrough, create the remote repository under your account, and provide its actual URL with the slide deck and local run instructions (or a secured deployed URL). No email has been sent and no submission URL is fabricated here.
