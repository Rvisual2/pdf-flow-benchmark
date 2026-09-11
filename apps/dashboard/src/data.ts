export interface Artifact {
  provenance?: Record<string, unknown>;
  url: string;
  sha256: string;
  size: number;
}
export interface Provider {
  id: string;
  name: string;
  vendor: string;
  service: string;
  score: number;
  config: Record<string, unknown>;
  wallSeconds: number | null;
  failed: number | null;
  categories: Record<string, number | undefined>;
}
export interface Snippet {
  index: number;
  text: string;
  ocr: boolean;
  retained: boolean;
  matches: Record<string, { distance: number; text: string }>;
}
export interface DocumentRecord {
  page: number;
  category: string;
  pdf: Artifact;
  thumbnail?: (Artifact & { width: number; height: number }) | null;
  outputs: Record<string, Artifact>;
  scores: Record<string, number | null>;
  snippets: Snippet[];
  scoredSnippets: number;
}
export interface Benchmark {
  schemaVersion: number;
  release: string;
  generatedAt: string;
  providers: Provider[];
  documents: DocumentRecord[];
  categories: Record<string, string>;
  scoredDocuments: number;
  scoredSnippets: number;
  methodology: string;
}
const cache = new Map<string, Promise<ArrayBuffer>>();
export function readArtifact(artifact: Artifact): Promise<ArrayBuffer> {
  const existing = cache.get(artifact.url);
  if (existing) return existing;
  const request = (async () => {
    const url = new URL(artifact.url);
    // A distinct viewer URL avoids reusing responses cached before bucket CORS was enabled.
    url.searchParams.set('viewer', 'flowbench');
    const response = await fetch(url);
    if (!response.ok) throw new Error(`Artifact request failed (${response.status}).`);
    const bytes = await response.arrayBuffer();
    const digest = await crypto.subtle.digest('SHA-256', bytes);
    const hash = Array.from(new Uint8Array(digest), (byte) =>
      byte.toString(16).padStart(2, '0'),
    ).join('');
    if (bytes.byteLength !== artifact.size || hash !== artifact.sha256)
      throw new Error('Artifact integrity check failed. Refresh to load the published version.');
    return bytes;
  })();
  cache.set(artifact.url, request);
  request.catch(() => cache.delete(artifact.url));
  return request;
}
export async function loadBenchmark(): Promise<Benchmark> {
  const response = await fetch(`${import.meta.env.BASE_URL}data-source.json`);
  if (!response.ok) throw new Error('The dashboard data pointer could not be loaded.');
  const data = JSON.parse(
    new TextDecoder().decode(await readArtifact(await response.json())),
  ) as Benchmark;
  if (data.schemaVersion !== 1 || !data.documents.length || !data.providers.length)
    throw new Error('Unsupported or empty benchmark snapshot.');
  return data;
}
export const scoreLabel = (score: number | null | undefined) =>
  score == null ? 'Unscored' : score.toFixed(2);
export const parserColor = (id: string) =>
  ({
    gemini: '#4563e8',
    datalab: '#259a88',
    docling_ocr: '#9365cd',
    reducto: '#e69b3a',
    llamaparse: '#dc6d87',
    docling_no_ocr: '#7980ba',
    pymupdf4llm: '#507e92',
  })[id] ?? '#4563e8';
