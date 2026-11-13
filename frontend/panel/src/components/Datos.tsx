import { useState } from 'react';
import type { Api } from '../lib/api';
import { puedeVerAuditoria } from '../lib/datos';
import type { Rol } from '../lib/tipos';
import { Auditoria } from './Auditoria';
import { Exportar } from './Exportar';

export type PestanaDatos = 'exportar' | 'auditoria';

interface Props {
  readonly api: Api;
  readonly roles: readonly Rol[];
  /** "Hoy" en la clínica ("YYYY-MM-DD"). */
  readonly hoy: string;
  /** Pestaña con la que abre (sale del hash `#/datos?pestana=auditoria`). */
  readonly pestanaInicial?: PestanaDatos;
}

/** «Datos» (C-13): exportar (recepción y admin) y auditoría (solo admin, O6). */
export function Datos({ api, roles, hoy, pestanaInicial = 'exportar' }: Props) {
  const [pestana, setPestana] = useState<PestanaDatos>(pestanaInicial);
  const veAuditoria = puedeVerAuditoria(roles);
  const pestanas: readonly { readonly id: PestanaDatos; readonly etiqueta: string }[] = [
    { id: 'exportar', etiqueta: 'Exportar' },
    ...(veAuditoria ? ([{ id: 'auditoria', etiqueta: 'Auditoría' }] as const) : []),
  ];

  return (
    <section className="datos" aria-label="Datos">
      <div className="selector selector-periodo" role="tablist" aria-label="Datos">
        {pestanas.map((p) => (
          <button
            key={p.id}
            type="button"
            role="tab"
            id={`pestana-${p.id}`}
            aria-selected={pestana === p.id}
            aria-controls="panel-datos"
            className={`selector-boton${pestana === p.id ? ' activo' : ''}`}
            onClick={() => {
              setPestana(p.id);
            }}
          >
            {p.etiqueta}
          </button>
        ))}
      </div>
      <div id="panel-datos" role="tabpanel" aria-labelledby={`pestana-${pestana}`}>
        {pestana === 'exportar' && <Exportar api={api} roles={roles} hoy={hoy} />}
        {pestana === 'auditoria' &&
          (veAuditoria ? (
            <Auditoria api={api} />
          ) : (
            <div className="aviso aviso-error" role="alert">
              <p>No tenés permiso para ver la auditoría.</p>
            </div>
          ))}
      </div>
    </section>
  );
}
