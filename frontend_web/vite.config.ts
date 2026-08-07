import { defineConfig } from 'vitest/config';
import path from 'path';
import react from '@vitejs/plugin-react';
import tailwindcss from '@tailwindcss/vite';
import { loadEnv } from 'vite';

import { VITE_DEFAULT_PORT, VITE_STATIC_DEFAULT_PORT } from './src/constants/dev';
import { DEFAULT_APP_LANGUAGE } from './src/lib/i18n/language';

const projectRoot = path.resolve(__dirname, '..');

export default defineConfig(({ mode }) => {
    const env = loadEnv(mode, projectRoot, '');
    const appLanguage =
        env.APP_LANGUAGE ||
        env.VITE_APP_LANGUAGE ||
        process.env.APP_LANGUAGE ||
        process.env.VITE_APP_LANGUAGE ||
        DEFAULT_APP_LANGUAGE;
    let base: string = '';
    // 1. if NOTEBOOK_ID is set, use /notebook-sessions/${NOTEBOOK_ID}/ports/5173/ for dev server
    if (process.env.NOTEBOOK_ID && process.env.NODE_ENV === 'development') {
        const notebookId = process.env.NOTEBOOK_ID;
        base = `/notebook-sessions/${notebookId}/ports/${VITE_DEFAULT_PORT}/`;
    }
    const proxyBase: string = base === '' ? '/' : base;
    const apiProxyTarget =
        env.VITE_API_PROXY_TARGET ||
        process.env.VITE_API_PROXY_TARGET ||
        `http://localhost:${VITE_STATIC_DEFAULT_PORT}`;

    // https://vite.dev/config/
    return {
        envDir: projectRoot,
        define: {
            'import.meta.env.VITE_APP_LANGUAGE': JSON.stringify(appLanguage),
        },
        plugins: [
            react(),
            tailwindcss(),
            {
                name: 'strip-base',
                apply: 'serve',
                configureServer({ middlewares }) {
                    middlewares.use((req, _res, next) => {
                        if (base !== '' && !req.url?.startsWith(base)) {
                            req.url = base.slice(0, -1) + req.url;
                        }
                        next();
                    });
                },
            },
        ],
        resolve: {
            alias: {
                '@': path.resolve(__dirname, './src'),
            },
        },
        base: base,
        build: {
            outDir: '../fastapi_server/static/',
            manifest: true,
        },
        server: {
            host: true,
            allowedHosts: ['localhost', '127.0.0.1', '.datarobot.com', '.drdev.io'],
            proxy: {
                [`${proxyBase}api/`]: {
                    target: apiProxyTarget,
                    changeOrigin: true,
                    rewrite: path => path.replace(new RegExp(`^${proxyBase}`), ''),
                },
            },
        },
        test: {
            globals: true,
            environment: 'jsdom',
            include: ['**/*.test.ts', '**/*.test.tsx'],
            setupFiles: ['./tests/setupMocks.ts', './tests/setupTests.ts'],
            typecheck: {
                tsconfig: './tsconfig.test.json',
            },
        },
    };
});
