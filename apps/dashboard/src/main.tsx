import { StrictMode, Suspense, lazy, useEffect, useState } from 'react';
import { createRoot } from 'react-dom/client';
import { FlaskConical, Grid2X2, LoaderCircle, ScanText } from 'lucide-react';
import { loadBenchmark, type Benchmark } from './data';
import type { Selection } from './DocumentExplorer';
import { defaultFilters, type Filters } from './triage';
import { Overview } from './Overview';
import './styles.css';
const DocumentExplorer = lazy(() =>
  import('./DocumentExplorer').then((module) => ({ default: module.DocumentExplorer })),
);

function readLocation() {
  const params = new URLSearchParams(location.search);
  const mode = params.get('mode');
  const band = params.get('band');
  const sort = params.get('sort');
  return {
    view: params.get('view') === 'documents' ? 'documents' : 'overview',
    selection: {
      page: Number(params.get('document')) || 1,
      parsers: params.get('parsers')?.split(',').filter(Boolean) ?? [],
      mode: mode === 'diff' || mode === 'outputs' || mode === 'pdf-markdown' ? mode : 'truth',
      snippet: params.has('snippet') ? Number(params.get('snippet')) : undefined,
    } as Selection,
    filters: {
      ...defaultFilters,
      query: params.get('q') ?? '',
      category: params.get('category') ?? 'all',
      provider: params.get('tool') ?? 'any',
      band: ['all', 'low', 'high', 'range', 'unscored'].includes(band ?? '') ? band : 'all',
      sort: ['worst', 'best', 'spread', 'page'].includes(sort ?? '') ? sort : 'worst',
      min:
        params.has('min') && Number.isFinite(Number(params.get('min')))
          ? Math.max(0, Math.min(100, Number(params.get('min'))))
          : 0,
      max:
        params.has('max') && Number.isFinite(Number(params.get('max')))
          ? Math.max(0, Math.min(100, Number(params.get('max'))))
          : 100,
    } as Filters,
  };
}
function App() {
  const [data, setData] = useState<Benchmark>();
  const [error, setError] = useState('');
  const [state, setState] = useState(readLocation);
  const { view, selection, filters } = state;
  useEffect(() => {
    loadBenchmark()
      .then((snapshot) => {
        setData(snapshot);
        setState((current) => {
          const parsers = [...new Set(current.selection.parsers)].filter((id) =>
            snapshot.providers.some((p) => p.id === id),
          );
          return {
            ...current,
            selection: {
              ...current.selection,
              page: snapshot.documents.some((doc) => doc.page === current.selection.page)
                ? current.selection.page
                : snapshot.documents[0].page,
              parsers: parsers.length ? parsers : [snapshot.providers[0].id],
            },
            filters: {
              ...current.filters,
              provider: ['any', 'all', ...snapshot.providers.map((p) => p.id)].includes(
                current.filters.provider,
              )
                ? current.filters.provider
                : 'any',
              category: ['all', ...snapshot.documents.map((doc) => doc.category)].includes(
                current.filters.category,
              )
                ? current.filters.category
                : 'all',
            },
          };
        });
      })
      .catch((error) => setError(String(error)));
  }, []);
  useEffect(() => {
    const url = new URL(location.href);
    const values: Record<string, string | undefined> = {
      view,
      document: String(selection.page),
      parsers: selection.parsers.join(','),
      mode: selection.mode,
      snippet: selection.snippet == null ? undefined : String(selection.snippet),
      q: filters.query || undefined,
      category: filters.category,
      tool: filters.provider,
      band: filters.band,
      sort: filters.sort,
      min: filters.band === 'range' ? String(filters.min) : undefined,
      max: filters.band === 'range' ? String(filters.max) : undefined,
    };
    for (const [key, value] of Object.entries(values)) {
      if (value === undefined) url.searchParams.delete(key);
      else url.searchParams.set(key, value);
    }
    history.replaceState(null, '', url);
  }, [state, view, selection, filters]);
  useEffect(() => {
    const restore = () => setState(readLocation());
    window.addEventListener('popstate', restore);
    return () => window.removeEventListener('popstate', restore);
  }, []);
  const setView = (view: string) => setState((current) => ({ ...current, view }));
  const onFilters = (filters: Filters) => setState((current) => ({ ...current, filters }));
  return (
    <div className="app-shell">
      <header className="topbar">
        <a
          className="brand"
          href="?"
          onClick={(event) => {
            event.preventDefault();
            setView('overview');
          }}
        >
          <span className="brand-icon">
            <FlaskConical size={19} />
          </span>
          FlowBench<span className="brand-tag">LAB</span>
        </a>
        <nav className="top-navigation" aria-label="Dashboard navigation">
          <button
            aria-current={view === 'overview' ? 'page' : undefined}
            onClick={() => setView('overview')}
          >
            <Grid2X2 size={15} /> Score matrix
          </button>
          <button
            aria-current={view === 'documents' ? 'page' : undefined}
            onClick={() => setView('documents')}
          >
            <ScanText size={15} /> Document inspector
          </button>
        </nav>
        <span className="snapshot">
          <span className="live-dot" />{' '}
          {data
            ? `${data.documents.length} documents · ${data.providers.length} tools`
            : 'Loading benchmark'}
        </span>
      </header>
      <main>
        {error ? (
          <div className="empty" role="alert">
            <h2>Unable to load benchmark</h2>
            <p>{error}</p>
            <button className="button secondary" onClick={() => location.reload()}>
              Try again
            </button>
          </div>
        ) : !data ? (
          <div className="empty" role="status">
            <LoaderCircle className="spin" />
            <p>Loading the published benchmark…</p>
          </div>
        ) : view === 'documents' ? (
          <Suspense fallback={<div className="empty">Loading document workspace…</div>}>
            <DocumentExplorer
              data={data}
              selection={selection}
              filters={filters}
              onFilters={onFilters}
              onBack={() => setView('overview')}
              onSelect={(selection) => setState((current) => ({ ...current, selection }))}
            />
          </Suspense>
        ) : (
          <Overview
            data={data}
            filters={filters}
            onFilters={onFilters}
            onExplore={(page, parser) =>
              setState((current) => ({
                ...current,
                view: 'documents',
                selection: { page, parsers: [parser], mode: 'truth' },
              }))
            }
          />
        )}
      </main>
    </div>
  );
}
createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <App />
  </StrictMode>,
);
