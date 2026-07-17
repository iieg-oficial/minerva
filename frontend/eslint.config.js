import js from '@eslint/js';
import globals from 'globals';
import react from 'eslint-plugin-react';
import reactHooks from 'eslint-plugin-react-hooks';
import prettier from 'eslint-config-prettier';

// Flat config para React 19 (Vite, ESM). El JSX runtime automático no requiere importar React.
export default [
    { ignores: ['dist', 'node_modules'] },
    js.configs.recommended,
    {
        files: ['**/*.{js,jsx,mjs}'],
        languageOptions: {
            ecmaVersion: 'latest',
            sourceType: 'module',
            globals: { ...globals.browser, ...globals.node },
            parserOptions: {
                ecmaFeatures: { jsx: true },
            },
        },
        plugins: {
            react,
            'react-hooks': reactHooks,
        },
        settings: { react: { version: 'detect' } },
        rules: {
            ...react.configs.recommended.rules,
            ...reactHooks.configs.recommended.rules,
            // JSX transform automático (React 17+): no hace falta tener React en scope.
            'react/react-in-jsx-scope': 'off',
            'react/prop-types': 'off',
            'no-unused-vars': ['warn', { argsIgnorePattern: '^_' }],
            // Permite catches vacíos intencionales (fetches best-effort). Para errores reales
            // que deban manejarse, usa message/notification de AntD en vez de tragar el error.
            'no-empty': ['error', { allowEmptyCatch: true }],
        },
    },
    // Desactiva reglas de estilo que entran en conflicto con Prettier. Debe ir al final.
    prettier,
];
