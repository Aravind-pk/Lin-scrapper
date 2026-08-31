# LinkedIn Profile API

Takes a LinkedIn profile URL, returns the profile as structured JSON. No browser
in the request path — a plain HTTP client against LinkedIn's own Voyager API.

```bash
curl -X POST "$BASE_URL/api/integrations/linkedin/profile" \
  -H 'Content-Type: application/json' \
  -d '{
        "url": "https://www.linkedin.com/in/williamhgates",
        "cookie_header": "<your LinkedIn Cookie header>",
        "user_agent": "<the browser you copied it from>"
      }'
```

`BASE_URL` is wherever the service is deployed, or `http://127.0.0.1:8000` when
run locally. Browsing to it serves a playground that calls the same endpoint.

The service stores no credentials. Every request runs on the caller's own
session, which is why both of those fields are required.

> Automated access to LinkedIn is not permitted by its User Agreement. This is a
> technical exercise — use your own account, and your own judgement.

---

## Running it locally

```bash
python3 -m venv .venv
./.venv/bin/pip install -r requirements-dev.txt
./.venv/bin/uvicorn app.main:app --reload
```

Nothing to configure. `.env` is optional and only overrides `REQUEST_TIMEOUT`
and `LOG_LEVEL`. Open http://127.0.0.1:8000 for the playground, or `/docs` for
Swagger.

**Getting your cookie header:** log in to LinkedIn, F12 → Network → click any
`linkedin.com` request → Copy as cURL, then take everything after `Cookie: `.
Paste all of it. That header contains `li_at`, a complete account credential —
no password or 2FA needed to reuse it.

Logs print cookie **names only, never values**.

---

## API

### `POST /api/integrations/linkedin/profile`

No authentication. The LinkedIn cookies are the only credential, and they are
the caller's.

| Field | Type | | Notes |
|---|---|---|---|
| `url` | string | required | Any usual profile form — scheme optional, `www.` or a locale subdomain, trailing slash, tracking query string. Company and school URLs are rejected. |
| `cookie_header` | string | required | Your `Cookie` header, verbatim. Sent in the body, never the query string, so it stays out of logs, browser history and `Referer` headers. |
| `user_agent` | string | required | The browser the cookies came from. |

**`user_agent` has no default, deliberately.** LinkedIn binds a session to the
browser it issued it to. A mismatch does not fail — it returns 200 with correct
data and *then* invalidates the session, logging the account out. A wrong guess
is worse than an error, so none is guessed. The playground sends
`navigator.userAgent` for you.

<details>
<summary><b>Response</b></summary>

```json
{
  "profile": {
    "name": "Ada Lovelace",
    "headline": "Analyst, Analytical Engine",
    "location": "London, England, United Kingdom",
    "about": "Notes upon the Analytical Engine…",
    "profile_picture": "https://media.licdn.com/…/800_800/photo.jpg",
    "background_image": "https://media.licdn.com/…/1584_396/cover.jpg",
    "experience": [
      {
        "title": "Analyst",
        "company": "Analytical Engine Programme",
        "employment_type": "Full-time",
        "location": "London, England, United Kingdom",
        "description": "Translated and extended Menabrea's memoir.",
        "start_date": "1843-03",
        "end_date": null,
        "is_current": true
      }
    ],
    "education": [
      {
        "school": "Private Tuition",
        "degree": "Mathematics",
        "field_of_study": "Mathematics and Logic",
        "description": null,
        "activities": "Correspondence with De Morgan",
        "start_date": "1829",
        "end_date": "1835"
      }
    ],
    "skills": ["Algorithms", "Mathematics"],
    "certifications": [
      {
        "name": "Fellow of the Analytical Society",
        "authority": "Analytical Society",
        "license_number": "AS-1843",
        "url": "https://example.org/cert/AS-1843",
        "start_date": "1843-06",
        "end_date": null
      }
    ],
    "languages": [{ "name": "English", "proficiency": "NATIVE_OR_BILINGUAL" }]
  },
  "meta": {
    "source": "voyager-dash-profiles",
    "decoration_id": "com.linkedin.voyager.dash.deco.identity.profile.FullProfileWithEntities-103",
    "fetched_at": "2026-08-31T09:41:22.104Z",
    "duration_ms": 618
  }
}
```

