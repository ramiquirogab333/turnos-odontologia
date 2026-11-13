import type { ArchivoExportado } from './tipos';

/** Entrega el archivo al navegador con un enlace temporal `download`; libera la URL apenas se dispara. */
export function guardarArchivo(archivo: ArchivoExportado): void {
  const url = URL.createObjectURL(archivo.blob);
  const enlace = document.createElement('a');
  enlace.href = url;
  enlace.download = archivo.nombre;
  enlace.rel = 'noopener';
  document.body.appendChild(enlace);
  enlace.click();
  enlace.remove();
  window.setTimeout(() => {
    URL.revokeObjectURL(url);
  }, 0);
}
