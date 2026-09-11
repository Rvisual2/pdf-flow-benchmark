import { useState } from 'react';
import ReactDiffViewer, { DiffMethod } from 'react-diff-viewer-continued';
import { CheckCheck, ChevronLeft, ChevronRight, Info } from 'lucide-react';
import { scoreLabel, type DocumentRecord, type Provider } from './data';
import { scoreTone } from './triage';

export default function GroundTruthPanel({
  document,
  providers,
  provider,
  snippetIndex,
  onSnippet,
  onProvider,
}: {
  document: DocumentRecord;
  providers: Provider[];
  provider: Provider;
  snippetIndex?: number;
  onSnippet: (index: number) => void;
  onProvider: (id: string) => void;
}) {
  const [includeExcluded, setIncludeExcluded] = useState(() =>
    document.snippets.some((snippet) => snippet.index === snippetIndex && !snippet.retained),
  );
  const [order, setOrder] = useState('worst');
  const [granularity, setGranularity] = useState<'words' | 'characters'>('characters');
  const [split, setSplit] = useState(true);
  const [changesOnly, setChangesOnly] = useState(false);
  const snippets = document.snippets
    .filter((snippet) => includeExcluded || snippet.retained)
    .sort((a, b) =>
      order === 'source'
        ? a.index - b.index
        : (b.matches[provider.id]?.distance ?? 1) - (a.matches[provider.id]?.distance ?? 1) ||
          a.index - b.index,
    );
  const selected = snippets.find((snippet) => snippet.index === snippetIndex) ?? snippets[0];
  const position = snippets.findIndex((snippet) => snippet.index === selected?.index);
  const match = selected?.matches[provider.id];
  const score = match ? (1 - match.distance) * 100 : null;
  return (
    <section className="truth-panel card">
      <div className="truth-heading">
        <div>
          <h2>Ground-truth matches</h2>
          <p>Reference snippets vs. the closest text found by the evaluator.</p>
        </div>
        <span className="pill">
          {document.scoredSnippets} scored / {document.snippets.length} references
        </span>
      </div>
      <div className="evidence-note">
        <Info size={15} />
        <span>
          Ground truth contains snippets, not a full Markdown document. Each diff shows the exact
          scored match; reference extraction may contain errors.
        </span>
      </div>
      <div className="snippet-controls">
        <label className="checkbox-label">
          <input
            type="checkbox"
            checked={includeExcluded}
            onChange={(event) => setIncludeExcluded(event.target.checked)}
          />{' '}
          Include filtered references
        </label>
        <label className="inline-field">
          Order
          <select
            aria-label="Snippet order"
            value={order}
            onChange={(event) => setOrder(event.target.value)}
          >
            <option value="worst">Worst match first</option>
            <option value="source">Reference order</option>
          </select>
        </label>
      </div>
      {!selected ? (
        <div className="panel-empty">
          <h3>{document.snippets.length ? 'No scored references' : 'No ground truth available'}</h3>
          <p>
            {document.snippets.length
              ? 'Include filtered references to investigate why this document was excluded.'
              : 'Inspect the source PDF and parser outputs using the other views.'}
          </p>
        </div>
      ) : (
        <>
          <div className="snippet-strip" aria-label="Reference snippets">
            {snippets.map((snippet) => {
              const match = snippet.matches[provider.id];
              const value = match ? (1 - match.distance) * 100 : null;
              return (
                <button
                  key={snippet.index}
                  aria-pressed={selected.index === snippet.index}
                  className={`snippet-chip ${scoreTone(value)}`}
                  onClick={() => onSnippet(snippet.index)}
                  title={snippet.text}
                  aria-label={`Reference ${snippet.index}, similarity ${scoreLabel(value)}${snippet.retained ? '' : ', filtered'}`}
                >
                  <span>
                    #{snippet.index}
                    {!snippet.retained && ' · filtered'}
                  </span>
                  <strong>{scoreLabel(value)}</strong>
                </button>
              );
            })}
          </div>
          <div className="reference-heading">
            <div>
              <span className="eyebrow">
                REFERENCE #{selected.index} {selected.ocr && ' / OCR'}
              </span>
              <h3>
                {selected.retained
                  ? 'Scored reading-flow snippet'
                  : 'Filtered out of aggregate scores'}
              </h3>
            </div>
            <div className="toolbar-actions">
              <button
                className="icon-button"
                aria-label="Previous reference"
                disabled={position <= 0}
                onClick={() => onSnippet(snippets[position - 1].index)}
              >
                <ChevronLeft size={16} />
              </button>
              <span>
                {position + 1} / {snippets.length}
              </span>
              <button
                className="icon-button"
                aria-label="Next reference"
                disabled={position >= snippets.length - 1}
                onClick={() => onSnippet(snippets[position + 1].index)}
              >
                <ChevronRight size={16} />
              </button>
            </div>
          </div>
          <div className="diff-toolbar">
            <div className="diff-legend">
              <span>
                <i className="diff-old-dot" /> Missing / changed reference
              </span>
              <span>
                <i className="diff-new-dot" /> Added / changed output
              </span>
            </div>
            <div className="diff-options">
              <label className="checkbox-label">
                <input
                  type="checkbox"
                  checked={changesOnly}
                  onChange={(event) => setChangesOnly(event.target.checked)}
                />{' '}
                Changes only
              </label>
              <select
                aria-label="Ground-truth diff layout"
                value={split ? 'split' : 'unified'}
                onChange={(event) => setSplit(event.target.value === 'split')}
              >
                <option value="split">Side by side</option>
                <option value="unified">Unified</option>
              </select>
              <select
                aria-label="Ground-truth diff granularity"
                value={granularity}
                onChange={(event) => setGranularity(event.target.value as typeof granularity)}
              >
                <option value="characters">Character diff</option>
                <option value="words">Word diff</option>
              </select>
            </div>
          </div>
          {match?.text === selected.text && (
            <div className="identical-notice">
              <CheckCheck size={16} /> Exact text match
            </div>
          )}
          {!match && (
            <div className="evidence-note">No evaluation match is available for this tool.</div>
          )}
          {match && !match.text && (
            <div className="evidence-note">The evaluator returned no matching text.</div>
          )}
          <div className="diff-viewer ground-truth-diff">
            <ReactDiffViewer
              key={`${document.page}:${selected.index}:${provider.id}:${split}`}
              oldValue={selected.text}
              newValue={match?.text ?? ''}
              splitView={split}
              compareMethod={
                granularity === 'characters' ? DiffMethod.CHARS : DiffMethod.WORDS_WITH_SPACE
              }
              showDiffOnly={changesOnly && selected.text !== match?.text}
              extraLinesSurroundingDiff={2}
              hideSummary
              leftTitle={
                split
                  ? 'Ground truth · reference text'
                  : `Ground truth → ${provider.name} · closest match`
              }
              rightTitle={`${provider.name} · closest match`}
              styles={{
                variables: {
                  light: {
                    diffViewerColor: '#293d3c',
                    removedBackground: '#fff1ef',
                    addedBackground: '#eef8f3',
                    wordRemovedBackground: '#ffc8be',
                    wordAddedBackground: '#b3e6cc',
                    gutterBackground: '#f5f7f6',
                    gutterColor: '#788784',
                    diffViewerTitleBackground: '#f5f7f6',
                    diffViewerTitleColor: '#354c48',
                  },
                },
                titleBlock: { height: 'auto', minHeight: '38px', padding: '8px 12px' },
                contentText: {
                  margin: 0,
                  fontSize: '13px',
                  lineHeight: '1.9',
                  fontFamily: 'ui-monospace, SFMono-Regular, Consolas, monospace',
                  overflowWrap: 'anywhere',
                  whiteSpace: 'pre-wrap',
                },
              }}
            />
          </div>
          <div className="match-scores" aria-label="All tool scores for this reference">
            {providers.map((tool) => {
              const result = selected.matches[tool.id];
              const value = result ? (1 - result.distance) * 100 : null;
              return (
                <button
                  key={tool.id}
                  aria-pressed={tool.id === provider.id}
                  onClick={() => onProvider(tool.id)}
                >
                  <span>{tool.name}</span>
                  <strong className={`score-badge ${scoreTone(value)}`}>{scoreLabel(value)}</strong>
                </button>
              );
            })}
          </div>
          <div className="match-footer">
            <span className={`score-badge ${scoreTone(score)}`}>
              {scoreLabel(score)} / 100 similarity
            </span>
            <span>
              Normalized distance: {match?.distance.toFixed(4) ?? 'unavailable'} · Original text,
              including whitespace
            </span>
          </div>
        </>
      )}
    </section>
  );
}
