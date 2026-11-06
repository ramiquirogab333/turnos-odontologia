import { createRoot } from 'react-dom/client';
import { App, RUTA_GESTION } from './App';
import { cargarCatalogo } from './lib/api';
import '@fontsource/plus-jakarta-sans/latin-400.css';
import '@fontsource/plus-jakarta-sans/latin-600.css';
import '@fontsource/plus-jakarta-sans/latin-700.css';
import './estilos.css';

const raiz = document.getElementById('root');
if (!raiz) throw new Error('Falta el elemento #root');

// La carga de tratamientos y profesionales arranca acá, antes de montar React.
const inicial = window.location.pathname === RUTA_GESTION ? Promise.resolve({ tratamientos: [], profesionales: [] }) : cargarCatalogo();
// Si volvemos del checkout el catálogo no se usa: se evita un rechazo sin manejar.
inicial.catch(() => undefined);
createRoot(raiz).render(<App inicial={inicial} recargar={cargarCatalogo} />);
