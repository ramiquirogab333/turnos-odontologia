import { createRoot } from 'react-dom/client';
import { App } from './App';
import { cargarCatalogo } from './lib/api';
import '@fontsource/plus-jakarta-sans/latin-400.css';
import '@fontsource/plus-jakarta-sans/latin-600.css';
import '@fontsource/plus-jakarta-sans/latin-700.css';
import './estilos.css';

const raiz = document.getElementById('root');
if (!raiz) throw new Error('Falta el elemento #root');

// La carga de tratamientos y profesionales arranca acá, antes de montar React.
createRoot(raiz).render(<App inicial={cargarCatalogo()} recargar={cargarCatalogo} />);
