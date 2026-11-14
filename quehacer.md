# What's Missing to Make PIER a True Hackathon Winner

The PIER project is already exceptionally well-structured and implements the full Spec 3 (Extreme Weather) with all business rules BR-1 through BR-12. It has 37 passing tests, cached demo data, a working Streamlit UI, and clear documentation. However, to distinguish it as a **true hackathon winner** (not just a "complete submission"), we need to move beyond "spec-compliant" into "exceptional user experience & impact."

Below are the highest-leverage gaps, ordered by impact on the evaluation criteria (Influence, Creativity, Validity, Relevance, Presentation).

---

## 1. **30-Second Demo Video That Actually Wins**

The notes.md requirement is a **make-or-break** element. Many submissions have great code but forget to package a compelling demo video.

**What's missing:** A tightly scripted, visually polished 30s that *shows*, not tells, the problem/solution.

**The fix — shoot and edit the video now:**

| Beat (≈5s each) | Visual + Script | Why it wins points |
|---|---|---|
| **1. The problem** | Satellite imagery + farmer field overlay; text overlay: "When flood/drought destroys the planned crop..." | Establishes relevance to the Space Apps challenge |
| **2. The detection** | CLI or Streamlit output: "Event detected: flood, confidence 85%" | Shows the NASA data integration (Influence) |
| **3. The GDD window** | Graph: accumulated GDD vs. remaining window to frost | Demonstrates technical depth (Validity) |
| **4. The recommendation** | Side-by-side: 2 rescue crops with plant-by dates ranked latest-first | Shows the core value proposition |
| **5. The fallback** | Text: "\"The season's cash crop is lost; this recommendation is soil protection only\"" + cover crop suggestion | Highlights the BR-5 safety net (Creativity/Relevance) |

**Production tips:**
- Use **OBS Studio** or **QuickTime** screen recording at 1080p.
- Add **English captions** (the video is evaluated with CC).
- Keep total length ≤30s (trim precisely).
- Upload to a shared link (Google Drive/YouTube unlisted) and embed in the README.
- If using **Hyperframes AI**, note it in the AI usage declaration — but a hand-edited video often scores higher for "Presentation."

**Deliverable:** `demo/pier_demo.mp4` (or `.mov`) ≤30s, English speech, with captions.

---

## 2. **SMS / USSD Fallback for Low-Connectivity Farmers**

The spec mentions "Mobile PWA + SMS fallback" in the post-MVP roadmap (Stage 14), but **no SMS implementation exists yet**. This is a **high-impact differentiator**: hackathon judges love solutions that reach the most vulnerable farmers who have smartphones but poor data connectivity (or no internet at all).

**The fix — add a minimal SMS/USSD gateway:**

- **Input:** Farmer sends SMS with `lat,lon,date` (e.g., `41.8,-93.6,2025-06-15`).
- **Output:** Concise reply: `"Flood detected. Rescue: Cereal rye. Plant by 2025-07-15. Protects soil. Cash crop lost."` (≤160 chars for one SMS).
- **Integration:** Reuse the existing `run_pier()` function; format the output for SMS length limits.
- **Tech:** Twilio API (or free alternative like **FreeTUNA** or **Clickatell**). If no account, simulate with a mock gateway that reads from a Twilio-like API config.
- **Documentation:** Add `piper_agent/ui/sms_gateway.py` with a `handle_sms(message: str) -> str` function.

**Why this wins:** Extends the solution's reach beyond tech-savvy users, directly addresses the "declining soil health" pressure for smallholder farmers, and demonstrates real-world impact — a major evaluation criterion.

**Deliverable:** `sms_gateway.py` with a working mock/Twilio integration (config in `.env.example`).

---

## 3. **Multi-Hemisphere Season Support**

The current demo data and logic appear **Northern-hemisphere–centric** (US Midwest, Horn of Africa at lat ~6.9). The spec's BR-3 GDD model and frost-date logic assume Northern-hemisphere season timing. A hackathon winner should explicitly handle **Southern-hemisphere** growing seasons (e.g., Brazil, Australia, Southern Africa).

**The fix — hemisphere-aware GDD and frost dates:**

- Detect hemisphere from the sign of `lat`: `lat > 0` → Northern, `lat < 0` → Southern.
- For Southern hemisphere: invert season start/frost date (e.g., frost in March/April instead of October/November).
- Adjust `season_start` and `climatological_frost_date` in the baselines accordingly.
- Add a `--hemisphere` CLI flag (default `auto` from lat sign) or a toggle in the Streamlit sidebar.

