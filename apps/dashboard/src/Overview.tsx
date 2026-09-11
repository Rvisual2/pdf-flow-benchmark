import { ArrowDownToLine, ArrowDownRight, ArrowUpRight, SlidersHorizontal } from 'lucide-react';
import { parserColor, scoreLabel, type Benchmark } from './data';
import { Filters } from './Filters';
import { filterDocuments, scoreTone, spread, type Filters as FilterState } from './triage';

export function Overview({
  data,
  filters,
  onFilters,
  onExplore,
}: {
  data: Benchmark;
  filters: FilterState;
  onFilters: (filters: FilterState) => void;
  onExplore: (page: number, parser: string) => void;
}) {
  const documents = filterDocuments(data, filters);
  const providers = [...data.providers].sort((a, b) => b.score - a.score);
  function downloadScores() {
    const quote = (value: string | number) => `"${String(value).replaceAll('"', '""')}"`;
    const rows = [
      ['Document', 'Category', 'Scored snippets', ...providers.map((p) => p.name)],
      ...documents.map((doc) => [
        `page_${doc.page}.pdf`,
        data.categories[doc.category] ?? doc.category,
        doc.scoredSnippets,
        ...providers.map((p) => doc.scores[p.id] ?? ''),
      ]),
    ];
    const url = URL.createObjectURL(
      new Blob([rows.map((row) => row.map(quote).join(',')).join('\n')], {
        type: 'text/csv;charset=utf-8',
      }),
    );
    const anchor = document.createElement('a');
    anchor.href = url;
    anchor.download = 'flowbench-filtered-documents.csv';
    anchor.click();
    URL.revokeObjectURL(url);
  }
  return (
    <div className="page">
      <div className="page-heading">
        <div>
          <div className="eyebrow">PARSER EVALUATION / DEBUG WORKSPACE</div>
          <h1>Find the failure. Inspect the evidence.</h1>
          <p className="subtitle">
            Compare every tool on every document. Open a score to see exactly what matched ground
            truth.
          </p>
        </div>
        <button className="button secondary" onClick={downloadScores}>
          <ArrowDownToLine size={16} /> Export filtered CSV
        </button>
      </div>
      <section className="provider-overview" aria-label="Overall parser scores">
        {providers.map((provider, index) => (
          <button
            key={provider.id}
            className={`provider-card ${filters.provider === provider.id ? 'active' : ''}`}
            onClick={() =>
              onFilters({ ...filters, provider: provider.id, band: 'all', sort: 'worst' })
            }
            aria-pressed={filters.provider === provider.id}
          >
            <span className="provider-card-top">
              <i style={{ background: parserColor(provider.id) }} />
              {provider.service}
              <span>#{index + 1}</span>
            </span>
            <strong>{provider.name}</strong>
            <div className="provider-card-score">
              {scoreLabel(provider.score)}
              <small>/ 100</small>
            </div>
            <div className="score-track">
              <span style={{ width: `${provider.score}%`, background: parserColor(provider.id) }} />
            </div>
            <span className="card-action">
              Inspect weakest documents <ArrowDownRight size={13} />
            </span>
          </button>
        ))}
      </section>
      <div className="benchmark-caption">
        Overall FATA · weighted by retained snippets · {data.scoredDocuments} scored documents ·{' '}
        {data.scoredSnippets.toLocaleString()} scored snippets
      </div>
      <section className="card matrix-section">
        <div className="section-heading">
          <div>
            <h2>
              <SlidersHorizontal size={18} /> Document score matrix
            </h2>
            <p>Start with an outlier, then compare its ground-truth matches.</p>
          </div>
          <div className="quick-filters" aria-label="Triage shortcuts">
            <button
              aria-pressed={filters.band === 'low'}
              onClick={() => onFilters({ ...filters, band: 'low', sort: 'worst' })}
            >
              Low scores &lt;75
            </button>
            <button
              aria-pressed={filters.band === 'high'}
              onClick={() => onFilters({ ...filters, band: 'high', sort: 'best' })}
            >
              High scores ≥95
            </button>
            <button
              aria-pressed={filters.sort === 'spread'}
              onClick={() => onFilters({ ...filters, band: 'all', sort: 'spread' })}
            >
              Tool disagreements
            </button>
          </div>
        </div>
        <Filters data={data} value={filters} onChange={onFilters} />
        <div className="matrix-caption">
          <span aria-live="polite">
            <strong>{documents.length}</strong> of {data.documents.length} documents
            {filters.provider === 'all' && filters.band !== 'all'
              ? ' · Every tool must match the filter'
              : ''}
          </span>
          <div className="score-legend">
            <span>
              <i className="low" /> &lt;75
            </span>
            <span>
              <i className="mid" /> 75–95
            </span>
            <span>
              <i className="high" /> ≥95
            </span>
            <span>— Unscored</span>
          </div>
        </div>
        <div className="table-scroll matrix-scroll">
          <table className="score-matrix">
            <thead>
              <tr>
                <th scope="col" className="sticky-column">
                  Document / category
                </th>
                {providers.map((provider) => (
                  <th
                    scope="col"
                    key={provider.id}
                    aria-sort={
                      filters.provider === provider.id && ['worst', 'best'].includes(filters.sort)
                        ? filters.sort === 'worst'
                          ? 'ascending'
                          : 'descending'
                        : 'none'
                    }
                  >
                    <button
                      className={filters.provider === provider.id ? 'active' : ''}
                      onClick={() =>
                        onFilters({
                          ...filters,
                          provider: provider.id,
                          sort:
                            filters.provider === provider.id && filters.sort === 'worst'
                              ? 'best'
                              : 'worst',
                        })
                      }
                    >
                      <i style={{ background: parserColor(provider.id) }} />
                      {provider.name}
                      {filters.provider === provider.id &&
                        ['worst', 'best'].includes(filters.sort) && (
                          <span>{filters.sort === 'worst' ? '↑' : '↓'}</span>
                        )}
                    </button>
                  </th>
                ))}
                <th scope="col" title="Highest minus lowest tool score, in points">
                  Spread
                </th>
              </tr>
            </thead>
            <tbody>
              {documents.map((doc) => (
                <tr key={doc.page}>
                  <th scope="row" className="sticky-column">
                    <button
                      className="document-link"
                      onClick={() =>
                        onExplore(
                          doc.page,
                          providers.find((p) => p.id === filters.provider)?.id ??
                            [...providers].sort(
                              (a, b) =>
                                (doc.scores[a.id] ?? Infinity) - (doc.scores[b.id] ?? Infinity),
                            )[0].id,
                        )
                      }
                    >
                      <span>
                        page_{doc.page}.pdf <ArrowUpRight size={13} />
                      </span>
                      <small>
                        {data.categories[doc.category] ?? doc.category} · {doc.scoredSnippets}{' '}
                        scored snippets
                      </small>
                    </button>
                  </th>
                  {providers.map((provider) => (
                    <td key={provider.id}>
                      <button
                        className={`score-cell ${scoreTone(doc.scores[provider.id])}`}
                        aria-label={`Inspect page_${doc.page}.pdf with ${provider.name}: ${scoreLabel(doc.scores[provider.id])}`}
                        onClick={() => onExplore(doc.page, provider.id)}
                      >
                        {doc.scores[provider.id] == null
                          ? '—'
                          : scoreLabel(doc.scores[provider.id])}
                      </button>
                    </td>
                  ))}
                  <td className="spread-cell">{spread(doc)?.toFixed(1) ?? '—'}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        {!documents.length && (
          <div className="empty">
            <h3>No documents match</h3>
            <p>Adjust the score range, tool, or category to broaden your search.</p>
          </div>
        )}
        <div className="matrix-footer">
          Click any score to open its ground-truth diff.
          <span>FATA similarity · 0–100 · Higher is better</span>
        </div>
      </section>
      <details className="methodology card">
        <summary>Scoring methodology & snapshot details</summary>
        <p>{data.methodology}</p>
        <p>
          Low (&lt;75) and high (≥95) are browsing thresholds. They do not change evaluation scores.
        </p>
        <p>
          Release: {data.release} · Exported {new Date(data.generatedAt).toLocaleString()}
        </p>
        <div className="table-scroll">
          <table>
            <caption>Scores by category · retained-snippet means</caption>
            <thead>
              <tr>
                <th>Category</th>
                {providers.map((p) => (
                  <th key={p.id}>{p.name}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {[...new Set(data.documents.map((d) => d.category))].map((category) => (
                <tr key={category}>
                  <th>{data.categories[category] ?? category}</th>
                  {providers.map((p) => (
                    <td key={p.id}>{scoreLabel(p.categories[category])}</td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </details>
    </div>
  );
}
