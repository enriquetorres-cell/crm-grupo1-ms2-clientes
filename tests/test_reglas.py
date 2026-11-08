import datetime

import pytest

from src import reglas
from src.comun import DatoInvalido


def test_ruc_valido_de_sunat():
    assert reglas.validar_ruc('20131312955') == '20131312955'


@pytest.mark.parametrize('malo', ['20131312954', '30131312955', '2013131295', 'abcdefghijk'])
def test_ruc_invalido(malo):
    with pytest.raises(DatoInvalido):
        reglas.validar_ruc(malo)


def test_ruc_vacio_es_opcional():
    assert reglas.validar_ruc('') is None


def test_correo_publico_no_sirve_para_deduplicar():
    assert reglas.dominio_corporativo('ana@gmail.com') is None
    assert reglas.dominio_corporativo('Ana@Andina.PE') == 'andina.pe'


@pytest.mark.parametrize('monto, esperado', [(0, 'C'), (9999.99, 'C'), (10000, 'B'), (49999, 'B'), (50000, 'A')])
def test_segmento_por_monto_ganado(monto, esperado):
    assert reglas.segmento(monto) == esperado


def test_cliente_sin_actividad_por_90_dias_pasa_a_inactivo():
    hoy = datetime.datetime(2026, 11, 20, tzinfo=datetime.timezone.utc)
    assert reglas.debe_pasar_a_inactivo('cliente', hoy - datetime.timedelta(days=91), hoy)
    assert not reglas.debe_pasar_a_inactivo('cliente', hoy - datetime.timedelta(days=30), hoy)
    assert not reglas.debe_pasar_a_inactivo('prospecto', hoy - datetime.timedelta(days=200), hoy)


def test_primer_contacto_siempre_es_principal():
    assert reglas.es_principal_al_agregar(0, False)
    assert not reglas.es_principal_al_agregar(2, False)
    assert reglas.es_principal_al_agregar(2, True)


def test_contacto_necesita_email_o_telefono():
    with pytest.raises(DatoInvalido):
        reglas.validar_contacto({'nombre': 'Ana'})
    assert reglas.validar_contacto({'nombre': 'Ana', 'telefono': '987654321'})['telefono'] == '987654321'
