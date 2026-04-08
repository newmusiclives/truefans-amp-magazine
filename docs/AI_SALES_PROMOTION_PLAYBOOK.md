# AI Sales + Promotion Playbook

What the AI Sales and Promotion staff will actually do when `WEEKLYAMP_WORKERS_ENABLED=true`. This is a working spec — every task in this playbook maps to a real method on `SalesAgent` / `PromotionAgent` / `MarketingAgent` and a real cron entry in `workers/scheduler.py`.

---

## The org chart

Each edition has a named Sales lead and a Promotion lead, and there's a cross-newsletter VP of Sales who coordinates across all three editions. This isn't aspirational — these personas already exist as seeded rows in the `ai_agents` table (`core/database.py:360-510`):

| Role | Fan Edition | Artist Edition | Industry Edition | Cross-newsletter |
|---|---|---|---|---|
| **Sales lead** | Kyle Mitchell | Dana Preston | Talia Brooks | Grant Sullivan (VP) |
| **Promotion lead** | Jess Whitfield | Cody Marshall | Ryan Caldwell | — |
| **CMO (coordinator)** | — | — | — | Morgan Blake |

`MarketingAgent` (Morgan) doesn't draft prospects or partners directly. It fans out to the per-edition specialists — same pattern the orchestrator uses for Writers. One trigger on Marketing produces structured output for all three editions in parallel.

---

## What gets stored where

All structured output lands in real DB tables, queryable from the admin UI:

| Output | Table | Owning agent type |
|---|---|---|
| Sponsor prospects | `sponsor_prospects` | Sales |
| Cross-promo partners | `cross_promo_partners` (v43) | Promotion |
| Outreach activity log | `outreach_log` | Sales + Promotion |
| Free-text plans, reports, drafts | `agent_outputs` | All |

The state machine on each prospect/partner is `identified → contacted → negotiating → closed_won/closed_lost` (sponsors) or `identified → contacted → negotiating → live/declined/expired` (partners). The agents move rows through these states; humans approve and close.

---

## Cron schedule

Set in `workers/scheduler.py:181-227`. All times UTC. The Sales/Promotion fan-outs are **driven by Marketing's cron entries** so a single trigger reaches all per-edition specialists.

| When | Job | What happens |
|---|---|---|
| Mon 09:00 | `marketing_prospect_scan` | Marketing fans out `identify_prospects` to Kyle, Dana, Talia, Grant. Each LLM-generates 5 sponsor candidates scoped to their edition, parses to JSON, writes rows to `sponsor_prospects` with `target_editions` set and `source = "agent:sales:<edition>"`. |
| Daily 10:00 | `marketing_outreach` | Marketing fans out `draft_outreach_batch` to all Sales agents. Each picks up the next 5 prospects in `identified` state for their edition, drafts a personalized email per prospect using its persona's voice, flips the prospect to `contacted`, and logs the send to `outreach_log`. |
| Daily 11:00 | `marketing_social` | Promotes recent published issues across X, LinkedIn, Instagram. Currently lives directly on `MarketingAgent` (cross-functional, not delegated). |
| Daily 14:00 | `marketing_retention` | Two-stage: `identify_at_risk` flags subscribers with no opens in 14 days; `draft_winback_batch` produces a re-engagement email and queues sends. |
| Fri 16:00 | `marketing_weekly_report` | Generates a weekly performance report consolidating outreach stats, prospect pipeline state, and growth metrics. Output to `agent_outputs` for the admin to review on Monday morning. |

**Crons that aren't yet wired but will be added:** `identify_partners` (Promotion fan-out, suggested weekly Tue 10:00), `draft_cross_promo` (Promotion, suggested daily 14:00 right after retention).

---

## Sales playbook — by edition

Each Sales lead operates on the same task types (`identify_prospects`, `draft_outreach`, `draft_outreach_batch`, `update_pipeline`) but their persona, prompt voice, and scoped audience are different. The agent reads its `edition` from `config_json` at construction time and threads it through every prompt.

### Fan Edition — Kyle Mitchell

**Persona:** Streaming-platform brand-partnerships background. "Thinks like a listener first, salesperson second."

**Prospect targets (what `identify_prospects` will surface):**
- Streaming platforms and music discovery apps (Spotify, Audius, Bandcamp, Tidal partner programs)
- DTC consumer brands that sponsor playlists or podcasts (Liquid Death, Athletic Greens, Magic Spoon, Liquid IV)
- Festival promoters and ticket platforms (Dice, See Tickets, regional festival circuits)
- Vinyl subscription services (VMP, Sounds Delicious)
- Music documentary and music-tourism brands

**Outreach voice:** Warm, conversational, leads with audience alignment ("Your audience and ours both index high on indie-music discovery"). Soft CTA to a 15-minute intro call. Sender signature: Kyle Mitchell, Sales Lead — TrueFans SIGNAL Fan Edition.

