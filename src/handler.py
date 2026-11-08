"""MS2 · Clientes: cuentas y contactos. PostgreSQL clientes_db, un schema por tenant.

Consume (cola crm-ms2): tenant.creado, lead.convertido, oportunidad.ganada.
"""
from decimal import Decimal

from . import db, reglas
from .comun import (NoEncontrado, ReglaNoCumplida, ahora, entero, enrutar, leer_cuerpo, log,
                    paginacion, parametro, procesar_cola, puede_ver, responder, ruta)


def _cuenta_visible(con, ctx, cuenta_id):
    cuenta = db.fila(con, 'SELECT * FROM cuentas WHERE id = :id', id=cuenta_id)
    if not cuenta or not puede_ver(ctx, cuenta['propietario']):
        raise NoEncontrado('cuenta_no_encontrada', cuenta_id)
    return cuenta


def _buscar_duplicado(con, ruc, dominio):
    """Regla de duplicados: misma empresa = mismo RUC o mismo dominio corporativo."""
    if ruc:
        cuenta = db.fila(con, 'SELECT * FROM cuentas WHERE ruc = :ruc', ruc=ruc)
        if cuenta:
            return cuenta
    if dominio:
        return db.fila(con, 'SELECT * FROM cuentas WHERE dominio_email = :d ORDER BY id LIMIT 1', d=dominio)
    return None


def _insertar_cuenta(con, datos, propietario, lead_id=None):
    return db.fila(
        con,
        """INSERT INTO cuentas (ruc, razon_social, dominio_email, industria, distrito, propietario, lead_id)
           VALUES (:ruc, :razon_social, :dominio_email, :industria, :distrito, :propietario, :lead_id)
           RETURNING *""",
        propietario=propietario, lead_id=lead_id, **datos,
    )


def _insertar_contacto(con, cuenta_id, datos, pedido_principal):
    existentes = db.fila(con, 'SELECT count(*) AS n FROM contactos WHERE cuenta_id = :c', c=cuenta_id)['n']
    principal = reglas.es_principal_al_agregar(existentes, pedido_principal)
    if principal:
        con.run('UPDATE contactos SET es_principal = FALSE WHERE cuenta_id = :c AND es_principal', c=cuenta_id)
    return db.fila(
        con,
        """INSERT INTO contactos (cuenta_id, nombre, apellido, email, telefono, cargo, es_principal)
           VALUES (:cuenta_id, :nombre, :apellido, :email, :telefono, :cargo, :principal)
           RETURNING *""",
        cuenta_id=cuenta_id, principal=principal, **datos,
    )


# ---------- Rutas ----------

def salud(event, ctx):
    return responder(200, {'status': 'ok', 'servicio': 'ms2'})


def listar_cuentas(event, ctx):
    page, limit = paginacion(event)
    con = db.conexion(ctx['tenant_id'])
    condiciones, params = [], {}
    if parametro(event, 'estado'):
        condiciones.append('estado = :estado')
        params['estado'] = parametro(event, 'estado')
    if parametro(event, 'segmento'):
        condiciones.append('segmento = :segmento')
        params['segmento'] = parametro(event, 'segmento').upper()
    if parametro(event, 'q'):
        condiciones.append('razon_social ILIKE :q')
        params['q'] = f'%{parametro(event, "q")}%'
    if ctx['rol'] == 'vendedor':
        condiciones.append('propietario = :yo')
        params['yo'] = ctx['usuario_id']
    # Solo se concatenan fragmentos fijos; los valores van como parámetros.
    where = f'WHERE {" AND ".join(condiciones)}' if condiciones else ''
    total = db.fila(con, f'SELECT count(*) AS total FROM cuentas {where}', **params)['total']
    items = db.filas(
        con, f'SELECT * FROM cuentas {where} ORDER BY id DESC LIMIT :limit OFFSET :offset',
        limit=limit, offset=(page - 1) * limit, **params,
    )
    return responder(200, {'total': total, 'page': page, 'limit': limit, 'items': items})


def obtener_cuenta(event, ctx):
    con = db.conexion(ctx['tenant_id'])
    cuenta = _cuenta_visible(con, ctx, entero(ruta(event, 'id'), 'id', minimo=1))
    cuenta['contactos'] = db.filas(
        con, 'SELECT * FROM contactos WHERE cuenta_id = :c ORDER BY es_principal DESC, id', c=cuenta['id'])
    return responder(200, cuenta)


def crear_cuenta(event, ctx):
    datos = reglas.validar_cuenta(leer_cuerpo(event))
    con = db.conexion(ctx['tenant_id'])
    with db.transaccion(con):
        duplicada = _buscar_duplicado(con, datos['ruc'], datos['dominio_email'])
        if duplicada:
            raise ReglaNoCumplida('cuenta_existente', {'id': duplicada['id'], 'razon_social': duplicada['razon_social']})
        cuenta = _insertar_cuenta(con, datos, ctx['usuario_id'])
    return responder(201, cuenta)