Dates are `YYYY-MM`, or `YYYY` when only a year is recorded. A position with no
end date is current. A field the profile omits is `null`; an absent collection
is `[]`. Keys are never missing.

</details>

### Errors

```json
{ "error": { "code": "profile_not_found", "message": "…" } }
```

| Code | HTTP | Meaning |
|---|---|---|
| `invalid_request` | 422 | Body is malformed or a required field is missing |
| `invalid_profile_url` | 400 | Not a `linkedin.com/in/<slug>` URL |
| `profile_not_found` | 404 | No such profile, or not visible to this session |
| `session_expired` | 503 | The supplied cookies are stale |
| `upstream_error` | 502 | LinkedIn returned something unexpected |
| `upstream_timeout` | 504 | LinkedIn did not respond in time |

Match on `code`, not the status. LinkedIn serves **403 for both** a dead session
and an unreachable profile; only the response body separates them, and the
service does that for you.

`GET /` serves the playground, `GET /health` reports status and the decoration
in use. Both answer `HEAD` as well as `GET`, which platform health checks need.

---

## Approach

### Options considered

| Route | Outcome |
|---|---|
| Headless browser (Playwright, Selenium) | **Rejected.** Works, but slow, heavy to host, and puts a browser in the serving path. |
| Voyager `identity/profiles/{slug}/profileView` | **Dead.** Returns 410 Gone. This is what every tutorial and library uses, which is why they are all broken. |
| Voyager GraphQL (`voyagerIdentityDashProfiles`) | **Dropped.** The projection I could construct returned two usable fields. |
| Profile page RSC / SDUI payload | **Works, not chosen.** The page ships React Server Components; parsing that flight payload yielded full experience entries. But it is a *rendering* format — it changes whenever the UI does. |
| **Voyager `identity/dash/profiles`** | **Chosen.** One request returns a normalized entity graph: ~90 KB, ~105 entities covering the whole profile. |

The dash endpoint wins because it is a data contract rather than a view. It
returns `{data, included[]}` — a flat graph of entities referencing each other
by URN — so the parser resolves references once and every field is an extractor
over the same structure.

```
GET /voyager/api/identity/dash/profiles
      ?q=memberIdentity&memberIdentity={slug}
      &decorationId=…FullProfileWithEntities-103
```

### What makes it work

- **The user agent must match the browser the cookies came from.** This was the
  hardest to find, because a mismatch does not fail. Requests returned 200 with
  correct data, then the session was invalidated seconds later and the account
  logged out. Every check asking "did the request work" answered yes.
- **Send no `x-li-*` headers at all.** Fabricating tracking headers —
  `x-li-track`, `x-li-page-instance`, `x-li-pem-metadata` — produced a 302 back
  to the same URL carrying `clear-site-data: "storage"`. Trace-context headers
  look like an exception because a browser randomises them per request, but a
  page-forest id names a tree the server issued and the tracestate format is
  vendor-defined, so any value composed is invented. There is no exception.
- **`csrf-token` is the `JSESSIONID` value with its quotes stripped**, while the
  cookie keeps them. Getting this wrong produces a 403 indistinguishable from an
  expired session.
- **Do not follow redirects.** A 3xx is the answer, not a detour; following them
  loops thirty times.
- **Send the whole cookie header.** `li_at` and `JSESSIONID` are enough for a
  request to succeed; the rest cost nothing to carry.

### What turned out not to matter

- **TLS fingerprinting.** `httpx` over plain OpenSSL returns byte-identical
  results to `curl_cffi` with Chrome impersonation, measured both while blocked
  and while succeeding. No `curl_cffi`, no C extensions — five runtime
  dependencies.
- **HTTP/2.** Another implementation carries an `h2` dependency and a comment
  claiming LinkedIn's WAF blocks HTTP/1.1 instantly. HTTP/1.1 returns 200 with
  131,722 bytes.

### How it was found

