import { cp, mkdir } from 'node:fs/promises';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

// PDF.js loads these resources on demand for embedded fonts and image decoding.
const root = dirname(dirname(fileURLToPath(import.meta.url)));
for (const directory of ['cmaps', 'standard_fonts', 'wasm']) {
  const destination = join(root, 'public', 'pdfjs', directory);
  await mkdir(destination, { recursive: true });
  await cp(join(root, 'node_modules', 'pdfjs-dist', directory), destination, { recursive: true });
}
