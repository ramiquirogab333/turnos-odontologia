import { createRoot } from 'react-dom/client';
import { App } from './App';
import { crearApi } from './lib/api';
import { Sesion } from './lib/sesion';
import { hoyClinica } from './lib/tiempo';
import '@fontsource/plus-jakarta-sans/latin-400.css';
import '@fontsource/plus-jakarta-sans/latin-600.css';
import '@fontsource/plus-jakarta-sans/latin-700.css';
import './estilos.css';

const raiz = document.getElementById('root');
if (!raiz) throw new Error('Falta el elemento #root');

const sesion = new Sesion();
const api = crearApi(sesion);
createRoot(raiz).render(<App sesion={sesion} api={api} hoy={() => hoyClinica(new Date())} />);
