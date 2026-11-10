// El navegador del paciente puede estar en cualquier zona: los tests corren en una
// zona distinta de la clínica (-03:00) para probar que nunca se usa la del navegador.
export default function setup(): void {
  process.env['TZ'] = 'Asia/Tokyo';
}
