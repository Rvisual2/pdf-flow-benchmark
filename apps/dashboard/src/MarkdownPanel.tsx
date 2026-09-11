import { useEffect, useState } from 'react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import rehypeRaw from 'rehype-raw';
import rehypeSanitize from 'rehype-sanitize';
import { ArrowDownToLine, Code2, ExternalLink, Eye, LoaderCircle } from 'lucide-react';
import { readArtifact, parserColor, scoreLabel, type Provider, type DocumentRecord } from './data';

export function MarkdownPanel({
  provider,
  document,
}: {
  provider: Provider;
  document: DocumentRecord;
}) {
  const [mode, setMode] = useState<'rendered' | 'raw'>('rendered');
  const [content, setContent] = useState<string>();
  const [error, setError] = useState('');
  const [attempt, setAttempt] = useState(0);
  const artifact = document.outputs[provider.id];
  useEffect(() => {
    let active = true;
    setError('');
    readArtifact(artifact)
      .then((bytes) => {
        if (active) setContent(new TextDecoder().decode(bytes));
      })
      .catch((error) => {
        if (active) setError(String(error));
      });
    return () => {
      active = false;
    };
  }, [artifact, attempt]);
  function download() {
    if (content === undefined) return;
    const url = URL.createObjectURL(new Blob([content], { type: 'text/markdown;charset=utf-8' }));
    const anchor = window.document.createElement('a');
    anchor.href = url;
    anchor.download = `${provider.id}-page_${document.page}.md`;
    anchor.click();
    URL.revokeObjectURL(url);
  }
  return (
    <article className="output-panel">
      <header className="panel-heading">
        <span className="parser-name">
          <i style={{ background: parserColor(provider.id) }} />
          {provider.name}
        </span>
        <strong
          className="document-score"
          title="Mean similarity across retained snippets on this PDF"
        >
          {scoreLabel(document.scores[provider.id])}
        </strong>
      </header>
      <div className="output-toolbar">
        <div className="segmented" aria-label={`${provider.name} output mode`}>
          <button aria-pressed={mode === 'rendered'} onClick={() => setMode('rendered')}>
            <Eye size={12} />
            Rendered
          </button>
          <button aria-pressed={mode === 'raw'} onClick={() => setMode('raw')}>
            <Code2 size={12} />
            Raw
          </button>
        </div>
        <button
          className="icon-button"
          disabled={content === undefined}
          onClick={download}
          aria-label={`Download ${provider.name} Markdown`}
        >
          <ArrowDownToLine size={15} />
        </button>
      </div>
      <div className="output-content">
        {error ? (
          <div className="panel-empty">
            <p>{error}</p>
            <button className="button secondary" onClick={() => setAttempt((value) => value + 1)}>
              Retry
            </button>
          </div>
        ) : content === undefined ? (
          <div className="panel-empty">
            <LoaderCircle className="spin" /> Loading Markdown…
          </div>
        ) : !content ? (
          <div className="panel-empty">This parser returned an empty file.</div>
        ) : mode === 'raw' ? (
          <pre className="raw-markdown">{content}</pre>
        ) : (
          <div className="markdown">
            <ReactMarkdown
              remarkPlugins={[remarkGfm]}
              rehypePlugins={[rehypeRaw, rehypeSanitize]}
              components={{
                a: (props) => (
                  <a href={props.href} target="_blank" rel="noopener noreferrer">
                    {props.children}
                  </a>
                ),
                img: (props) => (
                  <span className="image-placeholder">
                    [Image{props.alt ? `: ${props.alt}` : ''}]
                  </span>
                ),
              }}
            >
              {content}
            </ReactMarkdown>
          </div>
        )}
      </div>
      <details className="provenance">
        <summary>
          Artifact & parser configuration <span>{(artifact.size / 1024).toFixed(1)} KB</span>
        </summary>
        <div>
          <p>
            SHA-256 <code>{artifact.sha256}</code>
          </p>
          <pre>{JSON.stringify(artifact.provenance ?? provider.config, null, 2)}</pre>
          <a href={artifact.url} target="_blank" rel="noreferrer">
            Open original artifact <ExternalLink size={11} />
          </a>
        </div>
      </details>
    </article>
  );
}
