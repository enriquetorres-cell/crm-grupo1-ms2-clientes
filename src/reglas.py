"""Reglas de negocio de MS2 (Clientes). Sin BD ni HTTP: se prueban solas."""
import datetime
import re
from decimal import Decimal

from .comun import DatoInvalido

FACTORES_RUC = (5, 4, 3, 2, 7, 6, 5, 4, 3, 2)
UMBRAL_SEGMENTO_A = Decimal('50000')
UMBRAL_SEGMENTO_B = Decimal('10000')
DIAS_PARA_INACTIVO = 90
# Con estos dominios no se deduplica: dos personas con gmail no son la misma empresa.
DOMINIOS_PUBLICOS = {'gmail.com', 'hotmail.com', 'outlook.com', 'yahoo.com', 'live.com', 'icloud.com'}

_PATRON_EMAIL = re.compile(r'[^@\s]+@([^@\s]+\.[a-z]{2,})', re.IGNORECASE)


def digito_verificador_ruc(primeros_10):
    """Algoritmo módulo 11 de SUNAT."""
    suma = sum(int(d) * f for d, f in zip(primeros_10, FACTORES_RUC))
    resto = 11 - suma % 11
    return {10: 0, 11: 1}.get(resto, resto)


def validar_ruc(ruc):
    """11 dígitos, empieza con 10 (persona) o 20 (empresa) y dígito verificador correcto."""
    if ruc in (None, ''):
        return None
    ruc = str(ruc).strip()
    if not re.fullmatch(r'(10|20)\d{9}', ruc):
        raise DatoInvalido('ruc_invalido', 'El RUC tiene 11 dígitos y empieza con 10 o 20')
    if digito_verificador_ruc(ruc[:10]) != int(ruc[10]):
        raise DatoInvalido('ruc_invalido', 'El dígito verificador del RUC no coincide')
    return ruc


def dominio_corporativo(email):
    """Dominio usado para detectar la misma empresa; None si es un correo público."""
    if not email:
        return None
    coincidencia = _PATRON_EMAIL.fullmatch(str(email).strip())
    if not coincidencia:
        raise DatoInvalido('email_invalido', 'Email con formato nombre@dominio.com')
    dominio = coincidencia.group(1).lower()
    return None if dominio in DOMINIOS_PUBLICOS else dominio


def segmento(monto_ganado_12m):
    """A: >= S/ 50 000 ganados en 12 meses · B: >= S/ 10 000 · C: el resto."""
    monto = Decimal(str(monto_ganado_12m))
    if monto >= UMBRAL_SEGMENTO_A:
        return 'A'
    if monto >= UMBRAL_SEGMENTO_B:
        return 'B'
    return 'C'


def debe_pasar_a_inactivo(estado, ultima_actividad_en, ahora):
    if estado != 'cliente' or ultima_actividad_en is None:
        return False
    return ahora - ultima_actividad_en > datetime.timedelta(days=DIAS_PARA_INACTIVO)


def validar_cuenta(datos):
    razon_social = (datos.get('razon_social') or '').strip()
    if not razon_social:
        raise DatoInvalido('campo_obligatorio', 'razon_social es obligatorio')
    return {
        'razon_social': razon_social[:150],
        'ruc': validar_ruc(datos.get('ruc')),
        'dominio_email': dominio_corporativo(datos.get('email')),
        'industria': (datos.get('industria') or None),
        'distrito': (datos.get('distrito') or None),
    }


def validar_contacto(datos):
    nombre = (datos.get('nombre') or '').strip()
    if not nombre:
        raise DatoInvalido('campo_obligatorio', 'nombre es obligatorio')
    email = datos.get('email')
    if email:
        dominio_corporativo(email)  # solo valida el formato
    if not email and not datos.get('telefono'):
        raise DatoInvalido('contacto_sin_medio', 'El contacto necesita email o teléfono')
    return {
        'nombre': nombre[:80],
        'apellido': (datos.get('apellido') or None),
        'email': email.strip().lower() if email else None,
        'telefono': (datos.get('telefono') or None),
        'cargo': (datos.get('cargo') or None),
    }


def es_principal_al_agregar(contactos_existentes, pedido_principal):
    """Regla: cada cuenta tiene exactamente un principal. El primer contacto lo es siempre."""
    return contactos_existentes == 0 or bool(pedido_principal)