**Pipeline cadence:** Weekly identify (Mon), daily outreach drafts (Mon-Fri), pipeline snapshot to admin Friday afternoon as part of the weekly report.

### Artist Edition — Dana Preston

**Persona:** Major-label radio network ad sales background. "Niche audience targeting from podcast advertising."

**Prospect targets:**
- Music gear and instrument brands (Sweetwater, Reverb, Fender, PRS, DistroKid, Splice)
- Music education platforms (Berklee Online, ArtistWorks, Pickup Music, Soundfly)
- Recording and mixing services (LANDR, eMastered, MixCoach)
- Music software and plugins (Native Instruments, iZotope, FabFilter)
- Tour-support services (Soundcheck, Bandzoogle, BandLab, ToneDen)

**Outreach voice:** Data-driven, leads with engagement metrics, references the artist-development stage of the audience. "Our artist subscribers are at the buying stage for [category]." Sender signature: Dana Preston, Sales Lead — TrueFans SIGNAL Artist Edition.

**Pipeline cadence:** Same as Fan, scoped to artist-friendly categories.

### Industry Edition — Talia Brooks

**Persona:** Major-label corporate partnerships director. "Speaks fluent data, backs every pitch with audience demographics."

**Prospect targets:**
- B2B music tech (Chartmetric, Soundcharts, Songtrust, Audiokite, Beatdapp)
- Music rights and royalty services (Songtrust, Royalty Exchange, Cosynd, ICE)
- Legal services (entertainment law firms, IP boutiques)
- Music industry conferences and events (SXSW partner brands, MIDEM, Music Biz)
- Industry publications and trade press (Hits Daily Double, MusicBusinessWorldwide partnership inventory)
- Distribution and label services (UnitedMasters, Vydia, Stem, Symphonic)

**Outreach voice:** Executive register, leads with reach into decision-makers and concrete CPM/CTR projections. Heavier on data than the other two editions. Sender signature: Talia Brooks, Sales Lead — TrueFans SIGNAL Industry Edition.

**Pipeline cadence:** Same. Industry deals tend to be larger and longer cycles, so the prospects-per-week target is lower (3 instead of 5) and the proposal stage takes longer.

### Cross-newsletter — Grant Sullivan (VP of Sales)

**Persona:** 12 years in media ad sales (iHeartMedia, podcast networks). "Sets revenue targets, pricing strategy, sponsor retention."

**Role:** Coordinator and bundler. Grant doesn't draft individual prospect outreach &mdash; he picks up prospects that haven't been claimed by an edition (the `cross-newsletter` slot in `draft_outreach_batch`) and pitches **portfolio packages** that span all three editions. Bigger ticket, longer cycle, fewer in-flight deals.

**What Grant will produce when turned on:**
- Weekly portfolio prospect list (5 advertisers who would benefit from cross-edition placement)
- Tiered rate cards (logged as `agent_outputs.rate_card_proposal`)
- Quarterly retention outreach to existing sponsors flagged as `closed_won` more than 90 days ago
- Drafts of "renewal pitch" emails for sponsors approaching the end of their current term

---

## Promotion playbook — by edition

Promotion specialists handle the **subscriber acquisition** side: cross-promo partnerships, referral campaigns, and growth tactic generation. Same fan-out pattern, scoped to each edition's audience.

### Fan Edition — Jess Whitfield

**Persona:** Former Substack growth lead. Scaled three music newsletters past 100K. "Believes every subscriber is a potential evangelist."

**Partner targets (what `identify_partners` will surface):**
- Other music discovery newsletters (Hearing Things, The Quietus, The Talkhouse, The 5:38)
- Music podcasts with engaged audiences (Song Exploder, Switched On Pop, Cocaine &amp; Rhinestones, Strong Songs)
- Communities around specific genres (Rate Your Music adjacent, indie subreddits, Discord servers for niche fanbases)
- Indie-focused TikTok/YouTube creators with newsletter cross-promo budgets

**Cross-promo plays Jess will draft:**
1. **Featured-artist swap** — Each newsletter features the other's pick of the week in their next edition.
2. **Referral incentive trade** — Jess's edition offers Partner-X subscribers exclusive content; Partner-X reciprocates for our subscribers.
3. **Joint subscriber giveaway** — Both newsletters promote a shared sweepstakes (vinyl bundle, festival tickets, gear). Subscribers must opt in to both lists to enter.
4. **Guest column swap** — Editor-to-editor content trade.

**Voice:** Casual, peer-to-peer, "we're both indies trying to build something." Sender: Jess Whitfield, Promotion Lead.

### Artist Edition — Cody Marshall

**Persona:** Former music podcast network marketing director. "Master of artist community partnerships, ambassador programs."

