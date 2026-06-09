# TGAM Radio Room Frontend Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the Police Scout UI with TGAM Radio Room — a dark scanner-themed feed with a collapsible province/service folder sidebar, info popup, and the TPS call layer removed.

**Architecture:** Jinja2 renders the static sidebar tree at build time from `sources.csv` (with a new `province` column). All runtime behaviour — folder toggle, service filter, global search, infinite scroll, clock — is vanilla JS operating against the existing `docs/data.json`. Three files change: `sources.csv`, `scan.py` (two small edits), and `templates/feed.html` (full rewrite).

**Tech Stack:** Python 3.12, Jinja2 (already a dependency), vanilla JS (no new libraries), CSS custom properties.

---

### Task 1: Add `province` column to `sources.csv`

**Files:**
- Modify: `sources.csv`

- [ ] **Step 1: Replace the entire contents of `sources.csv`**

  The file gains a fifth column `province`. Paste this verbatim:

  ```
  Name of police service,url,link_selector,date_selector,province
  Abbotsford Police Department,https://www.abbypd.ca/blog/news_releases,a.blog-post-title,,British Columbia
  Akwesasne Mohawk Police Service,https://akwesasnepolice.ca/news-and-updates/,article h2 a,time,Ontario
  Altona Police Service,https://altona.ca/m/altona-police-service/local-notices,ul.notices a,time,Manitoba
  Amherst Police Department,https://www.amherst.ca/town-news/media-releases/,HEADING:div.blog-item,,Nova Scotia
  Amherstburg Police Service,https://windsorpolice.ca/newsroom/,HEADING:div.search-result,,Ontario
  Anishinabek Police Service,https://www.anishinabekpolice.ca/news,li.post-card h2 a,.fusion-tb-published-date,Ontario
  Annapolis Royal Police Department,https://annapolisroyal.com/police/,,,Nova Scotia
  Aylmer Police,https://www.aylmerpolice.com/events,,,Ontario
  Barrie Police Service,https://www.barriepolice.ca/newsroom/,h3.fl-post-title a,.fl-post-meta,Ontario
  Bathurst Police Force,https://www.bathurst.ca/en/services/1/bathurst-police-force,,,New Brunswick
  Belleville Police Service,https://www.bellevilleps.ca/news-stories/,article h3 a,time,Ontario
  Blood Tribe Police Service,https://www.bloodtribepolice.com/,,,Alberta
  Brandon Police Service,https://www.brandon.ca/news/police-media-releases/,a.gs-feed-list-title,.gs-feed-list-author-date,Manitoba
  Brantford Police Service,https://www.brantfordpolice.ca/news-and-media-releases/categories/media-releases/,a.gs-feed-list-title,.gs-feed-list-author-date,Ontario
  Bridgewater Police Department,https://www.bridgewaterpolice.ca/news-room,a[href*="/news-room/"],,Nova Scotia
  Brockville Police,https://brockvillepolice.com/news/,.entry-title a,time,Ontario
  Calgary Police Service,https://newsroom.calgary.ca/police-news-releases/,a.ppUnit,.pp-newsreel-list__date,Alberta
  Cape Breton Regional Police,https://www.cbrps.ca/media-releases/,HEADING:div.item-content,,Nova Scotia
  Central Saanich Police Service,https://www.cspolice.ca/news,.views-field-title h3 a,time,British Columbia
  Chatham-Kent Police Service,https://ckpolice.com/daily-news-release/,h2 a[href*="release"],time,Ontario
  Cobourg Police Service,https://cobourgpoliceservice.com/category/news/,.entry-title a,time,Ontario
  Cornwall Community Police Service,https://cornwallpolice.ca/news,div.card h4 a,,Ontario
  Delta Police Department,https://www.deltapolice.ca/media/releases,a.news-item__link,.news-item__date,British Columbia
  Durham Regional Police Service,https://www.drps.ca/news/media-releases/,a.gs-feed-list-title,.gs-feed-list-author-date,Ontario
  Edmonton Police Service,https://www.edmontonpolice.ca/News/MediaReleases,h2 a[href*="MediaReleases/"],,Alberta
  Fredericton Police Force,https://www.fredericton.ca/your-government/news,article h3 a,time,New Brunswick
  Greater Sudbury Police Service,https://www.gsps.ca/Modules/News/en,h2 a[href*="news"],.field-content,Ontario
  Guelph Police Service,https://www.guelphpolice.ca/news/media-releases/,a.gs-feed-list-title,.gs-feed-list-author-date,Ontario
  Halifax Regional Police,https://www.halifax.ca/home/news?category=25,a.c-news-updates__list-item-link,.c-news-updates__date,Nova Scotia
  Halton Regional Police Service,https://www.haltonpolice.ca/news-releases/,a.gs-feed-list-title,.gs-feed-list-author-date,Ontario
  Hamilton Police Service,https://hamiltonpolice.on.ca/news/?h=1&t=media,h3.pp_bigheadlines_heading a,.pp_bigheadlines_date,Ontario
  Nelson Police Department,https://www.nelson.ca/CivicAlerts.aspx?CID=7,,,British Columbia
  New Westminster Police Department,https://www.nwpolice.org/news-media/media-releases/,h3 a,time,British Columbia
  Nishnawbe-Aski Police Service,https://www.naps.ca/news/,.post-title a,,Ontario
  London Police Service,https://www.londonpolice.ca/news/general-releases/,a.gs-feed-list-title,.gs-feed-list-author-date,Ontario
  Ontario Provincial Police,https://www.opp.ca/news/,,,Ontario
  Ottawa Police Service,https://ottawapolice.news.esolg.ca/,a.newsTitle,.blogPostDate,Ontario
  Peel Regional Police,https://www.peelpolice.ca/news-feed/news-releases/,a.gs-feed-list-title,.gs-feed-list-author-date,Ontario
  RCMP,https://rcmp.ca/en/news,,,National
  Vancouver Police Department,https://vpd.ca/news/,,,British Columbia
  Winnipeg Police Service,https://www.winnipeg.ca/police/community/news-releases,,,Manitoba
  ```

