import { createContext } from 'react';

/** Recepción y admin pueden vincular turnos con pacientes; la odontóloga no (C-11, RN-CL-02). El servidor responde 403 igual. */
export const PuedeVincularContext = createContext(false);