**Partner targets:**
- Songwriter and musician communities (NSAI, ASCAP Foundation, Songfancy, BandZoogle blog, YouTube musician educators)
- Music education platforms with newsletters (Berklee Online, ArtistWorks, Pickup Music, Soundfly)
- Indie label newsletters and Bandcamp daily-style outlets
- Producer/engineer communities (Gearspace, Production Expert, Sound on Sound)
- Touring artist support orgs (Future of Music Coalition, Backline, MusiCares)

**Cross-promo plays:**
1. **Ambassador program** — Recruit our existing artist subscribers to share the newsletter with their fanbases in exchange for featured placement, gear giveaways, or paid promo of their next release.
2. **Guest takeover** — A respected artist guest-edits an edition; their fans come in via cross-promo.
3. **Co-branded content series** — Joint long-form pieces with another artist newsletter, bylined to both editorial teams.
4. **Conference partner swaps** — Cross-promo with conferences and music-business events.

**Voice:** Solidarity-focused, music-community first. Sender: Cody Marshall, Promotion Lead — Artist Edition.

### Industry Edition — Ryan Caldwell

**Persona:** Former Billboard / Music Business Worldwide marketing strategist. "LinkedIn thought leadership, conference partnerships, executive referral networks."

**Partner targets:**
- LinkedIn thought-leadership creators in music business
- Industry conferences and events (SXSW, MIDEM, NY:LON, Music Biz, Pollstar Live, IMS)
- Trade publication newsletters (MusicBusinessWorldwide, Variety Music, Billboard B2B)
- Executive referral networks (Music Business Association, A2IM, IMPALA)
- B2B podcasts (The Music Industry Blueprint, Music Tectonics)

**Cross-promo plays:**
1. **LinkedIn newsletter swap** — Cross-promotion to LinkedIn newsletter audiences.
2. **Conference partner placement** — Featured in conference comms in exchange for promotion to our executive readership.
3. **Executive referral campaigns** — Identify and approach C-suite music execs in our subscriber base for warm introductions to their networks.
4. **Trade publication content trades** — Long-form article exchanges with major industry outlets.

**Voice:** Polished, professional, B2B SaaS register. Sender: Ryan Caldwell, Promotion Lead — Industry Edition.

---

## Daily / weekly rhythm (operator view)

Once workers are enabled, this is what the admin sees on a typical week:

**Monday morning**
- Wake up to fresh sponsor prospects from all 3 Sales leads (15 total) in `sponsor_prospects` with status `identified`
- Weekly marketing report from Friday afternoon waiting in `agent_outputs`
- Open the admin dashboard → Sponsors view → review and approve/reject the new prospects

**Monday afternoon onwards**
- Outreach drafts start landing in the prospect detail view as the daily 10:00 cron fires
- Each prospect now has a draft email (in `agent_outputs.outreach_email`) ready for human edit-and-send
- Status flips to `contacted` once drafted

**Tuesday onwards**
- Promotion fan-out (when wired) produces partner candidates in `cross_promo_partners`
- Same approval flow: review, approve, edit drafts, send

**Friday afternoon**
- Weekly report consolidates the week's activity
- Pipeline snapshot per edition

**Throughout the week**
- Re-engagement check (daily 14:00) catches any subscribers going dormant and queues win-back emails
- Social posts (daily 11:00) promote published issues

**The human's job in this loop:** approve, edit, send. The agents handle prospect discovery, draft generation, persistence, and follow-up tracking. The human stays in the loop for every outbound message — none of these agents send mail without explicit approval.

---

## Safety / autonomy gating

Three layers of brakes:

1. **`WEEKLYAMP_WORKERS_ENABLED=true` env var** — master kill switch. False = no crons run at all. Currently true in production as of 2026-04-08.

2. **`agents.default_autonomy = "autonomous"` config flag** — Marketing's `_marketing_*` cron jobs no-op early when this is anything other than `"autonomous"` (see `workers/scheduler.py:78-178`). Default is `"semi_auto"` which keeps the fan-outs from running automatically until you flip the flag. This is the right place to "turn the AI Sales/Promotion teams on" — toggle this config field, not the master worker switch.

3. **Human approval required on every outbound message.** Even when fully autonomous, the agents draft and persist; they do not send. Sends happen through the existing approval flows in the admin UI.

Today's state: master switch on, autonomy = `semi_auto`. Crons are firing for non-marketing jobs (research, welcome queue, scheduled sends, dunning, etc.) but the Sales/Promotion fan-outs are gated off. To turn the AI teams on, change `agents.default_autonomy` to `"autonomous"` in `config/default.yaml` (or the equivalent env var override) and redeploy.

---

## Metrics to watch in week 1

If you turn the team on today, here's what to watch in the dashboard over the first week to know whether it's working:

1. **Prospects identified per edition** — Should land 15/week total once the Mon scan fires. If <10, the LLM is rejecting requests or the JSON parser is dropping malformed responses. Check `agent_outputs` for raw LLM output.

2. **Outreach draft completion rate** — Of prospects in `identified` state, what % get a draft email within 24h. Target: >80% by end of week 1. Lower means the daily 10:00 outreach cron is failing for some edition; check the per-edition `agent_outputs.outreach_email` rows.

3. **Approval-to-send rate** — Of drafts the agents produce, what % do you actually approve and send. Target: >50%. Below that means the prompts need editing. Above 80% means you're rubber-stamping and should slow down to spot-check more.

4. **Prospect → contacted state transitions** — Should be ~5/edition/day matching the batch size. If transitions aren't happening, the `update_prospect_status` call in `draft_outreach_batch` is silently failing (check `[ERRO]` lines in Railway logs — these now include tracebacks thanks to the formatter fix from 2026-04-08).

5. **Cost per edition** — From the existing per-edition cost tracking telemetry. Each prospect identification call is ~900 tokens out, each outreach draft is ~600 tokens out. Sales fan-out across 3 editions is therefore ~7,500 tokens/week of structured prospect output and ~9,000 tokens/day of outreach drafts. Roughly $0.05/day per edition at current Anthropic pricing — so the AI staff costs less than a single sponsored ad placement to run.

---

## When something goes wrong

The most likely failure modes once the AI teams are turned on, and what to do:

| Symptom | Likely cause | Fix |
|---|---|---|
| Zero prospects appearing | LLM rejecting prompt or JSON parser failing | Check `agent_outputs.prospect_list_raw` for the raw response. Adjust prompt in `agents/sales.py:identify_prospects`. |
| Duplicate prospects across editions | No cross-edition dedup yet | Add a unique constraint or pre-insert lookup on `(company_name, target_editions)`. Filed for v45. |
| Outreach drafts feel generic | LLM has no edition voice context | Each edition's persona is in the seeded `system_prompt` field on the agent row. Edit it via the admin Agents UI. |
| Same prospect getting outreached twice | `draft_outreach_batch` only filters by `status='identified'` | If you manually move a prospect back to `identified`, expect another draft. Move to `closed_won` or `closed_lost` to exit the loop. |
| Cron fires but produces nothing | `agents.default_autonomy != "autonomous"` | Check config. The marketing crons silently no-op when not autonomous. |
| Cron fires and crashes loudly | Some bug that wasn't covered by today's pool fix | Logs now include tracebacks thanks to the JSONFormatter fix in commit `bb381b1`. Read the traceback and patch. |

---

## What's NOT in scope for the AI teams

So expectations are calibrated:

- **The agents do not send emails autonomously.** They draft and persist. Humans approve and send. This is a deliberate design decision and should not change.
- **The agents do not negotiate.** They produce the first-touch and follow-up drafts. Once a prospect responds, the human takes over the thread.
- **The agents do not set rate cards.** Grant Sullivan is structured to *propose* rate cards as `agent_outputs`, but pricing decisions are still human.
- **The agents do not run paid ad campaigns.** No ad spend authority.
- **The agents do not contact existing subscribers in bulk** without going through the existing campaign approval flow.

---

## How to turn it on

Three steps. Reversible in seconds.

1. **Master switch** — already on:
   ```
   WEEKLYAMP_WORKERS_ENABLED=true   # currently true
   ```

2. **Autonomy flag** — currently off. To enable:
   - Edit `config/default.yaml` → `agents.default_autonomy: autonomous`, or
   - Set the env var override `WEEKLYAMP_AGENTS_AUTONOMY=autonomous` in Railway

3. **Redeploy** — `git push origin main` triggers auto-deploy to both repos and Railway picks up the change in ~3 minutes.

To turn it back off, flip step 2 back to `semi_auto` and redeploy. The crons will still fire on schedule but the marketing jobs will no-op early.

---

## Followups

Things this playbook describes that aren't yet in the code:

- [ ] **Cron entries for `identify_partners` and `draft_cross_promo`** (Promotion fan-outs). Currently `MarketingAgent.identify_partners` exists but no cron calls it. Add to `start_scheduler()`.
- [ ] **Cross-edition dedup on prospect identification** to avoid identifying the same company three times in one Monday morning batch.
- [ ] **Rate card generator** for Grant Sullivan — referenced in this doc but not yet implemented.
- [ ] **Renewal pitch generator** for sponsors approaching end of term — same.
- [ ] **Admin UI surface** for `cross_promo_partners` (table is in v43 but no admin page yet).
- [ ] **Per-edition cost dashboard** — the per-edition cost-tracking work in the user's auto-memory is the missing piece for tracking AI-team economics over time.