def agregar_contacto(event, ctx):
    cuerpo = leer_cuerpo(event)
    datos = reglas.validar_contacto(cuerpo)
    con = db.conexion(ctx['tenant_id'])
    with db.transaccion(con):
        cuenta = _cuenta_visible(con, ctx, entero(ruta(event, 'id'), 'id', minimo=1))
        contacto = _insertar_contacto(con, cuenta['id'], datos, cuerpo.get('es_principal'))
    return responder(201, contacto)


def marcar_principal(event, ctx):
    """PATCH /ms2/contactos/{id} {"es_principal": true}: desmarca al anterior en la misma transacción."""
    if leer_cuerpo(event).get('es_principal') is not True:
        raise ReglaNoCumplida('principal_obligatorio', 'Solo se puede marcar otro contacto como principal')
    con = db.conexion(ctx['tenant_id'])
    with db.transaccion(con):
        contacto = db.fila(con, 'SELECT * FROM contactos WHERE id = :id', id=entero(ruta(event, 'id'), 'id', minimo=1))
        if not contacto:
            raise NoEncontrado('contacto_no_encontrado', ruta(event, 'id'))
        _cuenta_visible(con, ctx, contacto['cuenta_id'])
        con.run('UPDATE contactos SET es_principal = FALSE WHERE cuenta_id = :c AND es_principal', c=contacto['cuenta_id'])
        contacto = db.fila(con, 'UPDATE contactos SET es_principal = TRUE WHERE id = :id RETURNING *', id=contacto['id'])
    return responder(200, contacto)


RUTAS = {
    'GET /ms2/health': salud,
    'GET /ms2/cuentas': listar_cuentas,
    'GET /ms2/cuentas/{id}': obtener_cuenta,
    'POST /ms2/cuentas': crear_cuenta,
    'POST /ms2/cuentas/{id}/contactos': agregar_contacto,
    'PATCH /ms2/contactos/{id}': marcar_principal,
}


def main(event, _context):
    return enrutar(RUTAS, event)


# ---------- Consumidor de eventos ----------

def _al_convertir_lead(con, datos):
    """lead.convertido -> crea la cuenta y su contacto, o se vincula a la empresa que ya existe."""
    cuenta_datos = reglas.validar_cuenta({
        'razon_social': datos.get('empresa'), 'ruc': datos.get('ruc'), 'email': datos.get('email'),
        'industria': datos.get('industria'), 'distrito': datos.get('distrito'),
    })
    cuenta = _buscar_duplicado(con, cuenta_datos['ruc'], cuenta_datos['dominio_email'])
    if cuenta:
        con.run('UPDATE cuentas SET lead_id = COALESCE(lead_id, :l) WHERE id = :id', l=datos['lead_id'], id=cuenta['id'])
    else:
        cuenta = _insertar_cuenta(con, cuenta_datos, datos.get('propietario'), datos['lead_id'])
    if datos.get('email') or datos.get('telefono'):
        contacto = reglas.validar_contacto({
            'nombre': datos.get('nombre') or datos.get('empresa'), 'apellido': datos.get('apellido'),
            'email': datos.get('email'), 'telefono': datos.get('telefono'), 'cargo': datos.get('cargo'),
        })
        _insertar_contacto(con, cuenta['id'], contacto, pedido_principal=False)


def _al_ganar_oportunidad(con, datos):
    """oportunidad.ganada -> la cuenta pasa a cliente y se recalcula su segmento."""
    if datos.get('cuenta_id'):
        cuenta = db.fila(con, 'SELECT * FROM cuentas WHERE id = :id', id=int(datos['cuenta_id']))
    else:
        cuenta = db.fila(con, 'SELECT * FROM cuentas WHERE lead_id = :l', l=datos.get('lead_id'))
    if not cuenta:
        log.warning('oportunidad.ganada sin cuenta asociada: %s', datos)
        return
    # Simplificación: se acumula el total ganado; la ventana real de 12 meses se recalcula en un job.
    nuevo_monto = Decimal(str(cuenta['monto_ganado_12m'])) + Decimal(str(datos.get('monto', 0)))
    con.run(
        """UPDATE cuentas SET estado = 'cliente', monto_ganado_12m = :m, segmento = :s,
                  ultima_actividad_en = :ahora WHERE id = :id""",
        m=nuevo_monto, s=reglas.segmento(nuevo_monto), ahora=ahora(), id=cuenta['id'],
    )


MANEJADORES = {
    'lead.convertido': _al_convertir_lead,
    'oportunidad.ganada': _al_ganar_oportunidad,
}


def _manejar(mensaje):
    if mensaje['evento'] == 'tenant.creado':
        db.crear_schema(mensaje['tenant_id'])
        return
    manejador = MANEJADORES.get(mensaje['evento'])
    if manejador is None:
        log.info('Evento ignorado: %s', mensaje['evento'])
        return
    con = db.conexion(mensaje['tenant_id'])
    with db.transaccion(con):
        if db.ya_procesado(con, mensaje['id']):
            return
        manejador(con, mensaje['datos'])


def consumidor(event, _context):
    return procesar_cola(event, _manejar)
