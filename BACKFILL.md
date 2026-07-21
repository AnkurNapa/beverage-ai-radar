# Backfill notes

Operational steps that were designed but could not complete in the build session,
plus how to finish them.

## LinkedIn URLs for key people (pending)

**State:** The data model and all rendering are done. Each company can carry a
structured `people` list `[{name, role, linkedin}]`; named people already render
on the dashboard cards, in `report.md`, and in the vault notes. What is missing
is the actual `linkedin` URL per person.

**Why the WebSearch approach failed, and the workaround that works:** During the
build session the WebSearch quota was fully spent (200/200), so agents relying on
the WebSearch tool returned `null` for everyone. The workaround that DID work:
drive the **Playwright MCP browser** to Bing (`bing.com/search?q=Name+Company+LinkedIn`)
and decode the real `linkedin.com/in/...` URL from the results. Agents are
instructed never to guess or construct a URL, so a person with no findable
profile stays `null`. (The vault's existing beer-AI leads, 231 profiles, were
checked for reuse and had zero overlap with these founders.)

**How to finish (needs a session with WebSearch budget):**

1. Regenerate the input chunks (companies that have `key_people`):

   ```bash
   cd ~/Documents/beverage-ai-radar
   python3 - <<'PY'
   import json, math
   d = json.load(open('data/seed.json'))
   withp = [{"name": c["name"], "key_people": c["key_people"]} for c in d if c.get("key_people")]
   k = math.ceil(len(withp) / 4)
   for i in range(4):
       json.dump(withp[i*k:(i+1)*k], open(f'data/_li_in_{i+1}.json', 'w'), indent=1)
   print(len(withp), "companies split into 4 chunks")
   PY
   ```

2. Run four research agents (one per chunk). Each agent: for every person, find
   the real LinkedIn profile via WebSearch, include the URL ONLY if seen in
   results and clearly matching this person at this company, else `null`. Never
   guess. Output per company:
   `{"name": "<company>", "people": [{"name", "role", "linkedin"}]}` written to
   `data/_li_out_<i>.json`.

3. Merge into the seed (sets both `people` structured list and keeps
   `key_people` string), then re-run:

   ```bash
   python3 - <<'PY'
   import json
   seed = json.load(open('data/seed.json'))
   by = {c['name'].strip().lower(): c for c in seed}
   for i in (1, 2, 3, 4):
       for r in json.load(open(f'data/_li_out_{i}.json')):
           c = by.get(r['name'].strip().lower())
           if c and r.get('people'):
               c['people'] = r['people']
   json.dump(seed, open('data/seed.json', 'w'), indent=2)
   PY
   rm -f data/_li_in_*.json data/_li_out_*.json
   rm -f radar.sqlite
   PYTHONPATH=src .venv/bin/python -m radar.cli run
   git add -A && git commit -m "data: backfill per-person LinkedIn URLs" && git push
   ```

The links then appear automatically on cards, report, and vault notes (the
`people_fmt.people_md` helper and `peopleHtml` in `dashboard/app.js` already
handle them).

## GitHub Pages (blocked on plan)

Pages cannot publish from a private repo on the current GitHub plan. Options:
raise the plan, make the repo public, or push only `dashboard/` to a separate
public repo. Until then, preview locally:

```bash
PYTHONPATH=src .venv/bin/python -m radar.cli export
cd dashboard && python3 -m http.server 8099   # http://localhost:8099
```

## Drinktec re-pull (biennial fair)

Drinktec's exhibitor UI is a JS app, but it is backed by a public Directus JSON
API: `https://yontex.directus.app/items/exhibitor` (paginated, English
descriptions + company website URLs). To refresh after the next Drinktec
edition: fetch that endpoint, filter descriptions for AI/ML/data/software
signals (exclude bottling/filling/packaging machinery), take the company's own
website as the domain, tag `company_type` product/service, and merge into
data/seed.json. Not wired into the 2h cron on purpose: the fair is biennial, so
the exhibitor list barely changes between editions.

AgFunder is a news feed, handled by the signals watcher (src/radar/signals.py);
it is agtech-broad, so beverage-AI companies there are sparse and mostly already
tracked. Re-run the on-demand agent pass if you want to sweep it again.
