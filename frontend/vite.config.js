// `defineConfig` sale de `vitest/config` y no de `vite`: la clave `test` de abajo no pertenece
// al esquema de Vite, y así queda tipada sin depender de que Vite tolere una clave desconocida.
import { defineConfig } from 'vitest/config';
import react from '@vitejs/plugin-react';
import path from 'path';

export default defineConfig({
    plugins: [react()],
    resolve: {
        alias: {
            // `import.meta.dirname` y no `__dirname`: este archivo es ESM y Vite 8 ya no lo
            // empaqueta a CJS, así que `__dirname` dejaría de existir.
            '@': path.resolve(import.meta.dirname, 'src'),
            '@features': path.resolve(import.meta.dirname, 'src/features'),
            '@app': path.resolve(import.meta.dirname, 'src/app'),
        },
    },
    test: {
        environment: 'jsdom',
        globals: true,
        setupFiles: './src/test/setup.js',
        include: ['src/**/*.test.{js,jsx}'],
    },
    server: {
        port: 3000,
        proxy: {
            '/api': {
                target: 'http://backend:9000',
                changeOrigin: true,
                rewrite: (p) => p.replace(/^\/api/, ''),
            },
        },
    },
});