**Code locations to modify:**
- `piper_agent/tools/fetch_power_gdd.py` — adjust GDD accumulation window start/end based on hemisphere.
- `piper_agent/data/baselines/` — add Southern-hemisphere baseline files or a computation function.
- `piper_agent/config.py` — add `HEMISPHERE_DEFAULT = "auto"` and frost-month mappings.

**Why this wins:** Shows depth of thinking about global farmer applicability. Explicitly addressing edge cases is highly valued in the "Validity" and "Relevance" categories.

**Deliverable:** Hemisphere-aware `fetch_power_gdd` and baseline loading; `--hemisphere` CLI option.

---

## 4. **Live NASA Data Path (With Prominent Cache Badge)**

The project currently operates in **cache-only mode** to avoid Earthdata authentication requirements. While the risk register documents this, a true winner ** transparently bridges both modes** and makes the data source visible to the user.

**The fix — dual-mode with real-time badge:**

- Keep the default `--demo True` (cache-only) for the hackathon demo.
- Add `--no-demo` flag that attempts live `imergpy`/`POWER` calls and gracefully handles auth failures (falls back to cache with a prominent warning).
- Add a **UI badge** that clearly states:
  - `"Demo mode — data cached (no live Earthdata call)"` when demo mode is on.
  - `"Live NASA data (production path)"` when `--no-demo` is used and live data is successfully fetched.
- Log when the fallback occurs (e.g., `"Earthdata auth unavailable — serving cached data"`).

**Why this wins:** Transparency + the ability to say "this also works with live data" is a strong points-talk during judging. It shows you've considered production readiness without compromising the demo.

**Deliverable:** Modified `agent.py` `run_pier()` with `--demo`/`--no-demo`; updated `streamlit_app.py` cache badge; `.env.example` notes.

---

## 5. **OpenET ETa + SMAP Soil Moisture Integration**

The spec's data-needs table and Post-MVP roadmap include **OpenET ETa** (actual evapotranspiration) and **SMAP soil moisture**, but **neither is implemented yet**. These are high-value layers that add **physical precision** to the rescue-crop filtering.

**The fix — add two optional data layers:**

- **OpenET ETa:** Fetch actual evapotranspiration for the field location/date. Useful for BR-11 dollar savings (how much water was actually lost) and water-shortage screening.
- **SMAP soil moisture:** Root-zone soil moisture percent. Useful for drought severity assessment and distinguishing flood vs. drought when IMERG data is ambiguous.

**Implementation path (lightweight, cache-first):**
- Add `piper_agent/data/fetch_openet.py` with `fetch_openet_eta(lat, lon, date_range) -> DataFrame[date, eta_mm]`.
- Add `piper_agent/data/fetch_smap.py` with `fetch_smap_moisture(lat, lon, date_range) -> DataFrame[date, soil_moisture_vol_pct]`.
- Both use a **cache-first, API-second** pattern: read from `data/cache/openet/` and `data/cache/smap/` if present; otherwise show a "synthetic/estimated" badge.
- Integrate into `filter_rescue_crops`: e.g., if SMAP moisture < 20th percentile, weight drought-tolerance crops higher.

**Why this wins:** Moves beyond "climatology-only" to real-time Earth observation integration. Judges notice when a project leverages multiple NASA datasets synergistically.

**Deliverable:** Two new modules with cache-first fetching; integration into the GDD/water budget logic; synthetic fallback badges.

---

## 6. **Market Price + Dollar Savings Estimate (BR-11)**

The spec includes dollar savings (BR-11), and the crop DB has `market_value_usd_ton` as an extended attribute, but **the dollar savings calculation is not wired into the output yet**. Adding this gives a **concrete, tangible value** that resonates with farmers and judges alike.

**The fix — compute estimated savings per recommendation:**

- **Input:** Crop type + current market price (use a hardcoded regional price table for the demo, or fetch via a simple API).
- **Calculation:** `saved_revenue = yield_per_ha * price_per_ton` (yield inferred from crop type; e.g., sorghum ~2.5 ton/ha).
- **Total loss:** `baseline_revenue = planned_crop_yield * planned_crop_price`.
- **Net savings:** `saved_revenue - total_loss` (where total_loss = 0 if rescue crop succeeds, or planned revenue if fallback cover crop).
- **Output:** Add to the plan text: `"Estimated savings: $X/ha vs. total loss."`

