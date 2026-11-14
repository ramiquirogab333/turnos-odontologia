import { useId, type ReactNode } from 'react';

interface PropsTexto {
  readonly etiqueta: string;
  readonly valor: string;
  readonly alCambiar: (valor: string) => void;
  readonly error?: string | undefined;
  readonly tipo?: 'text' | 'number' | 'time';
  readonly ayuda?: string;
  readonly autoComplete?: string;
  readonly inputMode?: 'numeric' | 'decimal' | 'text';
  readonly paso?: number;
}

/** Campo de texto con su etiqueta visible y el error pegado al campo (se anuncia y no pierde lo escrito). */
export function CampoCatalogo({ etiqueta, valor, alCambiar, error, tipo = 'text', ayuda, autoComplete, inputMode, paso }: PropsTexto) {
  const id = useId();
  const descripciones = [ayuda === undefined ? null : `${id}-ayuda`, error === undefined ? null : `${id}-error`]
    .filter((d): d is string => d !== null)
    .join(' ');
  return (
    <div className="campo">
      <label htmlFor={id}>{etiqueta}</label>
      <input
        id={id}
        type={tipo}
        value={valor}
        autoComplete={autoComplete ?? 'off'}
        {...(inputMode === undefined ? {} : { inputMode })}
        {...(paso === undefined ? {} : { step: paso })}
        aria-invalid={error === undefined ? undefined : true}
        aria-describedby={descripciones === '' ? undefined : descripciones}
        onChange={(e) => {
          alCambiar(e.target.value);
        }}
      />
      {ayuda !== undefined && (
        <p className="nota" id={`${id}-ayuda`}>
          {ayuda}
        </p>
      )}
      {error !== undefined && (
        <p className="campo-error" id={`${id}-error`}>
          {error}
        </p>
      )}
    </div>
  );
}

interface PropsSelector {
  readonly etiqueta: string;
  readonly valor: string;
  readonly alCambiar: (valor: string) => void;
  readonly children: ReactNode;
}

export function SelectorCatalogo({ etiqueta, valor, alCambiar, children }: PropsSelector) {
  const id = useId();
  return (
    <div className="campo">
      <label htmlFor={id}>{etiqueta}</label>
      <select
        id={id}
        value={valor}
        onChange={(e) => {
          alCambiar(e.target.value);
        }}
      >
        {children}
      </select>
    </div>
  );
}
