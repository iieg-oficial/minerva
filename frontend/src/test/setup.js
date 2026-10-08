// Setup global de Vitest: matchers de jest-dom y limpieza del DOM entre tests.
import '@testing-library/jest-dom/vitest';
import { cleanup, configure } from '@testing-library/react';
import { afterEach } from 'vitest';

// Los findBy esperan 1 s por defecto, y en el runner de CI el primer render de
// antd tarda más: el smoke de autenticación fallaba intermitente por eso.
configure({ asyncUtilTimeout: 5000 });

afterEach(() => {
    cleanup();
});