- [ ] **Step 2: Verify the row count is unchanged**

  ```bash
  uv run python -c "
  import csv
  rows = list(csv.DictReader(open('sources.csv')))
  print(f'{len(rows)} services')
  missing = [r['Name of police service'] for r in rows if not r.get('province','').strip()]
  print('Missing province:', missing or 'none')
  "
  ```

  Expected output:
  ```
  41 services
  Missing province: none
  ```

- [ ] **Step 3: Commit**

  ```bash
  git add sources.csv
  git commit -m "data: add province column to sources.csv"
  ```

---

### Task 2: Update `scan.py` — read province + build province tree for template

**Files:**
- Modify: `scan.py:51-66` (`load_sources`)
- Modify: `scan.py:984-994` (`build_feed`)

- [ ] **Step 1: Write a failing test for province loading**

  Create `test_province.py` in the project root:

  ```python
  # test_province.py
  import csv, textwrap
  from pathlib import Path
  import pytest
  import scan

  @pytest.fixture
  def patched_sources(tmp_path, monkeypatch):
      content = textwrap.dedent("""\
          Name of police service,url,link_selector,date_selector,province
          Test Police,https://example.com,,,Ontario
          Another Service,https://example2.com,,,British Columbia
      """)
      csv_file = tmp_path / "sources.csv"
      csv_file.write_text(content)
      monkeypatch.setattr(scan, "SOURCES_FILE", csv_file)
      return csv_file

  def test_load_sources_returns_province(patched_sources):
      sources = scan.load_sources()
      assert len(sources) == 2
      assert sources[0]["province"] == "Ontario"
      assert sources[1]["province"] == "British Columbia"

  def test_load_sources_province_missing_is_empty_string(tmp_path, monkeypatch):
      content = textwrap.dedent("""\
          Name of police service,url,link_selector,date_selector
          Old Format Police,https://example.com,,,
      """)
      csv_file = tmp_path / "sources.csv"
      csv_file.write_text(content)
      monkeypatch.setattr(scan, "SOURCES_FILE", csv_file)
      sources = scan.load_sources()
      assert sources[0].get("province", "") == ""
  ```

