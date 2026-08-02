# Third-party licences

The MIT licence in `LICENSE` covers the code in this repository. It does **not** cover the
dependencies this code installs at runtime. Read this file before you use the project for
anything beyond personal research.

## `vnstock` — proprietary, personal use only

`vnstock` (and the `vnstock_data` / `vnstock_news` premium tiers) is **not** open source.
It ships under the "Vnstock License Agreement", Copyright (c) 2024 Thinh Vu @ Vnstock.
The terms that matter:

- **Personal use only.** Research and modification for your own purposes are free.
- **No redistribution.** You may not copy, redistribute, or repackage the library.
- **No commercial use.** Use by any organisation, or any use that directly or indirectly
  produces revenue, requires written permission from the author.

The full text ships with the package, at
`.venv/lib/python3.12/site-packages/vnstock-*.dist-info/licenses/LICENSE.md`.

### What this means for this repository

- Installing and running this project for personal research is fine.
- Running it commercially is **not**, unless you obtain permission from the vnstock author.
- `vnstock-api/` wraps the library in an HTTP service. Serving that endpoint to other
  people redistributes vnstock's output. Keep it private: set `VNSTOCK_API_KEY`, set
  `VNSTOCK_ALLOWED_ORIGINS` to your own origins, and do not expose it publicly.
  `GET /stream/prices` is unauthenticated by design (browsers cannot send headers on an
  `EventSource` request) — put it behind your own proxy or network restriction.

`vnstock_data` and `vnstock_news` (used by `vnstock-api/`) are the paid Insiders tiers,
governed by a separate subscription agreement, not by the library licence above. You need
your own subscription. No credentials for one are included here.

`vnstock_ezchart`, a hard dependency of `vnstock`, is separately **MIT** (Copyright (c)
2024 Vnstock) and is not covered by the restrictions above.

## `vnai` — proprietary, with telemetry and a terms prompt

`vnai` installs automatically with `vnstock` (`Requires-Dist: vnai>=2.3.9`). It is marked
`License: proprietary` and ships **no licence text at all**. Two things it does that you
should know before running this project:

- **It requires accepting terms on first run.** It writes `~/.vnstock/id/terms_agreement.txt`
  and prompts interactively if you have not accepted. Set `ACCEPT_TC="tôi đồng ý"` or the
  pipeline blocks on stdin in CI.
- **It phones home.** It contacts `vnstocks.com` and `hq.vnstocks.com` for device
  registration, licence verification, analytics, and profile sync. Running this project
  registers your device with a third party.

## Other dependencies worth naming

Nothing below imposes copyleft obligations on this repository's own code — none of these
libraries is modified or redistributed here — but the set is not uniformly permissive:

| Package | Licence | Comes in via |
|---|---|---|
| `vnai` | proprietary, no text shipped | `vnstock` |
| `frozendict` | **LGPL-3.0** | `yfinance` |
| `certifi` | MPL-2.0 | `requests`, `httpx` |
| `tqdm` | MPL-2.0 AND MIT | `transformers`, `openai` |
| `docutils` | mixed, includes GPL-classified files | `fastmcp` → `cyclopts` → `rich-rst` |
| `matplotlib` | custom PSF-style licence | `vnstock_ezchart` |
| `nvidia-*` (17 packages), `cuda-bindings` | **NVIDIA proprietary EULA** | `torch` ← `sentence-transformers`, on Linux |

Everything else resolves to MIT, Apache-2.0, BSD, or ISC. Resolved versions are pinned in
`uv.lock` and `web/pnpm-lock.yaml`; run `uv pip list` or `pnpm list` for the authoritative set.

## Vendored source

### shadcn/ui — MIT, Copyright (c) 2023 shadcn

`web/src/components/ui/` (badge, button, card, chart, collapsible, dialog, dropdown-menu,
input, label, popover, select, sheet, skeleton, table, tabs, textarea, tooltip) and the
`@theme inline` token block in `web/src/styles/globals.css` are shadcn/ui registry
components, copied into this repo rather than installed as a dependency.

```
Permission is hereby granted, free of charge, to any person obtaining a copy of this
software and associated documentation files (the "Software"), to deal in the Software
without restriction, including without limitation the rights to use, copy, modify, merge,
publish, distribute, sublicense, and/or sell copies of the Software, and to permit persons
to whom the Software is furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all copies or
substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR IMPLIED,
INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY, FITNESS FOR A PARTICULAR
PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT HOLDERS BE LIABLE
FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR
OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER
DEALINGS IN THE SOFTWARE.
```

### lightweight-charts — Apache-2.0, Copyright (c) TradingView, Inc.

Used as a dependency, not vendored. If you distribute a built bundle, Apache-2.0 §4(d)
requires you to carry its NOTICE. The TradingView attribution logo is left enabled.

## News sources

`vnstock-api/news.py` and `scripts/data/articles_intl/feeds.py` fetch RSS and crawl
sitemaps from third-party publishers: cafebiz, vietstock, vnexpress, vneconomy, baodautu,
CNBC, MarketWatch, OilPrice, and Nikkei Asia. Headlines and summaries are cached in the
database indefinitely.

No article text is committed to this repository — publishing it ships the fetcher, not a
corpus. Two things are on you as the operator: those publishers' terms of service and
`robots.txt` govern your use, and redistributing anything you cache is your
responsibility, not this project's. Note also that both fetchers send a browser-style
`User-Agent` because at least one source returns empty results without one.

## Not financial advice

This project is published for its engineering. Nothing in it is investment advice, and
the authors accept no liability for losses arising from its use.
