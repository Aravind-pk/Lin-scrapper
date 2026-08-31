/*
 * In-browser endpoint probe.
 *
 * This is the diagnostic that should be run FIRST, not tenth. Every test from
 * our own HTTP client confounds two questions — does the endpoint still serve
 * profiles, and does LinkedIn accept our replay of a browser session? A 302 is
 * consistent with either, which is why four rounds of probing did not converge.
 *
 * Running from the page's own JavaScript removes the second variable entirely:
 * same origin, same cookies, same TLS, the same client LinkedIn issued the
 * session to. Whatever comes back is the endpoint's real answer.
 *
 * USE
 *   1. Open a logged-in linkedin.com tab.
 *   2. F12 -> Console.
 *   3. Paste this file, press Enter, read the table.
 *
 * This is investigation, not the product. The service never puts a browser in
 * the request path.
 */

(async () => {
  const SLUG = prompt("Profile slug to probe (the part after /in/)", "");
  if (!SLUG) return;

  const BASE = "https://www.linkedin.com/voyager/api";
  const DECO = "com.linkedin.voyager.dash.deco.identity.profile";

  const targets = [
    ["CONTROL /me", `${BASE}/me`],
    ["legacy profileView", `${BASE}/identity/profiles/${SLUG}/profileView`],
    ["dash/profiles -103", dash(`${DECO}.FullProfileWithEntities-103`)],
    ["dash/profiles -93", dash(`${DECO}.FullProfileWithEntities-93`)],
    ["dash/profiles undecorated", dash(null)],
  ];

  function dash(decorationId) {
    const q = new URLSearchParams({ q: "memberIdentity", memberIdentity: SLUG });
    if (decorationId) q.set("decorationId", decorationId);
    return `${BASE}/identity/dash/profiles?${q}`;
  }

  // The csrf-token header is JSESSIONID with its quotes stripped, while the
  // cookie keeps them. The asymmetry is real; four implementations have now
  // independently derived it.
  const jsessionid = document.cookie
    .split("; ")
    .find((c) => c.startsWith("JSESSIONID="))
    ?.split("=")[1]
    ?.replace(/"/g, "");

  if (!jsessionid) {
    console.error("No JSESSIONID cookie — are you logged in on this tab?");
    return;
  }

  const rows = [];
  for (const [name, url] of targets) {
    try {
      const res = await fetch(url, {
        credentials: "include",
        redirect: "manual",
        headers: {
          "csrf-token": jsessionid,
          accept: "application/vnd.linkedin.normalized+json+2.1",
          "x-restli-protocol-version": "2.0.0",
        },
      });
      const body = await res.text();
      let included = 0;
      try {
        included = (JSON.parse(body).included || []).length;
      } catch {}
      rows.push({
        endpoint: name,
        // redirect:"manual" reports an opaque redirect rather than 302. That
        // still separates it from 410 and 200, which is all we need here.
        status: res.type === "opaqueredirect" ? "redirect" : res.status,
        bytes: body.length,
        included,
      });
    } catch (err) {
      rows.push({ endpoint: name, status: "error", bytes: 0, included: String(err) });
    }
    await new Promise((r) => setTimeout(r, 3000));
  }
  console.table(rows);
})();
