import { existsSync, readFileSync } from 'node:fs';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import tailwindcss from '@tailwindcss/vite';
import react from '@vitejs/plugin-react';
import { defineConfig, type Plugin } from 'vite';
import { LEGACY_HTML_PAGES } from './frontend/src/app/legacyHtml';

const rootDir = dirname(fileURLToPath(import.meta.url));
const frontend = resolve(rootDir, 'frontend');

const legacyHtmlPaths = new Set(LEGACY_HTML_PAGES.map((name) => `/${name}.html`));
// Vite's HTML fallback serves /add-item as add-item.html when that file exists,
// even with appType: 'spa'. Rewrite those extensionless paths to the shell too;
// React then redirects them to the current route (/dashboard -> /today, etc.).
const legacyRoutes = new Set<string>(LEGACY_HTML_PAGES.map((name) => `/${name}`));

// The Stock import dialog links to this file. Vite does not copy plain href assets.
const staticAssets = [
  'import-template.csv',
];

function copyStaticAssets(): Plugin {
  return {
    name: 'copy-static-frontend-assets',
    generateBundle() {
      for (const file of staticAssets) {
        const from = resolve(frontend, file);
        if (!existsSync(from)) continue;
        this.emitFile({
          type: 'asset',
          fileName: file,
          source: readFileSync(from),
        });
      }
    },
  };
}

// Old *.html URLs (emails, bookmarks) are not Vite inputs. Serve the SPA shell
// for them and keep the query string; legacyHtml.ts maps each to its new route.
function rewriteLegacyHtml(req: { url?: string }): void {
  const raw = req.url;
  if (!raw) return;
  const hashAt = raw.indexOf('#');
  const withoutHash = hashAt === -1 ? raw : raw.slice(0, hashAt);
  const queryAt = withoutHash.indexOf('?');
  const path = queryAt === -1 ? withoutHash : withoutHash.slice(0, queryAt);
  if (!legacyHtmlPaths.has(path) && !legacyRoutes.has(path)) return;
  const search = queryAt === -1 ? '' : withoutHash.slice(queryAt);
  const hash = hashAt === -1 ? '' : raw.slice(hashAt);
  req.url = `/index.html${search}${hash}`;
}

function legacyHtmlSpaFallback(): Plugin {
  return {
    name: 'legacy-html-spa-fallback',
    configureServer(server) {
      server.middlewares.use((req, _res, next) => {
        rewriteLegacyHtml(req);
        next();
      });
    },
    configurePreviewServer(server) {
      server.middlewares.use((req, _res, next) => {
        rewriteLegacyHtml(req);
        next();
      });
    },
  };
}

export default defineConfig({
  root: frontend,
  appType: 'spa',
  plugins: [legacyHtmlSpaFallback(), react(), tailwindcss(), copyStaticAssets()],
  resolve: {
    alias: {
      '@': resolve(frontend, 'src'),
    },
  },
  server: {
    port: 8000,
    strictPort: true,
  },
  preview: {
    port: 8000,
    strictPort: true,
  },
  build: {
    outDir: resolve(frontend, 'dist'),
    emptyOutDir: true,
    rollupOptions: {
      input: resolve(frontend, 'index.html'),
    },
  },
});