- [ ] **Step 2: Run the test — expect failure**

  ```bash
  uv run pytest test_province.py -v
  ```

  Expected: `FAILED test_province.py::test_load_sources_returns_province` — `KeyError: 'province'`

- [ ] **Step 3: Update `load_sources()` in `scan.py`**

  Find lines 60-65 (the `sources.append({...})` block). Replace:

  ```python
                  sources.append({
                      "name": name,
                      "url": url,
                      "link_selector": row.get("link_selector", "").strip(),
                      "date_selector": row.get("date_selector", "").strip(),
                  })
  ```

  With:

  ```python
                  sources.append({
                      "name": name,
                      "url": url,
                      "link_selector": row.get("link_selector", "").strip(),
                      "date_selector": row.get("date_selector", "").strip(),
                      "province": row.get("province", "").strip(),
                  })
  ```

- [ ] **Step 4: Run tests — expect both to pass**

  ```bash
  uv run pytest test_province.py -v
  ```

  Expected:
  ```
  PASSED test_province.py::test_load_sources_returns_province
  PASSED test_province.py::test_load_sources_province_missing_is_empty_string
  ```

- [ ] **Step 5: Update `build_feed()` to compute province tree and pass it to Jinja2**

  Find the block at lines ~984-991:

  ```python
      sources = sorted({item["source"] for item in all_items if item.get("source")})
      env = Environment(loader=FileSystemLoader(str(TEMPLATE_DIR)), autoescape=True)
      try:
          template = env.get_template("feed.html")
      except Exception as e:
          print(f"  [build_feed] WARNING: could not load feed.html template: {e}")
          return
      html = template.render(generated_at=generated_at, sources=sources)
  ```

  Replace with:

  ```python
      _PROVINCE_ORDER = [
          "National", "British Columbia", "Alberta", "Manitoba",
          "Ontario", "New Brunswick", "Nova Scotia",
      ]

      def _slugify(s: str) -> str:
          return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")

      raw_provinces: dict[str, list[str]] = {}
      for src in load_sources():
          prov = src.get("province") or "Other"
          raw_provinces.setdefault(prov, []).append(src["name"])

      provinces: dict[str, list[str]] = {}
      for prov in _PROVINCE_ORDER:
          if prov in raw_provinces:
              provinces[prov] = sorted(raw_provinces[prov])
      for prov in sorted(raw_provinces):
          if prov not in provinces:
              provinces[prov] = sorted(raw_provinces[prov])

      service_paths: dict[str, str] = {}
      for prov, svcs in provinces.items():
          for svc in svcs:
              service_paths[svc] = f"{_slugify(prov)}/{_slugify(svc)}"

      total_services = sum(len(svcs) for svcs in provinces.values())

      env = Environment(loader=FileSystemLoader(str(TEMPLATE_DIR)), autoescape=True)
      try:
          template = env.get_template("feed.html")
      except Exception as e:
          print(f"  [build_feed] WARNING: could not load feed.html template: {e}")
          return
      html = template.render(
          generated_at=generated_at,
          provinces=provinces,
          service_paths=service_paths,
          total_services=total_services,
      )
  ```

- [ ] **Step 6: Smoke-test the template render**

  Run this one-liner. It calls `build_feed` against the existing `docs/data.json` and checks the output HTML contains the expected province names:

  ```bash
  uv run python -c "
  import scan, json
  items = json.loads(open('docs/data.json').read())
  scan.build_feed(items)
  html = open('docs/index.html').read()
  for prov in ['National', 'British Columbia', 'Ontario', 'Alberta']:
      assert prov in html, f'Missing: {prov}'
  print('OK — all province names present in output HTML')
  "
  ```

  Expected: `OK — all province names present in output HTML`

  If it raises `TemplateNotFound` or similar, the old `feed.html` is still in place — that's fine, Task 3 rewrites it. Fix any Python errors before proceeding.