**Code location:** `piper_agent/tools/generate_recovery_plan.py` — enrich `structured` output with `dollar_savings_estimate`; `piper_agent/tools/fetch_market_price.py` — add a `get_market_price(crop, region) -> float` function (mock API for demo).

**Why this wins:** Concrete numbers make the impact obvious. "Your field could save $287/ha" is a much stronger judging point than "the rescue crop fits the GDD window."

**Deliverable:** Market price lookup + savings calculation in plan output; hardcoded demo price table in `.env` or `config.py`.

---

## 7. **Enhanced Edge-Case Handling & Error UX**

The project handles the main paths well, but **edge cases that cause silent failures or confusing output** can crash a demo during live judging. Proactive edge-case handling shows maturity.

**The fix — three high-impact edge cases:**

| Edge case | Current behavior | Fix |
|---|---|---|
| **No crop fits the GDD window** | Returns `[]` from `filter_rescue_crops`; BR-5 fallback in `generate_recovery_plan` | Ensure the fallback cover-crop text is always displayed with a clear "cash crop is lost" statement. |
| **Live Earthdata auth fails mid-demo** | Cryptic `imergpy` error | Add a top-level `try/except` in `agent.py` that catches auth errors and switches to cache mode, printing a friendly notice. |
| **SMS input malformed** | No validation | Add input validation in `sms_gateway.py` that replies `"Please send: lat,lon,date"` on bad format. |

**Why this wins:** Judges will test edge cases live. Handling them gracefully = +2 credibility points.

**Deliverable:** Enhanced `agent.py` error handling; SMS input validation.

---

## 8. **Presentation / Slide Deck Backup**

Even with a great video, some judges may ask for a quick walkthrough or want to inspect the UI. A ≤7-slide deck is the required backup format.

**The fix — prepare the deck now:**

Slides (use Google Slides / PowerPoint / even A4 PDF):

1. **Problem** — Farmer facing flood/drought, crop loss, need for rescue planning (1 slide).
2. **Spec 3 Context** — Extreme weather + soil health pressures from the challenge (1 slide).
3. **How PIER Works** — The 4-tool pipeline (detect → GDD → filter → plan) (1 slide).
4. **Demo: Flood** — Screenshot of app, event detected, 2 crops with plant-by dates (1 slide).
5. **Demo: Drought** — Same format (1 slide).
6. **Fallback / BR-5** — Cover crop recommendation + "cash crop is lost" statement (1 slide).
7. **Impact & Roadmap** — SMS fallback, multi-hemisphere, live data path, future v1.1+ features (1 slide).

**Why this wins:** Having the deck ready shows you've "finished the thought" beyond the video. It also lets you adapt if video playback fails.

**Deliverable:** `docs/hackathon_deck.pdf` (or `.md`) ≤7 slides.

---

## Summary: Prioritized Action List

| Priority | Action | Estimated effort | Impact on evaluation |
|---|---|---|---|
| **P0** | Record 30s demo video (with captions) | 2–3 hours | **Critical** for Presentation/Relevance |
| **P0** | Prepare ≤7-slide deck backup | 1 hour | Required backup format |
| **P1** | Add SMS/USSD gateway (mock/Twilio) | 2–3 hours | High relevance/impact for farmers |
| **P1** | Add dollar savings estimate to plan output | 1–2 hours | Concrete value; strong judging point |
| **P1** | Hemisphere-aware GDD/frost logic | 1–2 hours | Shows global thinking |
| **P2** | OpenET ETa + SMAP integration | 2–3 hours | Multi-dataset depth |
| **P2** | Live data path with cache badge | 1–2 hours | Production transparency |
| **P3** | Enhanced edge-case error handling | 1 hour | Credibility during live judging |

**Recommendation:** Start with **P0** (video + deck) since those are deadline-mandatory. Then implement **P1** SMS + dollar savings — these give the biggest "wow" factor relative to effort. The rest can be post-hackathon roadmap additions.

---
*Generated as a strategic analysis for the PIER hackathon submission. All business rules BR-1 through BR-12 are already implemented; the gaps above are what will distinguish a "complete submission" from a "winning submission."*