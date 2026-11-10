export function Cargando({ texto }: { readonly texto: string }) {
  return (
    <p className="estado-carga" role="status">
      {texto}
    </p>
  );
}
