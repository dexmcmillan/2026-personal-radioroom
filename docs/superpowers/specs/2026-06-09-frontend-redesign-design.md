# TGAM Radio Room — Frontend Redesign Design

**Date:** 2026-06-09
**Status:** Approved

## Overview

Replace the current Police Scout feed UI with "TGAM Radio Room" — a dark, monospace-styled monitoring interface with a collapsible province/service folder sidebar for navigation and filtering.

## Layout

Full-height, two-panel layout with no page scroll at the outer level:

```
┌─────────────────────────────────────────────┐
│  TGAM Radio Room       [search_]    09:41:22 │  ← header bar (full width)
├──────────────┬──────────────────────────────┤
│              │ ~/radio-room/ » ontario/halton│  ← path breadcrumb (sticky)
│   Sidebar    │                              │
│   (240px)    │         Feed                 │
│              │                              │
│              │                              │
└──────────────┴──────────────────────────────┘
```

## Header Bar

- Background: `#161b22`, bottom border: `#30363d`
- Left: green pulsing dot + "TGAM Radio Room" in uppercase monospace
- Centre: global search input (dark background, monospace)
- Right: live clock, updated every second (`HH:MM:SS`)
- Green `● LIVE` badge between title and search

## Sidebar

**Width:** 240px, fixed, non-scrolling with the feed. Independently scrollable.

**Structure:**
```
Services
────────────────
  All Releases         ← permanent home entry, selected on load
────────────────
▶ 📁 National
▶ 📁 British Columbia
▼ 📂 Ontario           ← expanded
    📄 Barrie PS
    📄 Belleville PS
    📄 Halton RPS      ← active (highlighted blue)
    ...
▶ 📁 Alberta
▶ 📁 Manitoba
▶ 📁 New Brunswick
▶ 📁 Nova Scotia
```

**Behaviour:**
- Province folders expand/collapse on click; arrow rotates 90° when open
- Clicking a service name: highlights it, filters the feed, updates the breadcrumb
- Clicking "All Releases": clears selection, restores full feed, resets breadcrumb
- Only one service can be active at a time
- On load: "All Releases" is active, all province folders are collapsed

**Visual style:**
- Background: `#111318`
- Folder text: `#c9d1d9`, open folder text: `#e6edf3`
- Service text: `#8b949e`, hover: `#c9d1d9`
- Active service: `#58a6ff` text, `#1c2840` background, `#58a6ff` left border (2px)
- Section label ("Services"): `#484f58`, small caps, 0.6rem

## Feed Panel

**Path breadcrumb (sticky):**
- `~/radio-room/ » ` in `#484f58`, province/service slug in `#58a6ff`
- When "All Releases" is active: `~/radio-room/ » all`

**Item layout:**
```
09:28   Halton Regional Police
        Missing Person – Oakville: Located →
        The individual reported missing on June 8 has been safely...
```

- Time column: `#3fb950` (green), monospace, 48px min-width, right-aligned
- Source name: `#58a6ff`, uppercase, 0.63rem, letter-spacing
- Title: `#e6edf3`, 0.82rem, semi-bold, linked to original release
- Snippet (first 4 lines): `#8b949e`, sans-serif, 0.72rem
- Row bottom border: `#161b22`; hover background: `#161b22`
- Infinite scroll (same IntersectionObserver pattern as current)

**TPS calls:** Excluded from this redesign. The feed is press releases only.

**Empty state:** Centred message in `#484f58`: `no releases found_`

## Search

- Input in top header bar, monospace, placeholder `search_`
- Filters globally across the full dataset, regardless of sidebar selection
- Combining search + sidebar filter is supported: search within a selected service
- Client-side, same substring match as current implementation

## Data & Build

**`sources.csv`:** Add a `province` column as the fifth field:
```
Name,url,link_selector,date_selector,province
Halton Regional Police Service,...,...,...,Ontario
Vancouver Police Department,...,...,...,British Columbia
RCMP,...,...,...,National
```

**Province assignments:**
| Province | Services |
|----------|----------|
| National | RCMP |
| British Columbia | Abbotsford PD, Central Saanich PS, Delta PD, Nelson PD, New Westminster PD, Vancouver PD |
| Alberta | Blood Tribe PS, Calgary PS, Edmonton PS |
| Manitoba | Altona PS, Brandon PS, Winnipeg PS |
| Ontario | Akwesasne Mohawk PS, Amherstburg PS, Anishinabek PS, Aylmer Police, Barrie PS, Belleville PS, Brantford PS, Brockville Police, Chatham-Kent PS, Cobourg PS, Cornwall CCPS, Durham RPSS, Greater Sudbury PS, Guelph PS, Halton RPSS, Hamilton PS, London PS, Nishnawbe-Aski PS, OPP, Ottawa PS, Peel RP |
| New Brunswick | Bathurst PF, Fredericton PF |
| Nova Scotia | Amherst PD, Annapolis Royal PD, Bridgewater PD, Cape Breton RPS, Halifax RP |

**`scan.py` → `build_feed()` function:**
- Load `sources.csv` via `load_sources()`, group by `province`, sort provinces alphabetically (National first)
- Pass `provinces` dict to Jinja2: `{ "National": [...], "British Columbia": [...], ... }`
- Template renders sidebar tree from `provinces`; feed still loads `docs/data.json` at runtime

**`templates/feed.html`:**
- Full rewrite of CSS and layout
- Sidebar rendered by Jinja2 at build time (service names, province grouping)
- JS handles: folder toggle, service selection, feed filtering, search, infinite scroll, clock
- No new JS dependencies

## Rename

The product is renamed from "Police Scout" to "TGAM Radio Room":
- `<title>` tag: `TGAM Radio Room`
- Header: `TGAM RADIO ROOM` (uppercase monospace)
- Path breadcrumb prefix: `~/radio-room/ »`
- Any other "Police Scout" references in the template

## Files Changed

| File | Change |
|------|--------|
| `sources.csv` | Add `province` column to all rows |
| `scan.py` (`build_feed`) | Pass `provinces` grouped dict to Jinja2 template |
| `templates/feed.html` | Full rewrite — new layout, sidebar, dark theme |

`scan.py`, `backfill.py`, and all data files are unchanged.