- [ ] **Step 7: Commit**

  ```bash
  git add scan.py test_province.py
  git commit -m "feat: pass province tree to Jinja2 template from sources.csv"
  ```

---

### Task 3: Rewrite `templates/feed.html`

**Files:**
- Modify: `templates/feed.html` (full rewrite)

- [ ] **Step 1: Replace `templates/feed.html` with the new template**

  Paste this complete file:

  ```html
  <!DOCTYPE html>
  <html lang="en">
  <head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>TGAM Radio Room</title>
    <style>
      *, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }

      body {
        font-family: "SF Mono", "Fira Code", "Cascadia Code", "Consolas", monospace;
        background: #0d1117;
        color: #e6edf3;
        height: 100vh;
        display: flex;
        flex-direction: column;
        overflow: hidden;
      }

      /* ── Top bar ── */
      .topbar {
        background: #161b22;
        border-bottom: 1px solid #30363d;
        padding: 8px 16px;
        display: flex;
        align-items: center;
        gap: 12px;
        flex-shrink: 0;
      }
      .topbar-dot {
        width: 9px; height: 9px;
        border-radius: 50%;
        background: #3fb950;
        box-shadow: 0 0 8px #3fb950;
        flex-shrink: 0;
      }
      .topbar-title {
        font-size: 0.85rem;
        font-weight: 700;
        letter-spacing: 0.1em;
        text-transform: uppercase;
        color: #e6edf3;
        white-space: nowrap;
      }
      .topbar-live {
        font-size: 0.68rem;
        color: #3fb950;
        letter-spacing: 0.06em;
        white-space: nowrap;
      }
      #search {
        flex: 1;
        min-width: 0;
        max-width: 360px;
        background: #0d1117;
        border: 1px solid #30363d;
        border-radius: 4px;
        padding: 4px 10px;
        color: #e6edf3;
        font-family: inherit;
        font-size: 0.78rem;
      }
      #search:focus { outline: none; border-color: #58a6ff; }
      #search::placeholder { color: #484f58; }
      #clock {
        font-size: 0.7rem;
        color: #3fb950;
        white-space: nowrap;
      }
      .topbar-spacer { flex: 1; }
      .info-btn {
        background: none;
        border: 1px solid #30363d;
        color: #8b949e;
        font-family: inherit;
        font-size: 0.72rem;
        padding: 2px 7px;
        border-radius: 3px;
        cursor: pointer;
        white-space: nowrap;
        flex-shrink: 0;
      }
      .info-btn:hover { border-color: #58a6ff; color: #58a6ff; }

      /* ── Layout ── */
      .layout {
        display: flex;
        flex: 1;
        overflow: hidden;
      }

      /* ── Sidebar ── */
      .sidebar {
        width: 240px;
        flex-shrink: 0;
        background: #111318;
        border-right: 1px solid #21262d;
        overflow-y: auto;
        padding: 8px 0;
      }
      .sidebar-label {
        font-size: 0.6rem;
        letter-spacing: 0.1em;
        text-transform: uppercase;
        color: #484f58;
        padding: 4px 12px 6px;
      }
      .all-releases {
        display: flex;
        align-items: center;
        gap: 6px;
        padding: 5px 12px;
        font-size: 0.78rem;
        color: #c9d1d9;
        cursor: pointer;
        border-left: 2px solid transparent;
      }
      .all-releases:hover { background: #1c2128; color: #e6edf3; }
      .all-releases.active { color: #58a6ff; background: #1c2840; border-left-color: #58a6ff; }
      .sidebar-divider { border: none; border-top: 1px solid #21262d; margin: 6px 0; }
      .tree-item { position: relative; }
      .tree-folder {
        display: flex;
        align-items: center;
        gap: 5px;
        padding: 3px 8px 3px 10px;
        cursor: pointer;
        user-select: none;
        font-size: 0.78rem;
        color: #c9d1d9;
      }
      .tree-folder:hover { background: #1c2128; }
      .tree-folder.open { color: #e6edf3; }
      .tree-arrow {
        font-size: 0.6rem;
        color: #58a6ff;
        width: 10px;
        display: inline-block;
        transition: transform 0.12s;
        flex-shrink: 0;
      }
      .tree-folder.open .tree-arrow { transform: rotate(90deg); }
      .folder-icon { font-size: 0.9rem; flex-shrink: 0; }
      .tree-children { display: none; }
      .tree-children.open { display: block; }
      .tree-service {
        display: flex;
        align-items: center;
        gap: 5px;
        padding: 2px 8px 2px 28px;
        cursor: pointer;
        font-size: 0.73rem;
        color: #8b949e;
        white-space: nowrap;
        overflow: hidden;
        text-overflow: ellipsis;
        border-left: 2px solid transparent;
        margin-left: 10px;
      }
      .tree-service:hover { background: #1c2128; color: #c9d1d9; }
      .tree-service.active { color: #58a6ff; background: #1c2840; border-left-color: #58a6ff; }

      /* ── Feed panel ── */
      .feed-panel {
        flex: 1;
        display: flex;
        flex-direction: column;
        overflow: hidden;
      }
      .breadcrumb {
        background: #0d1117;
        border-bottom: 1px solid #21262d;
        padding: 6px 16px;
        font-size: 0.7rem;
        color: #484f58;
        flex-shrink: 0;
        display: flex;
        align-items: center;
        gap: 0;
      }
      #breadcrumb-path { color: #58a6ff; }
      #count { color: #484f58; margin-left: 20px; }
      #feed { flex: 1; overflow-y: auto; }
      .feed-item {
        display: flex;
        gap: 10px;
        padding: 9px 16px;
        border-bottom: 1px solid #161b22;
        align-items: flex-start;
      }
      .feed-item:hover { background: #161b22; }
      .feed-time {
        font-size: 0.7rem;
        color: #3fb950;
        white-space: nowrap;
        padding-top: 2px;
        min-width: 52px;
      }
      .feed-body { min-width: 0; flex: 1; }
      .feed-source {
        font-size: 0.63rem;
        text-transform: uppercase;
        letter-spacing: 0.07em;
        color: #58a6ff;
        margin-bottom: 2px;
      }
      .feed-title {
        font-size: 0.82rem;
        font-weight: 600;
        color: #e6edf3;
        line-height: 1.35;
      }
      .feed-title a { color: inherit; text-decoration: none; }
      .feed-title a:hover { color: #58a6ff; }
      .feed-snippet {
        font-size: 0.72rem;
        color: #8b949e;
        margin-top: 3px;
        line-height: 1.45;
        font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
        white-space: pre-wrap;
        display: -webkit-box;
        -webkit-line-clamp: 4;
        -webkit-box-orient: vertical;
        overflow: hidden;
      }
      #feed-empty {
        display: none;
        padding: 60px 20px;
        text-align: center;
        color: #484f58;
        font-size: 0.8rem;
      }
      #loading { padding: 40px; text-align: center; color: #484f58; font-size: 0.8rem; }
      #load-sentinel { height: 1px; display: none; }

      /* ── Info modal ── */
      .modal-overlay {
        display: none;
        position: fixed;
        inset: 0;
        background: rgba(0,0,0,0.7);
        z-index: 200;
        align-items: center;
        justify-content: center;
      }
      .modal-overlay.open { display: flex; }
      .modal {
        background: #161b22;
        border: 1px solid #30363d;
        border-radius: 6px;
        padding: 24px 28px;
        max-width: 480px;
        width: 90%;
        position: relative;
      }
      .modal h2 {
        font-size: 0.9rem;
        letter-spacing: 0.08em;
        text-transform: uppercase;
        color: #e6edf3;
        margin-bottom: 14px;
      }
      .modal p {
        font-size: 0.8rem;
        color: #8b949e;
        line-height: 1.65;
        font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
        margin-bottom: 10px;
      }
      .modal p:last-of-type { margin-bottom: 0; }
      .modal-close {
        position: absolute;
        top: 12px; right: 14px;
        background: none;
        border: none;
        color: #484f58;
        font-family: inherit;
        font-size: 0.8rem;
        cursor: pointer;
      }
      .modal-close:hover { color: #e6edf3; }

      /* ── Scrollbar ── */
      ::-webkit-scrollbar { width: 5px; }
      ::-webkit-scrollbar-track { background: transparent; }
      ::-webkit-scrollbar-thumb { background: #30363d; border-radius: 3px; }
      ::-webkit-scrollbar-thumb:hover { background: #484f58; }
    </style>
  </head>
  <body>

    <div class="topbar">
      <div class="topbar-dot"></div>
      <span class="topbar-title">TGAM Radio Room</span>
      <span class="topbar-live">● LIVE</span>
      <input id="search" type="search" placeholder="search_" autocomplete="off">
      <span class="topbar-spacer"></span>
      <span id="clock"></span>
      <button class="info-btn" onclick="toggleModal(true)">[?]</button>
    </div>

    <div class="layout">

      <div class="sidebar">
        <div class="sidebar-label">Services</div>
        <div class="all-releases active" onclick="selectAll(this)">◈ All Releases</div>
        <hr class="sidebar-divider">
        {% for province, services in provinces.items() %}
        <div class="tree-item">
          <div class="tree-folder" onclick="toggleFolder(this)">
            <span class="tree-arrow">▶</span>
            <span class="folder-icon">📁</span>
            {{ province }}
          </div>
          <div class="tree-children">
            {% for service in services %}
            <div class="tree-service"
                 data-service="{{ service }}"
                 data-path="{{ service_paths[service] }}"
                 onclick="selectService(this)">
              📄 {{ service }}
            </div>
            {% endfor %}
          </div>
        </div>
        {% endfor %}
      </div>

      <div class="feed-panel">
        <div class="breadcrumb">
          ~/radio-room/ » <span id="breadcrumb-path">all</span>
          <span id="count"></span>
        </div>
        <div id="feed"><div id="loading">loading_</div></div>
        <div id="feed-empty">no releases found_</div>
        <div id="load-sentinel"></div>
      </div>

    </div>

    <!-- Info modal -->
    <div class="modal-overlay" id="modal-overlay" onclick="handleOverlayClick(event)">
      <div class="modal">
        <button class="modal-close" onclick="toggleModal(false)">[x]</button>
        <h2>// TGAM Radio Room</h2>
        <p>TGAM Radio Room monitors {{ total_services }} Canadian police services and automatically collects press releases as they are published. The archive is rebuilt roughly every hour via a scheduled GitHub Actions workflow.</p>
        <p>Use the sidebar to browse by province or service. The search bar filters across all releases regardless of sidebar selection.</p>
        <p>Updated: {{ generated_at }}</p>
      </div>
    </div>

    <script>
      (function () {
        var allItems = [];
        var currentFiltered = [];
        var renderedCount = 0;
        var PAGE_SIZE = 50;
        var selectedService = null;

        var feedEl      = document.getElementById('feed');
        var sentinelEl  = document.getElementById('load-sentinel');
        var emptyEl     = document.getElementById('feed-empty');
        var searchEl    = document.getElementById('search');
        var clockEl     = document.getElementById('clock');
        var breadcrumbEl = document.getElementById('breadcrumb-path');
        var countEl     = document.getElementById('count');

        // ── Clock ──
        function tick() {
          var now = new Date();
          clockEl.textContent = now.toTimeString().slice(0, 8);
        }
        setInterval(tick, 1000);
        tick();

        // ── Info modal ──
        function toggleModal(open) {
          var overlay = document.getElementById('modal-overlay');
          if (open) overlay.classList.add('open');
          else overlay.classList.remove('open');
        }
        function handleOverlayClick(e) {
          if (e.target === document.getElementById('modal-overlay')) toggleModal(false);
        }

        // ── Folder toggle ──
        function toggleFolder(el) {
          el.classList.toggle('open');
          var icon = el.querySelector('.folder-icon');
          var children = el.closest('.tree-item').querySelector('.tree-children');
          if (el.classList.contains('open')) {
            icon.textContent = '📂';
            children.classList.add('open');
          } else {
            icon.textContent = '📁';
            children.classList.remove('open');
          }
        }

        // ── Service selection ──
        function clearActive() {
          document.querySelectorAll('.tree-service.active, .all-releases.active')
            .forEach(function (el) { el.classList.remove('active'); });
        }

        function selectAll(el) {
          clearActive();
          el.classList.add('active');
          selectedService = null;
          breadcrumbEl.textContent = 'all';
          applyFilters();
        }

        function selectService(el) {
          clearActive();
          el.classList.add('active');
          selectedService = el.dataset.service;
          breadcrumbEl.textContent = el.dataset.path;
          applyFilters();
        }

        // ── Helpers ──
        function esc(str) {
          if (!str) return '';
          return String(str)
            .replace(/&/g, '&amp;').replace(/</g, '&lt;')
            .replace(/>/g, '&gt;').replace(/"/g, '&quot;');
        }

        function formatDate(iso) {
          if (!iso) return '—';
          var p = iso.split('-');
          var months = ['Jan','Feb','Mar','Apr','May','Jun',
                        'Jul','Aug','Sep','Oct','Nov','Dec'];
          return months[parseInt(p[1], 10) - 1] + ' ' + parseInt(p[2], 10);
        }

        function getSearchText(item) {
          return ((item.title || '') + ' ' + (item.source || '') + ' ' + (item.content || '')).toLowerCase();
        }

        // ── Card ──
        function renderCard(item) {
          var div = document.createElement('div');
          div.className = 'feed-item';
          var titleHtml = item.url
            ? '<a href="' + esc(item.url) + '" target="_blank" rel="noopener">' + esc(item.title) + ' →</a>'
            : esc(item.title || '');
          var snippetHtml = item.content
            ? '<div class="feed-snippet">' + esc(item.content.slice(0, 500)) + '</div>'
            : '';
          div.innerHTML =
            '<div class="feed-time">' + esc(formatDate(item.date)) + '</div>' +
            '<div class="feed-body">' +
              '<div class="feed-source">' + esc(item.source) + '</div>' +
              '<div class="feed-title">' + titleHtml + '</div>' +
              snippetHtml +
            '</div>';
          return div;
        }

        // ── Pagination ──
        function appendNextPage() {
          var end = Math.min(renderedCount + PAGE_SIZE, currentFiltered.length);
          for (var i = renderedCount; i < end; i++) {
            feedEl.appendChild(renderCard(currentFiltered[i]));
          }
          renderedCount = end;
          sentinelEl.style.display = renderedCount < currentFiltered.length ? 'block' : 'none';
          updateCount();
        }

        function updateCount() {
          var q = searchEl.value.trim();
          if (q || selectedService) {
            countEl.textContent = currentFiltered.length + ' of ' + allItems.length;
          } else {
            countEl.textContent = allItems.length + ' releases';
          }
        }

        // ── Filter ──
        function applyFilters() {
          var q = searchEl.value.toLowerCase().trim();
          currentFiltered = allItems.filter(function (item) {
            var matchesService = !selectedService || item.source === selectedService;
            var matchesSearch  = !q || getSearchText(item).indexOf(q) !== -1;
            return matchesService && matchesSearch;
          });
          feedEl.innerHTML = '';
          renderedCount = 0;
          if (currentFiltered.length === 0) {
            emptyEl.style.display = '';
            sentinelEl.style.display = 'none';
            updateCount();
          } else {
            emptyEl.style.display = 'none';
            appendNextPage();
          }
        }

        // ── Infinite scroll ──
        if ('IntersectionObserver' in window) {
          var observer = new IntersectionObserver(function (entries) {
            if (entries[0].isIntersecting && renderedCount < currentFiltered.length) {
              appendNextPage();
            }
          }, { rootMargin: '300px' });
          observer.observe(sentinelEl);
        }

        // ── Search ──
        searchEl.addEventListener('input', applyFilters);

        // ── Expose to inline onclick attrs ──
        window.toggleFolder  = toggleFolder;
        window.selectAll     = selectAll;
        window.selectService = selectService;
        window.toggleModal   = toggleModal;
        window.handleOverlayClick = handleOverlayClick;

        // ── Load data ──
        fetch('data.json')
          .then(function (r) {
            if (!r.ok) throw new Error('HTTP ' + r.status);
            return r.json();
          })
          .then(function (data) {
            allItems = data.filter(function (item) { return item.type !== 'tps_call'; });
            applyFilters();
          })
          .catch(function (err) {
            feedEl.innerHTML = '<div style="padding:40px;text-align:center;color:#f78166">error: ' + esc(String(err)) + '</div>';
          });
      })();
    </script>
  </body>
  </html>
  ```

