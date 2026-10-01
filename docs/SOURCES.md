# Source registry and provenance

Prepared 30-09-2026. This is a starting collection, not a claim of exhaustive industry coverage.

## Enabled endpoints

| Source | Type | Focus |
|---|---|---|
| The Beat | RSS | US-led comics trade coverage |
| Publishers Weekly, Comics | RSS | Comics publishing/business, including North American coverage |
| downthetubes | RSS | UK-led comics news |
| Broken Frontier | RSS | Independent comics and UK-led coverage |
| Zona Negativa | RSS, Spanish | Spanish/EU comics coverage |
| BDZoom | RSS, French | French-language/EU comics coverage |
| GlobalComix Headquarters | HTML announcement index | Official product/company developments |
| GlobalComix Partnerships | HTML announcement index | Official partnership developments |
| WEBTOON investor/company news | HTML announcement index | Official company announcements |
| WEBTOON English notices | HTML notice index | Reader/creator-facing product and service changes |

Exact URLs and HTML URL patterns live in `config/sources.json`. HTML indices are scanned for qualifying article links and dates; article dates are additionally sought in metadata. No JavaScript execution or logged-in browsing is used.

Browser research could read GlobalComix Headquarters and WEBTOON announcement/notice indices. Several feed requests returned a recognised RSS/XML content type that the research browser could not display; that is not the same as a parsed, validated feed. The Publishers Weekly comics feed was returned as a text feed in search. The GlobalComix partnership route is included as an initial endpoint and still needs the same runner-level validation as every other source.

Initial build-environment requests failed DNS resolution. Subsequently, the user's source-check report dated 30-09-2026 recorded nine successful endpoints out of ten, with Publishers Weekly reporting `robots_disallowed_or_unavailable`. This was one source-only run, not a live editorial acceptance test. The bounded collection update was tested offline with synthetic fixtures, not newly fetched website markup. Use a fresh `check-sources` run and a preview before enabling the schedule. Source endpoints, access policies and publication formats can change.

## Disabled candidates and gaps

ActuaBD returned HTTP 403 to browser retrieval. Drawn & Quarterly's news page returned HTTP 503 and its feed was not verified. Both are present but disabled. They must be verified before enabling; no attempt is made to evade restrictions.

Canadian coverage is initially indirect through broader comics trade reporting. Our source list does not yet provide robust dedicated coverage of Canadian publishers. EU coverage begins with French and Spanish reporting, not every EU language or national market. Asian/Latin American developments are primarily encountered when covered by the configured English/EU sources or the official company pages. There is no claim to comprehensive domestic Asian or Latin American monitoring.

There is no paid search API, social-media listening, email-newsletter ingestion, authenticated publisher/paywall account, or search-engine scraping. A newer company can be discovered in trade coverage without appearing on the watchlist, but an unreported event outside our sources can be missed.

## Platform directory

`config/watchlist.json` includes 36 named entries from the user-provided **Existing platforms.pdf**, plus 18 explicitly labelled additional monitoring seeds. Only names and aliases were imported. The document's company descriptions, prices, acquisition claims, statistics and operating statuses were **not** adopted as verified facts.

The PDF's opening reliability note states that only a listed subset was rechecked in August 2026 and that other entries are unverified and may be out of date. Inclusion on the watchlist is therefore not an assertion that a company remains active. Each new story must stand on retrieved current source material.

User-derived seeds have `origin: user_platform_directory`. Added industry seeds have `origin: additional_monitoring_seed`. Both use `status: not_asserted`. Broad names, such as Patreon, only qualify when the current story has a direct comics-industry connection.

## Access and copyright handling

The collector honours robots exclusions, uses modest concurrency and per-host pacing, and does not bypass paywalls or bot challenges. Unavailable robots instructions are treated conservatively as a reason not to fetch. This can reduce coverage on temporarily failing sites.

A detected paywall restricts input to publicly supplied feed/metadata previews. A failed article request may still provide a clearly labelled feed excerpt. Headlines without sufficient accompanying evidence are not given substantive generated summaries. Source excerpts are transient processing inputs, not a public article archive. The email contains paraphrases, attribution and direct links. Supporting quotes used by validation are capped and are not displayed in the newsletter.

Access labels describe what the program retrieved, not a guarantee that a reader in another location can access the same page. HTML extraction is heuristic and may be incomplete. Undated material is omitted instead of being described as newly published.

## Adding a source

1. Find the publisher's own feed or announcement index, not an invented URL.
2. Add an entry to `config/sources.json` with `enabled: true`, type, region, language and source kind. For HTML indices also supply an article-URL pattern restrictive enough to avoid navigation links.
3. Run `check-sources` and verify dated article detection, useful public text and acceptable access policy.
4. Run a preview and verify the source improves relevance rather than creating routine-release noise.

Adding a watchlist name is not the same as adding a source. The former helps selection; the latter determines what can actually be collected.
