import { useEffect, useState } from 'react';
import ReactDiffViewer, { DiffMethod } from 'react-diff-viewer-continued';
import { ArrowLeftRight, LoaderCircle } from 'lucide-react';
import { readArtifact, scoreLabel, type DocumentRecord, type Provider } from './data';

export default function DiffPanel({
  document,
  providers,
  pair,
  onChange,
}: {
  document: DocumentRecord;
  providers: Provider[];
  pair: string[];
  onChange: (pair: string[]) => void;
}) {
  const left = providers.find((provider) => provider.id === pair[0]) ?? providers[0];
  const right =
    providers.find((provider) => provider.id === pair[1] && provider.id !== left.id) ??
    providers.find((provider) => provider.id !== left.id) ??
    left;
  const [content, setContent] = useState<{ left: string; right: string }>();
  const [error, setError] = useState('');
  const [attempt, setAttempt] = useState(0);
  const [changesOnly, setChangesOnly] = useState(true);
  const [granularity, setGranularity] = useState<'words' | 'characters'>('words');
  useEffect(() => {
    let active = true;
    setContent(undefined);
    setError('');
    Promise.all([readArtifact(document.outputs[left.id]), readArtifact(document.outputs[right.id])])
      .then(([leftBytes, rightBytes]) => {
        if (active)
          setContent({
            left: new TextDecoder().decode(leftBytes),
            right: new TextDecoder().decode(rightBytes),
          });
      })
      .catch((error) => {
        if (active) setError(String(error));
      });
    return () => {
      active = false;
    };
  }, [document, left.id, right.id, attempt]);
  return (
    <section className="diff-panel card">
      <div className="diff-selectors">
        <label>
          <span>
            <i className="diff-old-dot" />
            LEFT PARSER
          </span>
          <select
            aria-label="Left parser for diff"
            value={left.id}
            onChange={(event) =>
              onChange([event.target.value, event.target.value === right.id ? left.id : right.id])
            }
          >
            {providers.map((provider) => (
              <option key={provider.id} value={provider.id}>
                {provider.name}
              </option>
            ))}
          </select>
          <small>Document FATA: {scoreLabel(document.scores[left.id])}</small>
        </label>
        <button
          className="swap-button icon-button"
          aria-label="Swap compared parsers"
          title="Swap sides"
          onClick={() => onChange([right.id, left.id])}
        >
          <ArrowLeftRight size={18} />
        </button>
        <label>
          <span>
            <i className="diff-new-dot" />
            RIGHT PARSER
          </span>
          <select
            aria-label="Right parser for diff"
            value={right.id}
            onChange={(event) =>
              onChange([event.target.value === left.id ? right.id : left.id, event.target.value])
            }
          >
            {providers.map((provider) => (
              <option key={provider.id} value={provider.id}>
                {provider.name}
              </option>
            ))}
          </select>
          <small>Document FATA: {scoreLabel(document.scores[right.id])}</small>
        </label>
      </div>
      <div className="diff-toolbar">
        <div className="diff-legend">
          <span>
            <i className="diff-old-dot" />
            Left-only text
          </span>
          <span>
            <i className="diff-new-dot" />
            Right-only text
          </span>
        </div>
        <div className="diff-options">
          <label className="checkbox-label">
            <input
              type="checkbox"
              checked={changesOnly}
              onChange={(event) => setChangesOnly(event.target.checked)}
            />
            Changes only
          </label>
          <select
            aria-label="Diff highlight granularity"
            value={granularity}
            onChange={(event) => setGranularity(event.target.value as 'words' | 'characters')}
          >
            <option value="words">Word diff</option>
            <option value="characters">Character diff</option>
          </select>
        </div>
      </div>
      {error ? (
        <div className="panel-empty">
          <p>{error}</p>
          <button className="button secondary" onClick={() => setAttempt((value) => value + 1)}>
            Retry comparison
          </button>
        </div>
      ) : !content ? (
        <div className="panel-empty">
          <LoaderCircle className="spin" />
          Loading both parser outputs…
        </div>
      ) : (
        <>
          {content.left === content.right && (
            <div className="identical-notice">These parser outputs are identical.</div>
          )}
          <div className="diff-viewer">
            <ReactDiffViewer
              key={`${document.page}:${left.id}:${right.id}`}
              oldValue={content.left}
              newValue={content.right}
              splitView
              compareMethod={
                granularity === 'words' ? DiffMethod.WORDS_WITH_SPACE : DiffMethod.CHARS
              }
              showDiffOnly={changesOnly && content.left !== content.right}
              extraLinesSurroundingDiff={3}
              hideSummary
              leftTitle={left.name}
              rightTitle={right.name}
              useDarkTheme={false}
              styles={{
                variables: {
                  light: {
                    diffViewerBackground: '#ffffff',
                    diffViewerColor: '#52617a',
                    diffViewerTitleBackground: '#f7f9fc',
                    diffViewerTitleColor: '#52617a',
                    addedBackground: '#effaf5',
                    addedColor: '#336a54',
                    removedBackground: '#fff1f1',
                    removedColor: '#914f57',
                    wordAddedBackground: '#bcebd2',
                    wordRemovedBackground: '#f8c9cd',
                    gutterBackground: '#fafbfd',
                    gutterColor: '#a1aec0',
                    codeFoldBackground: '#f4f7fc',
                    codeFoldContentColor: '#6981af',
                  },
                },
                titleBlock: { height: 'auto', minHeight: '38px', padding: '8px 12px' },
                contentText: {
                  margin: 0,
                  fontSize: '11px',
                  lineHeight: '1.85',
                  fontFamily: 'ui-monospace, SFMono-Regular, Consolas, monospace',
                  overflowWrap: 'anywhere',
                  whiteSpace: 'pre-wrap',
                },
              }}
            />
          </div>
        </>
      )}
      <div className="evidence-note">
        Comparing the original Markdown, including whitespace and HTML. Red and green identify the
        two sides; they do not indicate correctness.
      </div>
    </section>
  );
}
