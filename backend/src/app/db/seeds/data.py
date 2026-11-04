"""Datos sintéticos de seed (R19: información 100% sintética, sin datos reales de pacientes)."""

from datetime import time

# Roles del sistema (unique por nombre)
SEED_ROLES = [
    {"nombre": "admin", "descripcion": "Administrador del sistema con acceso total"},
    {"nombre": "odontologo", "descripcion": "Odontólogo que atiende turnos"},
    {"nombre": "recepcion", "descripcion": "Recepción del consultorio"},
]

# Usuario administrador inicial (email único; hashed_password sintético placeholder)
SEED_USUARIO_ADMIN = {
    "email": "admin@consultorio.test",
    "nombre_completo": "Administrador Sistema",
    "hashed_password": "$2b$12$placeholder.hash.admin.synthetic.do.not.use.in.production",
}

# Obras sociales de referencia para nomenclador (código único)
SEED_OBRAS_SOCIALES = [
    {"codigo": "OSDE", "nombre": "OSDE", "sigla": "OSDE"},
    {"codigo": "SWISS", "nombre": "Swiss Medical", "sigla": "SWM"},
    {"codigo": "GALICIA", "nombre": "Galicia Salud", "sigla": "GAL"},
    {"codigo": "OMEGA", "nombre": "Omint", "sigla": "OMI"},
    {"codigo": "PARTICULAR", "nombre": "Particular", "sigla": "PAR"},
]

# Tratamientos iniciales con duración y precio base (RN-TU-05 — placeholder explícito si la clínica no aporta)
SEED_TRATAMIENTOS = [
    {"nombre": "Consulta odontológica", "duracion_minutos": 30, "precio_base": "15000.00"},
    {"nombre": "Limpieza dental", "duracion_minutos": 45, "precio_base": "25000.00"},
    {"nombre": "Empaste / obturación", "duracion_minutos": 45, "precio_base": "30000.00"},
    {"nombre": "Extracción simple", "duracion_minutos": 30, "precio_base": "20000.00"},
    {"nombre": "Blanqueamiento", "duracion_minutos": 60, "precio_base": "80000.00"},
]

# Múltiples profesionales (multi-odontólogo día 1, Resolución 2026-09-30 nº1)
SEED_PROFESIONALES = [
    {"nombre": "Dr. Juan Pérez", "matricula": "MAT-001", "especialidad": "General"},
    {"nombre": "Dra. María Gómez", "matricula": "MAT-002", "especialidad": "General"},
    {"nombre": "Dr. Carlos Ruiz", "matricula": "MAT-003", "especialidad": "Ortodoncia"},
]

# Múltiples sillones (multi-sillón día 1)
SEED_SILLONES = [
    {"nombre": "Sillón 1", "estado": "activo"},
    {"nombre": "Sillón 2", "estado": "activo"},
    {"nombre": "Sillón 3", "estado": "activo"},
]

# Disponibilidad horaria por profesional (lunes a viernes, 08:00-12:00 y 14:00-18:00)
SEED_DISPONIBILIDAD = []
for prof_idx in range(1, len(SEED_PROFESIONALES) + 1):
    for dia in range(0, 5):  # Lunes a viernes
        SEED_DISPONIBILIDAD.append(
            {
                "profesional_id": prof_idx,
                "dia_semana": dia,
                "hora_inicio": time(8, 0),
                "hora_fin": time(12, 0),
                "sillon_defecto_id": None,
            }
        )
        SEED_DISPONIBILIDAD.append(
            {
                "profesional_id": prof_idx,
                "dia_semana": dia,
                "hora_inicio": time(14, 0),
                "hora_fin": time(18, 0),
                "sillon_defecto_id": None,
            }
        )
