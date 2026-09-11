import type { Benchmark, DocumentRecord } from './data.ts';

export interface Filters {
  query: string;
  category: string;
  provider: string;
  band: 'all' | 'low' | 'high' | 'range' | 'unscored';
  sort: 'worst' | 'best' | 'spread' | 'page';
  min: number;
  max: number;
}
export const defaultFilters: Filters = {
  query: '',
  category: 'all',
  provider: 'any',
  band: 'all',
  sort: 'worst',
  min: 0,
  max: 100,
};
export function scoresFor(doc: DocumentRecord, provider: string): number[] {
  const values =
    provider === 'any' || provider === 'all' ? Object.values(doc.scores) : [doc.scores[provider]];
  return values.filter((score): score is number => score != null && Number.isFinite(score));
}
export function spread(doc: DocumentRecord): number | null {
  const scores = scoresFor(doc, 'any');
  return scores.length > 1 ? Math.max(...scores) - Math.min(...scores) : null;
}
export function focusScore(doc: DocumentRecord, filters: Filters): number | null {
  if (filters.sort === 'spread') return spread(doc);
  const scores = scoresFor(doc, filters.provider);
  if (!scores.length) return null;
  return filters.sort === 'best' ? Math.max(...scores) : Math.min(...scores);
}
export function filterDocuments(data: Benchmark, filters: Filters): DocumentRecord[] {
  return data.documents
    .filter((doc) => {
      if (filters.category !== 'all' && doc.category !== filters.category) return false;
      if (
        !`page_${doc.page}.pdf ${data.categories[doc.category] ?? doc.category}`
          .toLowerCase()
          .includes(filters.query.trim().toLowerCase())
      )
        return false;
      const scores = scoresFor(doc, filters.provider);
      if (filters.band === 'all') return true;
      if (filters.band === 'unscored') return !scores.length;
      if (!scores.length) return false;
      const matches = (score: number) =>
        filters.band === 'low'
          ? score < 75
          : filters.band === 'high'
            ? score >= 95
            : score >= filters.min && score <= filters.max;
      return filters.provider === 'all'
        ? scores.length === data.providers.length && scores.every(matches)
        : scores.some(matches);
    })
    .sort((a, b) => {
      if (filters.sort === 'page') return a.page - b.page;
      const left = focusScore(a, filters);
      const right = focusScore(b, filters);
      if (left == null) return right == null ? a.page - b.page : 1;
      if (right == null) return -1;
      return (filters.sort === 'worst' ? left - right : right - left) || a.page - b.page;
    });
}
export function scoreTone(score: number | null | undefined): string {
  return score == null ? 'unscored' : score < 75 ? 'low' : score < 95 ? 'mid' : 'high';
}
