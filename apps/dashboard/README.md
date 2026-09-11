# FlowBench dashboard

A React + TypeScript workspace for comparing PDF-to-Markdown parsers. Vite builds a
static site; no API server, account, or provider credentials are needed to browse it.

[Open the live dashboard](https://pdf-flow-benchmark.vercel.app).

## Run locally

Use Node.js 22.12+ (or 24+) and npm:

```bash
cd apps/dashboard
npm ci
npm run dev
```

Open the URL printed by Vite. `npm run build` checks TypeScript and creates `dist/`;
`npm run preview` serves that build. `npm run format:check` checks formatting. `npm test` checks filtering and ranking contracts.
PDF.js font, character-map, and image-decoder assets are copied from the pinned
package before development and production builds; generated copies are ignored.

## Explore

- **Score matrix:** every document × every tool, colored by similarity. Click any score
  to open that exact document and parser in the ground-truth diff. Overall parser cards
  focus the matrix on that tool's weakest documents. Column headings toggle score order.
- Filter by document name, category, and **one tool, any tool, or every tool**.
  Find low scores (<75), high scores (≥95), a custom inclusive range, or unscored documents.
  Sort by lowest score, highest score, largest tool disagreement, or document number.
  Low/high cutoffs are browsing aids and do not change FATA evaluation.
- **Export filtered CSV** downloads the visible document set, with all parser scores.
- **Document inspector:** full-width document previews show category and score beneath
  each page, with filenames reserved for accessibility labels. The filtered queue stays
  available while debugging. Use
  Alt+left/right to move through it. Selecting a tool changes the inspection target;
  the separate “Score for” filter controls which documents remain in the queue.
- **Ground-truth diff** is the default inspection view. Choose a reference (worst match
  first by default) and compare its exact text with the evaluator's closest match.
  Switch between character/word highlights, split/unified layouts, and changes-only
  view. Inspect each tool's score on the selected reference and optionally include
  filtered references. Ground truth consists of snippets, not a full-document transcript.
- **PDF + Markdown:** opens the original PDF and selected tool's full Markdown in
  equal-width panels. Switch tools or rendered/raw Markdown while checking the source;
  this view is preserved in the URL. Panels stack on narrow screens.
- **Full output:** rendered Markdown or raw source, original Markdown download, and
  parser configuration/provenance. **Show source PDF** opens the original beside any view.
- **Tool vs. tool:** compare two complete original Markdown outputs, swap sides,
  highlight words or characters, and fold unchanged lines.
- The URL preserves the document, tools, view, score filters, sorting, and selected
  reference for reproducible debugging links. Unscored documents remain inspectable.

Rendered Markdown supports GFM and sanitized HTML tables. Images are labeled
placeholders because external image assets are not part of the published Markdown
release. Rendering does not modify the text or scores used by the evaluator.

## Refresh the published snapshot

The tracked `public/data-source.json` points to an immutable, hash-verified JSON
snapshot in the existing artifact bucket. PDFs and Markdown load on demand from
that bucket, with size and SHA-256 checks. No raw artifacts are bundled in Git.

From the repository root, evaluate a complete published run, then export it:

```bash
uv run pdf-benchmark dashboard export \
  --evaluation-dir results/runs/evaluation \
  --run-dir results/runs/published-september \
  --release all-tools-2026-09-10 \
  --publish
```

`--run-dir` contains `<parser>/markdowns/page_<number>.md` and optional per-parser
`run.json` files. Parser IDs in the evaluation columns must match these directory
names and release manifest paths. Local outputs must match the published hashes;
the summary must agree with retained snippet scores. Download a release with
`pdf-benchmark results download --release ... --directory ...` if needed.

Without `--publish`, export only writes the snapshot under ignored
`results/runs/dashboard/`. Publishing uses the existing gcloud login, updates the
small data pointer, and requires rebuilding the site. Upload new parser outputs
as a results release before exporting their evaluation.

Browser reads require the bucket's read-only CORS configuration to allow `GET`
and `HEAD`. This does not grant listing or writing permissions.

## PDF thumbnails

The document list uses lazy-loaded color JPEG covers from the separate
`pdf-flow-thumbnails-hashiromer-20260910` bucket. Each image is capped at 320 pixels
on its longest edge, with JPEG quality 70. All 127 current PDFs have one page;
future multi-page inputs use the first page as their cover.

```bash
uv run pdf-benchmark dashboard thumbnails --publish
```

This command verifies the input PDF hashes, renders covers into ignored
`results/runs/thumbnails/`, uploads immutable images and their provenance manifest,
and updates the artifact catalog. `--long-edge`, `--quality`, `--input-dir`,
`--bucket`, and `--account` customize generation. Omit `--publish` for local output.
Run `dashboard export --publish` afterward and rebuild to refresh the dashboard.
The original PDFs remain available for detailed inspection.

## Code organization

`Overview.tsx` renders the score matrix; `Filters.tsx` and `triage.ts` share filter
controls and ranking logic; `DocumentExplorer.tsx` renders the inspection queue;
`GroundTruthPanel.tsx` compares references with evaluator matches; `MarkdownPanel.tsx` renders output and provenance; `DiffPanel.tsx` compares two outputs; `PdfPanel.tsx`
handles PDF.js lifecycle. `data.ts` defines the snapshot contract and verified,
deduplicated artifact loading. Heavy viewers load only when needed.

## Vercel deployment

The Vercel project `pdf-flow-benchmark` lives in the personal scope
`hashiromers-projects` and connects to
[Rvisual2/pdf-flow-benchmark](https://github.com/Rvisual2/pdf-flow-benchmark).
Its production branch is `main`, Root Directory is `apps/dashboard`, and Node.js
version is 24.x. `vercel.json` configures Vite, `npm ci`, `npm run build`, and the
`dist` output.

Vercel's native Git integration deploys dashboard changes on `main` to production
and creates previews for other branches. Its **Ignored Build Step** compares
`apps/dashboard/` with the last deployed commit on that branch. Changes elsewhere
in the repository skip the build. A first deployment always builds; comparing
against the last deployment also catches dashboard edits earlier in a multi-commit
push. Vercel records skipped pushes as canceled deployments; dependency
installation and the build command do not run, and the existing production
deployment stays live. No GitHub Actions workflow or Vercel token in GitHub
secrets is needed.

Changes to `public/data-source.json` count as dashboard changes, so publishing a
new evaluation and pushing its updated pointer refreshes the deployed results.
Python code, dataset files, and root documentation alone do not trigger a build.

Deploy `dist/` to any static host. Keep its `data-source.json` and `pdfjs/` assets.
