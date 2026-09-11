import assert from 'node:assert/strict';
import { test } from 'node:test';
import { defaultFilters, filterDocuments } from '../src/triage.ts';

const documents = [
  { page: 1, category: 'science', scores: { a: 0, b: 100 } },
  { page: 2, category: 'science', scores: { a: 74.99, b: 74.99 } },
  { page: 3, category: 'law', scores: { a: 75, b: 95 } },
  { page: 4, category: 'law', scores: { a: 95, b: 100 } },
  { page: 5, category: 'law', scores: { a: null, b: null } },
  { page: 6, category: 'science', scores: { a: 100, b: null } },
];
const data = {
  documents,
  providers: [{ id: 'a' }, { id: 'b' }],
  categories: { science: 'Science', law: 'Law' },
};
const pages = (filters) =>
  filterDocuments(data, { ...defaultFilters, sort: 'page', ...filters }).map((doc) => doc.page);

test('low/high filters distinguish any, every, and a selected tool at the boundaries', () => {
  assert.deepEqual(pages({ band: 'low', provider: 'any' }), [1, 2]);
  assert.deepEqual(pages({ band: 'low', provider: 'all' }), [2]);
  assert.deepEqual(pages({ band: 'low', provider: 'b' }), [2]);
  assert.deepEqual(pages({ band: 'high', provider: 'any' }), [1, 3, 4, 6]);
  assert.deepEqual(pages({ band: 'high', provider: 'all' }), [4]);
  assert.deepEqual(pages({ band: 'high', provider: 'a' }), [4, 6]);
});

test('zero is scored, missing scores never pass a numeric filter, custom endpoints are inclusive', () => {
  assert.deepEqual(pages({ band: 'unscored' }), [5]);
  assert.deepEqual(pages({ band: 'unscored', provider: 'b' }), [5, 6]);
  assert.deepEqual(pages({ band: 'range', provider: 'all', min: 0, max: 100 }), [1, 2, 3, 4]);
  assert.deepEqual(pages({ band: 'range', provider: 'a', min: 75, max: 95 }), [3, 4]);
  assert.deepEqual(pages({ band: 'range', min: 95, max: 75 }), []);
});

test('sorting uses the selected tool and keeps unscored documents last in both directions', () => {
  assert.deepEqual(pages({ provider: 'b', sort: 'worst' }), [2, 3, 1, 4, 5, 6]);
  assert.deepEqual(pages({ provider: 'b', sort: 'best' }), [1, 4, 3, 2, 5, 6]);
  assert.deepEqual(pages({ sort: 'spread' }), [1, 3, 4, 2, 5, 6]);
  assert.deepEqual(
    data.documents.map((doc) => doc.page),
    [1, 2, 3, 4, 5, 6],
  );
});

test('search and category constraints compose with score filtering', () => {
  assert.deepEqual(pages({ category: 'law', provider: 'a', band: 'high' }), [4]);
  assert.deepEqual(pages({ query: ' SCIENCE ', band: 'low' }), [1, 2]);
  assert.deepEqual(pages({ query: 'page_4.pdf' }), [4]);
  assert.deepEqual(pages({ query: 'missing' }), []);
});
