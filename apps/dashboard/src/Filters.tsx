import { RotateCcw, Search } from 'lucide-react';
import type { Benchmark } from './data';
import { defaultFilters, type Filters as FilterState } from './triage';

export function Filters({
  data,
  value,
  onChange,
  compact = false,
}: {
  data: Benchmark;
  value: FilterState;
  onChange: (filters: FilterState) => void;
  compact?: boolean;
}) {
  const update = (patch: Partial<FilterState>) => onChange({ ...value, ...patch });
  return (
    <div className={`filters ${compact ? 'compact' : ''}`}>
      <label className="search-field">
        <Search size={16} />
        <input
          aria-label="Search documents"
          placeholder="Search documents or categories…"
          value={value.query}
          onChange={(event) => update({ query: event.target.value })}
        />
      </label>
      <label className="field">
        Category
        <select
          value={value.category}
          onChange={(event) => update({ category: event.target.value })}
        >
          <option value="all">All categories</option>
          {[...new Set(data.documents.map((doc) => doc.category))].map((category) => (
            <option key={category} value={category}>
              {data.categories[category] ?? category}
            </option>
          ))}
        </select>
      </label>
      <label className="field">
        Score for
        <select
          value={value.provider}
          onChange={(event) => update({ provider: event.target.value })}
        >
          <option value="any">Any tool</option>
          <option value="all">Every tool</option>
          {data.providers.map((provider) => (
            <option key={provider.id} value={provider.id}>
              {provider.name}
            </option>
          ))}
        </select>
      </label>
      <label className="field">
        Score filter
        <select
          value={value.band}
          onChange={(event) => {
            const band = event.target.value as FilterState['band'];
            update({
              band,
              ...(band === 'low' ? { sort: 'worst' } : band === 'high' ? { sort: 'best' } : {}),
            });
          }}
        >
          <option value="all">All scores</option>
          <option value="low">Low · below 75</option>
          <option value="high">High · 95 and above</option>
          <option value="range">Custom range</option>
          <option value="unscored">Unscored</option>
        </select>
      </label>
      <label className="field">
        Sort documents
        <select
          value={value.sort}
          onChange={(event) => update({ sort: event.target.value as FilterState['sort'] })}
        >
          <option value="worst">Lowest score first</option>
          <option value="best">Highest score first</option>
          <option value="spread">Largest tool disagreement</option>
          <option value="page">Document number</option>
        </select>
      </label>
      <button
        className="icon-button reset-filters"
        title="Reset filters"
        aria-label="Reset filters"
        onClick={() => onChange({ ...defaultFilters })}
      >
        <RotateCcw size={16} />
      </button>
      {value.band === 'range' && (
        <div className="range-fields">
          <label className="field">
            Minimum score
            <input
              type="number"
              min="0"
              max="100"
              value={value.min}
              onChange={(event) =>
                update({ min: Math.max(0, Math.min(100, Number(event.target.value))) })
              }
            />
          </label>
          <span>to</span>
          <label className="field">
            Maximum score
            <input
              type="number"
              min="0"
              max="100"
              value={value.max}
              onChange={(event) =>
                update({ max: Math.max(0, Math.min(100, Number(event.target.value))) })
              }
            />
          </label>
          {value.min > value.max && (
            <span className="error-text">Minimum must not exceed maximum.</span>
          )}
        </div>
      )}
    </div>
  );
}
