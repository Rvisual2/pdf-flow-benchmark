import { lazy, Suspense, useEffect, useRef, useState } from 'react';
import {
  ArrowLeft,
  ArrowLeftRight,
  ChevronLeft,
  ChevronRight,
  ExternalLink,
  FileText,
  PanelsTopLeft,
  ScanText,
} from 'lucide-react';
import { parserColor, scoreLabel, type Benchmark, type DocumentRecord } from './data';
import { Filters } from './Filters';
import { filterDocuments, focusScore, scoreTone, type Filters as FilterState } from './triage';
import { MarkdownPanel } from './MarkdownPanel';
const PdfPanel = lazy(() => import('./PdfPanel'));
const DiffPanel = lazy(() => import('./DiffPanel'));
const GroundTruthPanel = lazy(() => import('./GroundTruthPanel'));

export interface Selection {
  page: number;
  parsers: string[];
  mode: 'truth' | 'pdf-markdown' | 'outputs' | 'diff';
  snippet?: number;
}
export function DocumentExplorer({
  data,
  selection,
  onSelect,
  filters,
  onFilters,
  onBack,
}: {
  data: Benchmark;
  selection: Selection;
  onSelect: (selection: Selection) => void;
  filters: FilterState;
  onFilters: (filters: FilterState) => void;
  onBack: () => void;
}) {
  const [showPdf, setShowPdf] = useState(false);
  const pdfMarkdown = selection.mode === 'pdf-markdown';
  const pdfVisible = pdfMarkdown || showPdf;
  const queue = useRef<HTMLDivElement>(null);
  const documents = filterDocuments(data, filters);
  const current = data.documents.find((doc) => doc.page === selection.page) ?? data.documents[0];
  const position = documents.findIndex((doc) => doc.page === current.page);
  const activeProvider =
    data.providers.find((provider) => provider.id === selection.parsers[0]) ?? data.providers[0];
  useEffect(() => {
    const container = queue.current;
    const selected = container?.querySelector<HTMLElement>('[aria-current="true"]');
    if (!container || !selected) return;
    const bounds = container.getBoundingClientRect();
    const item = selected.getBoundingClientRect();
    if (container.scrollHeight > container.clientHeight) {
      if (item.top < bounds.top) container.scrollTop += item.top - bounds.top;
      else if (item.bottom > bounds.bottom) container.scrollTop += item.bottom - bounds.bottom;
    }
    if (container.scrollWidth > container.clientWidth) {
      if (item.left < bounds.left) container.scrollLeft += item.left - bounds.left;
      else if (item.right > bounds.right) container.scrollLeft += item.right - bounds.right;
    }
  }, [current.page, filters]);
  function selectDocument(page: number) {
    onSelect({ ...selection, page, snippet: undefined });
  }
  function move(offset: number) {
    const next = position >= 0 ? documents[position + offset] : undefined;
    if (next) selectDocument(next.page);
  }
  function selectProvider(id: string) {
    onSelect({
      ...selection,
      parsers: [id, ...selection.parsers.filter((other) => other !== id)].slice(0, 2),
    });
  }
  useEffect(() => {
    function onKey(event: KeyboardEvent) {
      if (event.altKey && ['ArrowLeft', 'ArrowRight'].includes(event.key)) {
        event.preventDefault();
        move(event.key === 'ArrowRight' ? 1 : -1);
      }
    }
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  });
  return (
    <div className="explorer">
      <aside className="document-list">
        <button className="back-button" onClick={onBack}>
          <ArrowLeft size={16} /> Score matrix
        </button>
        <Filters data={data} value={filters} onChange={onFilters} compact />
        <div className="list-caption">
          <span aria-live="polite">{documents.length} DOCUMENTS</span>
          <span>
            {filters.sort === 'spread'
              ? 'SPREAD'
              : filters.sort === 'best'
                ? 'BEST SCORE'
                : 'LOWEST SCORE'}
          </span>
        </div>
        <div className="document-scroll" ref={queue}>
          {documents.map((doc) => (
            <button
              className={`document-item ${doc.page === current.page ? 'selected' : ''}`}
              key={doc.page}
              aria-current={doc.page === current.page ? 'true' : undefined}
              aria-label={`Inspect page_${doc.page}.pdf · ${data.categories[doc.category] ?? doc.category} · ${filters.sort === 'spread' ? 'spread' : 'score'} ${focusScore(doc, filters)?.toFixed(1) ?? 'unscored'}`}
              onClick={() => selectDocument(doc.page)}
            >
              <DocumentThumbnail document={doc} />
              <span className="document-item-caption">
                <span>{data.categories[doc.category] ?? doc.category}</span>
                <span
                  className={`queue-score ${filters.sort === 'spread' ? '' : scoreTone(focusScore(doc, filters))}`}
                >
                  {focusScore(doc, filters)?.toFixed(1) ?? '—'}
                </span>
              </span>
            </button>
          ))}
          {!documents.length && (
            <p className="list-empty">No documents match. Adjust or reset the filters.</p>
          )}
        </div>
        <div className="queue-footer">
          <kbd>Alt</kbd> + <kbd>←</kbd> / <kbd>→</kbd> next document
        </div>
      </aside>
      <div className="document-workspace">
        <header className="document-toolbar">
          <div>
            <div className="eyebrow">DOCUMENT INSPECTOR</div>
            <h1>page_{current.page}.pdf</h1>
            <p>
              {data.categories[current.category] ?? current.category} <span>·</span>{' '}
              {current.scoredSnippets
                ? `${current.scoredSnippets} scored snippets`
                : 'Unscored document'}
            </p>
          </div>
          <div className="toolbar-actions">
            <button
              className="icon-button"
              aria-label="Previous document (Alt + left arrow)"
              disabled={position <= 0}
              onClick={() => move(-1)}
            >
              <ChevronLeft size={18} />
            </button>
            <span>
              {position >= 0 ? `${position + 1} of ${documents.length}` : 'Outside current filters'}
            </span>
            <button
              className="icon-button"
              aria-label="Next document (Alt + right arrow)"
              disabled={position < 0 || position >= documents.length - 1}
              onClick={() => move(1)}
            >
              <ChevronRight size={18} />
            </button>
            <a className="button secondary" href={current.pdf.url} target="_blank" rel="noreferrer">
              <ExternalLink size={14} /> Original PDF
            </a>
          </div>
        </header>
        {position < 0 && (
          <div className="outside-filter">
            This document is outside your current filters.
            {documents.length > 0 && (
              <button onClick={() => selectDocument(documents[0].page)}>
                Open first matching document <ChevronRight size={14} />
              </button>
            )}
          </div>
        )}
        <div className="document-provider-scores" aria-label="Tool scores for this document">
          {data.providers.map((provider) => (
            <button
              key={provider.id}
              aria-pressed={activeProvider.id === provider.id}
              onClick={() => selectProvider(provider.id)}
            >
              <span>
                <i style={{ background: parserColor(provider.id) }} />
                {provider.name}
              </span>
              <strong className={`score-badge ${scoreTone(current.scores[provider.id])}`}>
                {scoreLabel(current.scores[provider.id])}
              </strong>
            </button>
          ))}
        </div>
        <div className="workspace-modes">
          <div className="segmented" aria-label="Inspection mode">
            <button
              aria-pressed={selection.mode === 'truth'}
              onClick={() => onSelect({ ...selection, mode: 'truth' })}
            >
              <ScanText size={16} /> Ground-truth diff
            </button>
            <button
              aria-pressed={pdfMarkdown}
              onClick={() => onSelect({ ...selection, mode: 'pdf-markdown' })}
            >
              <PanelsTopLeft size={16} /> PDF + Markdown
            </button>
            <button
              aria-pressed={selection.mode === 'outputs'}
              onClick={() => onSelect({ ...selection, mode: 'outputs' })}
            >
              <FileText size={16} /> Full output
            </button>
            <button
              aria-pressed={selection.mode === 'diff'}
              onClick={() => {
                const pair = [
                  activeProvider.id,
                  selection.parsers[1] ??
                    data.providers.find((p) => p.id !== activeProvider.id)?.id,
                ].filter((id): id is string => !!id);
                onSelect({ ...selection, mode: 'diff', parsers: pair });
              }}
            >
              <ArrowLeftRight size={16} /> Tool vs. tool
            </button>
          </div>
          {!pdfMarkdown && (
            <label className="checkbox-label">
              <input
                type="checkbox"
                checked={showPdf}
                onChange={(event) => setShowPdf(event.target.checked)}
              />{' '}
              Show source PDF
            </label>
          )}
        </div>
        <div
          className={`comparison-area ${pdfVisible ? 'with-pdf' : ''} ${pdfMarkdown ? 'pdf-markdown' : ''}`}
        >
          {pdfVisible && (
            <Suspense fallback={<div className="panel-empty">Loading PDF viewer…</div>}>
              <PdfPanel key={current.pdf.sha256} artifact={current.pdf} />
            </Suspense>
          )}
          <Suspense fallback={<div className="panel-empty">Loading comparison…</div>}>
            {selection.mode === 'truth' ? (
              <GroundTruthPanel
                key={current.page}
                document={current}
                providers={data.providers}
                provider={activeProvider}
                snippetIndex={selection.snippet}
                onSnippet={(snippet) => onSelect({ ...selection, snippet })}
                onProvider={selectProvider}
              />
            ) : selection.mode === 'diff' ? (
              <DiffPanel
                document={current}
                providers={data.providers}
                pair={selection.parsers}
                onChange={(parsers) => onSelect({ ...selection, parsers })}
              />
            ) : (
              <MarkdownPanel
                key={`${current.page}-${activeProvider.id}`}
                provider={activeProvider}
                document={current}
              />
            )}
          </Suspense>
        </div>
      </div>
    </div>
  );
}
function DocumentThumbnail({ document }: { document: DocumentRecord }) {
  const [failed, setFailed] = useState(false);
  return (
    <span
      className="document-thumbnail"
      aria-hidden="true"
      style={{
        aspectRatio: document.thumbnail
          ? `${document.thumbnail.width} / ${document.thumbnail.height}`
          : '3 / 4',
      }}
    >
      {document.thumbnail && !failed ? (
        <img
          src={document.thumbnail.url}
          width={document.thumbnail.width}
          height={document.thumbnail.height}
          alt=""
          loading="lazy"
          decoding="async"
          onError={() => setFailed(true)}
        />
      ) : (
        <FileText size={20} />
      )}
    </span>
  );
}