- [ ] **Step 2: Rebuild and open in browser**

  ```bash
  uv run python -c "
  import scan, json
  items = json.loads(open('docs/data.json').read())
  scan.build_feed(items)
  print('Built docs/index.html')
  "
  open docs/index.html
  ```

- [ ] **Step 3: Verify these things manually**

  - [ ] Dark background loads, green dot and clock visible in top bar
  - [ ] Sidebar shows "All Releases" at top (active/highlighted blue on load)
  - [ ] Province folders are present and collapsed by default
  - [ ] Clicking a province folder opens/closes it and swaps 📁/📂 icon
  - [ ] Clicking a service name: highlights it, feed filters to that service only, breadcrumb updates
  - [ ] Clicking "All Releases" resets the feed to all releases and clears the service highlight
  - [ ] Typing in search box filters the visible feed (test with a known service name)
  - [ ] Combining search + service selection: only matching releases for that service appear
  - [ ] `[?]` button opens the info modal; clicking outside or `[x]` closes it
  - [ ] Modal shows correct service count and "Updated:" timestamp
  - [ ] No TPS call items appear in the feed (check a date where TPS calls were present)
  - [ ] Scroll to the bottom of a long feed triggers infinite scroll to load more

- [ ] **Step 4: Commit**

  ```bash
  git add templates/feed.html
  git commit -m "feat: TGAM Radio Room — dark scanner UI with province folder sidebar"
  ```

---

### Task 4: Clean up

**Files:**
- No file changes

- [ ] **Step 1: Run the full test suite**

  ```bash
  uv run pytest test_province.py -v
  ```

  Expected: 2 passed, 0 failed.

- [ ] **Step 2: Verify `scan.py` main run still works end-to-end**

  Do a dry run of the scraper (this actually hits the network — use `--help` flag or just build from cached data):

  ```bash
  uv run python -c "
  import scan, json
  items = json.loads(open('docs/data.json').read())
  scan.build_feed(items)
  print('build_feed OK')
  "
  ```

  Expected: `build_feed OK` with no exceptions.

- [ ] **Step 3: Final commit**

  ```bash
  git add -u
  git status
  ```

  Confirm only expected files are staged, then:

  ```bash
  git commit -m "chore: TGAM Radio Room redesign complete" --allow-empty
  ```

  (Use `--allow-empty` only if there are no outstanding changes; otherwise commit whatever remains staged.)
