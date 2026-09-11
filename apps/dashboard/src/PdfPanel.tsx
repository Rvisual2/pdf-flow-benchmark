import { useEffect, useRef, useState } from 'react';
import * as pdfjs from 'pdfjs-dist';
import pdfWorker from 'pdfjs-dist/build/pdf.worker.min.mjs?url';
import { ChevronLeft, ChevronRight, ExternalLink, FileText, LoaderCircle } from 'lucide-react';
import { readArtifact, type Artifact } from './data';
pdfjs.GlobalWorkerOptions.workerSrc = pdfWorker;

export default function PdfPanel({ artifact }: { artifact: Artifact }) {
  const [pdf, setPdf] = useState<pdfjs.PDFDocumentProxy>();
  const [page, setPage] = useState(1);
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(true);
  const [width, setWidth] = useState(320);
  const [attempt, setAttempt] = useState(0);
  const container = useRef<HTMLDivElement>(null);
  const canvas = useRef<HTMLCanvasElement>(null);
  useEffect(() => {
    let active = true;
    let task: pdfjs.PDFDocumentLoadingTask | undefined;
    setError('');
    setLoading(true);
    readArtifact(artifact)
      .then((bytes) => {
        if (!active) return;
        const assets = `${import.meta.env.BASE_URL}pdfjs/`;
        task = pdfjs.getDocument({
          data: bytes.slice(0),
          cMapUrl: `${assets}cmaps/`,
          cMapPacked: true,
          standardFontDataUrl: `${assets}standard_fonts/`,
          wasmUrl: `${assets}wasm/`,
        });
        return task.promise;
      })
      .then((document) => {
        if (active && document) setPdf(document);
      })
      .catch((error) => {
        if (active) {
          setError(String(error));
          setLoading(false);
        }
      });
    return () => {
      active = false;
      void task?.destroy();
    };
  }, [artifact, attempt]);
  useEffect(() => {
    if (!container.current) return;
    const observer = new ResizeObserver((entries) =>
      setWidth(Math.max(180, entries[0].contentRect.width - 32)),
    );
    observer.observe(container.current);
    return () => observer.disconnect();
  }, []);
  useEffect(() => {
    if (!pdf || !canvas.current) return;
    let cancelled = false;
    let rendering: pdfjs.RenderTask | undefined;
    setLoading(true);
    pdf
      .getPage(page)
      .then((pdfPage) => {
        if (cancelled || !canvas.current) return;
        const viewport = pdfPage.getViewport({
          scale: width / pdfPage.getViewport({ scale: 1 }).width,
        });
        const ratio = Math.min(window.devicePixelRatio || 1, 2);
        const target = canvas.current;
        target.width = Math.floor(viewport.width * ratio);
        target.height = Math.floor(viewport.height * ratio);
        target.style.width = `${viewport.width}px`;
        target.style.height = `${viewport.height}px`;
        rendering = pdfPage.render({
          canvas: target,
          viewport,
          transform: [ratio, 0, 0, ratio, 0, 0],
        });
        return rendering.promise;
      })
      .then(() => {
        if (!cancelled) setLoading(false);
      })
      .catch((error) => {
        if (!cancelled) {
          setError(String(error));
          setLoading(false);
        }
      });
    return () => {
      cancelled = true;
      rendering?.cancel();
    };
  }, [pdf, page, width]);
  return (
    <section className="pdf-panel">
      <header className="panel-heading">
        <span className="parser-name">
          <FileText size={14} />
          Source PDF
        </span>
        <a
          className="icon-button"
          href={artifact.url}
          target="_blank"
          rel="noreferrer"
          aria-label="Open PDF in a new tab"
        >
          <ExternalLink size={14} />
        </a>
      </header>
      <div className="pdf-navigation">
        <button
          className="icon-button"
          aria-label="Previous PDF page"
          disabled={page <= 1}
          onClick={() => setPage(page - 1)}
        >
          <ChevronLeft size={15} />
        </button>
        <span>
          {page} / {pdf?.numPages ?? '…'}
        </span>
        <button
          className="icon-button"
          aria-label="Next PDF page"
          disabled={!pdf || page >= pdf.numPages}
          onClick={() => setPage(page + 1)}
        >
          <ChevronRight size={15} />
        </button>
        <span className="pdf-fit">Fit width</span>
      </div>
      <div className="pdf-canvas" ref={container}>
        {error ? (
          <div className="panel-empty">
            <p>{error}</p>
            <button className="button secondary" onClick={() => setAttempt((value) => value + 1)}>
              Retry PDF
            </button>
            <a href={artifact.url} target="_blank" rel="noreferrer">
              Open original PDF
            </a>
          </div>
        ) : (
          <>
            {loading && (
              <div className="pdf-loading">
                <LoaderCircle size={18} className="spin" />
              </div>
            )}
            <canvas
              ref={canvas}
              aria-label={`Source PDF, page ${page}. Use Open PDF for the original accessible document.`}
            />
          </>
        )}
      </div>
    </section>
  );
}