`tools/browser_console_probe.js` makes the same request from a logged-in page's
own JavaScript. That removes the session as a variable — same origin, same
cookies, same TLS — so whatever comes back is the endpoint's real answer. It is
how `profileView`'s 410 was confirmed and the working decoration identified, and
it is how to find the next decoration when this one rotates.

---

## Testing

```bash
./.venv/bin/pytest
```

146 tests. The ones worth knowing about:

- **No `x-li-*` header is ever sent** — a regression guard, because that mistake
  cost three LinkedIn sessions.
- **`user_agent` has no default** — asserted on the constructor signature, so a
  well-meaning fallback cannot creep back in.
- **`csrf-token` is unquoted while the cookie keeps its quotes.**
- **3xx is checked before 4xx** in status mapping; the ordering is load-bearing.
- **A 403 carrying `VoyagerUserVisibleException` is 404, not 503** — conflating
  them sends operators off re-copying cookies that were fine.
- **Cookies are never passed per-request to httpx** — it would merge them with
  the jar and send each twice, which LinkedIn reads as a hijacked session.
  Invisible at runtime: no error, just dead sessions.

---

## Deployment

The `Dockerfile` is the whole contract: the container reads `PORT` and needs no
configuration, because callers bring their own cookies.

**Render** — `render.yaml` is committed, so use **New → Blueprint** and point it
at the repo. By hand: runtime **Docker**, Dockerfile path `./Dockerfile`, health
check path `/health`, no start command. On the free plan the instance sleeps
after ~15 minutes idle and the first request afterwards takes up to a minute.

**Cloud Run** — `gcloud run deploy lin-scrapper --source . --region us-central1
--allow-unauthenticated`, from the same Dockerfile.

**Locally** — `docker build -t lin-scrapper . && docker run -p 8080:8080
lin-scrapper`. Python 3.12 slim, non-root, ~159 MB, no test dependencies.

The URL is public and the API has no auth of its own — deliberate, so it can be
tried without being issued a key. Since the service stores no credentials, what
is exposed is compute.

---

## Limits of the approach

Inherent to replaying a browser session against an unofficial API. None of these
is fixable by better code.

- **It needs a real logged-in account.** No anonymous mode, no programmatic
  login. When cookies expire they are copied again by hand.
- **Results depend on who is asking.** LinkedIn varies profile data by network
  degree, so the same URL fetched with two sessions can return different fields.
  Out-of-network and private profiles come back as `profile_not_found`.
  *Untested* — I only ever fetched with one account.
- **The session is bound to one browser.** Cookies and user agent must travel
  together, so a session cannot be moved between machines or shared.
- **No contract, no notice.** `profileView` returned 410 mid-2025 and broke every
  library built on it; this endpoint can go the same way, and the decoration
  rotates on its own schedule.
- **It does not scale, and the obvious workarounds are what get accounts
  banned.** One session, sequential requests. Pooling accounts or renting
  residential proxies is where this stops being a technical exercise.
- **Detection is partly out of reach.** `_pxvid` in the cookie jar shows
  PerimeterX is involved, and it fingerprints via JavaScript the browser
  executes. No HTTP-level fidelity reaches that.

In production the answer is an official data source — LinkedIn's partner APIs or
a licensed provider — which is precisely why those exist.

## Limits of this implementation

Scope and quality gaps — fixable, just not done.

- **The decoration will rotate.** `DECORATION_ID` is the most fragile value
  here. Symptoms are a 410 or an empty `included[]`; the console probe finds the
  replacement.
- **Skills are capped at ~20** by the primary call. Complete lists need the
  per-section endpoints (`profileSkills`, `profileLanguages`, …), one request
  each.
- **Not extracted:** honours, projects, volunteering, publications,
  recommendations. Each is one more extractor over data already fetched.
- **Body string-matching is brittle.** Separating an unreachable profile from a
  dead session relies on LinkedIn's error wording, which will change.
- **One synthetic fixture.** It covers reference cycles and dangling refs a real
  response does not reliably contain, but nothing in CI proves the extractors
  against genuine data.
- **`certifications` is unverified** — the profiles tested against had none.
- **No caching, rate limiting or auth.**
- **Datacenter egress is untested.** Every measurement came from a residential
  connection, and LinkedIn treats cloud ASNs more harshly.
