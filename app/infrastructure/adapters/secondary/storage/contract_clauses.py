"""Cláusulas generales inamovibles de locación de servicios de entretenimiento (Perú).

Este módulo contiene el cuerpo normativo estándar e inalterable de los contratos de
EventPro, alineado con el Código Civil peruano (arts. 141, 141-A, 1315, 1764 y ss.),
la Ley N° 27269 (Firmas y Certificados Digitales), la Ley N° 29733 (Protección de Datos
Personales) y las reglas operativas y de control del negocio (RN-01 a RN-09, PC-01 a PC-12).
"""

from dataclasses import dataclass

from app.application.dtos.contract_dto import ContractData, PromoterIdentity

_SERVICE_CATEGORY_LABELS: dict[str, str] = {
    "SHOW": "Espectáculo artístico, animación y Hora Loca",
    "DJ": "Servicio de DJ, mezcla musical, sonido e iluminación",
    "DECORATION": "Ambientación y decoración temática",
    "TENTS": "Infraestructura, montaje y alquiler de toldos",
}


@dataclass(frozen=True)
class ContractClause:
    """Cláusula general inamovible del contrato."""

    ordinal: str
    title: str
    paragraphs: tuple[str, ...]


def service_category_label(category: str | None) -> str:
    """Traduce el código de categoría del catálogo a descripción legible para el contrato."""
    if not category:
        return "Servicios integrales de entretenimiento y producción para eventos"
    return _SERVICE_CATEGORY_LABELS.get(category, category)


def build_immutable_clauses(
    promoter: PromoterIdentity,
    data: ContractData,
) -> tuple[ContractClause, ...]:
    """Devuelve las trece cláusulas generales inamovibles del contrato."""
    advance_pct = data.advance_percent
    city = promoter.city

    return (
        ContractClause(
            ordinal="CLÁUSULA PRIMERA",
            title="NATURALEZA JURÍDICA, OBJETO Y AUTONOMÍA OPERATIVA",
            paragraphs=(
                f"El presente contrato se celebra bajo la modalidad de Locación de Servicios "
                f"de Entretenimiento y Producción de Eventos, regulada supletoriamente por los "
                f"artículos 1764 y siguientes del Código Civil peruano. En virtud de este "
                f"acuerdo, {promoter.legal_name} (en adelante, EL LOCADOR), operando "
                f"comercialmente como {promoter.commercial_name}, se obliga a ejecutar a favor "
                f"de EL COMITENTE únicamente el paquete, temática, extras y horario detallados "
                f"en la Sección I (Condiciones Particulares del Servicio Pactado).",
                "EL LOCADOR presta sus servicios con plena autonomía técnica, artística y "
                "operativa, pudiendo ejecutar la presentación mediante artistas, animadores, "
                "DJs, decoradores o personal técnico convocado bajo modalidad independiente. "
                "Este contrato es de naturaleza estrictamente civil y no genera vínculo "
                "laboral, subordinación, dependencia ni obligación de beneficios sociales "
                "entre EL COMITENTE y EL LOCADOR o el personal asignado al evento.",
            ),
        ),
        ContractClause(
            ordinal="CLÁUSULA SEGUNDA",
            title="RETRIBUCIÓN, ADELANTO DE RESERVA Y CONDICIÓN PREVIA AL INICIO",
            paragraphs=(
                f"La contraprestación total por los servicios y movilidad se fija en los "
                f"importes consignados en la Sección I. El adelanto obligatorio equivalente al "
                f"{advance_pct}% del subtotal de servicios tiene por finalidad asegurar la "
                f"reserva de fecha, elenco e inventario; el costo de movilidad no integra la "
                f"base del adelanto y se liquida íntegramente junto con el saldo restante.",
                "CONDICIÓN SUSPENSIVA OBLIGATORIA DE INICIO (REGLA PRE-SHOW): Ningún show, "
                "presentación musical, armado de toldo ni instalación de ambientación podrá "
                "iniciar sin que EL COMITENTE haya cancelado el 100% del saldo total pendiente "
                "(saldo de servicios más movilidad) antes de la hora programada de inicio, "
                "mediante Yape, Plin, transferencia bancaria verificable o efectivo contra "
                "registro de evidencia por el operador designado en sitio.",
                "De mantenerse un saldo impago al momento previsto para el comienzo del "
                "servicio, EL LOCADOR queda facultado a suspender el inicio hasta verificar el "
                "pago total, sin que el tiempo de demora sea recuperable ni genere penalidad "
                "para EL LOCADOR.",
            ),
        ),
        ContractClause(
            ordinal="CLÁUSULA TERCERA",
            title="MOVILIDAD, ACCESO AL RECINTO, MONTAJE Y DESMONTAJE",
            paragraphs=(
                "Salvo que en la Sección I conste expresamente que EL COMITENTE proporciona "
                "el transporte de ida y vuelta para el personal y equipos, el concepto de "
                "movilidad cubre el desplazamiento desde la base operativa en Lima hasta el "
                "lugar del evento y su retorno.",
                "EL COMITENTE deberá garantizar el acceso libre, oportuno y sin restricciones "
                "de vehículos, personal técnico, artistas, vestuario e infraestructura al local "
                "con una anticipación razonable (mínimo 30 minutos para shows/DJ y conforme "
                "a coordinación previa para toldos o decoración), así como las facilidades de "
                "carga, descarga y retiro inmediato al concluir el servicio.",
                "Si por disposición del local, junta vecinal, administración o terceros "
                "ajenos a EL LOCADOR se impidiera o retrasara el ingreso o el retiro de los "
                "equipos y estructuras, EL COMITENTE asumirá los costos logísticos adicionales "
                "de custodia o traslado extraordinario que ello origine.",
            ),
        ),
        ContractClause(
            ordinal="CLÁUSULA CUARTA",
            title="CONDICIONES DEL ESPACIO FÍSICO Y SUMINISTRO ELÉCTRICO",
            paragraphs=(
                "Para servicios que involucren sonido, DJ, iluminación, efectos especiales, "
                "decoración o toldos, EL COMITENTE se obliga a proporcionar un área física "
                "despejada, segura, nivelada y protegida contra humedad o lluvia directa, "
                "con dimensiones acordes al servicio contratado.",
                "Asimismo, EL COMITENTE deberá proveer un punto de suministro eléctrico "
                "estable de 220V con capacidad suficiente y debidamente protegido. EL LOCADOR "
                "no asume responsabilidad por interrupciones, caídas de tensión, cortes de "
                "energía o daños derivados de instalaciones eléctricas defectuosas del local; "
                "dichas contingencias no suspenden ni prorrogan el horario pactado.",
            ),
        ),
        ContractClause(
            ordinal="CLÁUSULA QUINTA",
            title="PUNTUALIDAD, TOLERANCIA Y EXTENSIONES EN VIVO",
            paragraphs=(
                "El servicio se ejecutará estrictamente dentro de la ventana horaria pactada "
                "en la Sección I. Los retrasos en el inicio ocasionados por demoras del evento, "
                "falta de acceso al local, ausencia de energía eléctrica o falta de pago del "
                "saldo pendiente no obligan a EL LOCADOR a extender el horario de término.",
                "Cualquier ampliación del tiempo de presentación o espera adicional solicitada "
                "por EL COMITENTE durante el desarrollo del evento constituye una Extensión en "
                "Vivo, sujeta obligatoriamente a la disponibilidad de agenda del elenco, "
                "inventario y tiempos de tránsito hacia compromisos posteriores, así como al "
                "acuerdo de tarifa adicional y su pago inmediato con registro de evidencia "
                "antes de ejecutarse el tiempo extra.",
            ),
        ),
        ContractClause(
            ordinal="CLÁUSULA SEXTA",
            title="CUSTODIA, DAÑOS A EQUIPOS, VESTUARIO Y SEGURIDAD DEL ELENCO",
            paragraphs=(
                "Desde el ingreso del personal y bienes de EL LOCADOR al recinto hasta su "
                "retiro efectivo, EL COMITENTE asume la responsabilidad civil y patrimonial "
                "por la seguridad e integridad física del equipo humano y de los bienes "
                "asignados (vestuario, muñecos gigantes, utilería, consolas, parlantes, "
                "luces, estructuras de toldos y elementos decorativos).",
                "EL COMITENTE responderá íntegramente por cualquier daño, rotura, quemadura, "
                "mancha irreversible, extravío o robo ocasionado por invitados, asistentes, "
                "menores sin supervisión, personal del local o terceros, obligándose a cubrir "
                "el costo de reparación o reposición a valor comercial de mercado.",
                "Ante situaciones de violencia, hostigamiento, agresión física o verbal contra "
                "cualquier integrante del elenco o riesgo grave de seguridad, EL LOCADOR podrá "
                "dar por concluida la presentación de forma inmediata sin devolución de importes.",
            ),
        ),
        ContractClause(
            ordinal="CLÁUSULA SÉPTIMA",
            title="PERMISOS MUNICIPALES, AUTORIZACIONES Y DERECHOS DE AUTOR",
            paragraphs=(
                "EL COMITENTE declara bajo su exclusiva responsabilidad contar con todas las "
                "autorizaciones municipales, permisos de condominio o club, licencias de "
                "evento y medidas de defensa civil requeridas en el distrito de realización.",
                "Igualmente, corresponde exclusivamente a EL COMITENTE gestionar y pagar, "
                "cuando la naturaleza pública o privada del evento lo exija, los derechos de "
                "autor y conexos ante sociedades de gestión colectiva (tales como APDAYC y "
                "UNIMPRO), quedando EL LOCADOR liberado de toda multa, sanción administrativa "
                "o retención de equipos derivada de la falta de dichos permisos.",
            ),
        ),
        ContractClause(
            ordinal="CLÁUSULA OCTAVA",
            title="CANCELACIÓN, REPROGRAMACIÓN Y SOBRECUPO",
            paragraphs=(
                "En caso de cancelación unilateral del evento por parte de EL COMITENTE, "
                "el adelanto abonado no será reembolsable, quedando a favor de EL LOCADOR "
                "como compensación por la reserva exclusiva de fecha, bloqueo de recursos "
                "y lucro cesante.",
                "EL COMITENTE podrá solicitar por única vez la reprogramación de fecha u "
                "horario con una anticipación mínima de siete (7) días calendario respecto a "
                "la fecha pactada, la cual quedará estrictamente sujeta a la disponibilidad "
                "de agenda, elencos e inventario de EL LOCADOR dentro de los noventa (90) "
                "días calendario siguientes, aplicándose los ajustes de movilidad vigentes si "
                "cambiara la ubicación.",
                "Únicamente procederá la devolución íntegra del adelanto cuando el servicio "
                "no pueda prestarse por causa imputable a EL LOCADOR o cuando una solicitud "
                "sujeta a aprobación manual por sobrecupo simultáneo sea rechazada por la "
                "administración antes de la emisión definitiva del contrato.",
            ),
        ),
        ContractClause(
            ordinal="CLÁUSULA NOVENA",
            title="CASO FORTUITO, FUERZA MAYOR Y CONDICIONES CLIMÁTICAS",
            paragraphs=(
                "Conforme al artículo 1315 del Código Civil peruano, ninguna de las partes "
                "será responsable por el incumplimiento o retraso derivado de caso fortuito o "
                "fuerza mayor debidamente acreditados (sismos, desastres naturales, cierres "
                "viales graves, estados de emergencia o prohibiciones gubernamentales).",
                "En eventos al aire libre con toldos, sonido o iluminación, si lluvias "
                "intensas, descargas eléctricas o vientos fuertes ponen en riesgo la "
                "estabilidad estructural o la seguridad eléctrica de asistentes y personal, "
                "EL LOCADOR podrá suspender preventivamente la operación eléctrica o el show. "
                "Ante fuerza mayor, las partes priorizarán la reprogramación de fecha de "
                "mutuo acuerdo, reconociéndose los gastos logísticos ya ejecutados.",
            ),
        ),
        ContractClause(
            ordinal="CLÁUSULA DÉCIMA",
            title="OBSERVACIONES ESPECIALES, DERECHOS DE IMAGEN Y CONFIDENCIALIDAD",
            paragraphs=(
                "Las preferencias artísticas, restricciones musicales o indicaciones de "
                "coordinación consignadas en el apartado OBSERVACIONES ESPECIALES DEL CLIENTE "
                "forman parte vinculante del servicio, siempre que no contravengan la ley, la "
                "seguridad del personal ni el alcance del paquete contratado. En caso de "
                "acuerdos específicos en modo manual, estos solo complementan y no derogan "
                "las presentes cláusulas generales.",
                "EL COMITENTE autoriza a EL LOCADOR a capturar material fotográfico o "
                "audiovisual breve de su propio espectáculo con fines estrictamente "
                "promocionales y de portafolio, salvo que deje constancia expresa de su "
                "oposición por escrito en las observaciones previas a la firma.",
            ),
        ),
        ContractClause(
            ordinal="CLÁUSULA DÉCIMO PRIMERA",
            title="PROTECCIÓN DE DATOS PERSONALES (LEY N° 29733)",
            paragraphs=(
                "De conformidad con la Ley N° 29733, Ley de Protección de Datos Personales, "
                "y su Reglamento, EL COMITENTE autoriza el tratamiento de sus datos de "
                "identificación (nombre completo, DNI/RUC, teléfono WhatsApp, dirección del "
                "evento) y de los registros técnicos de firma electrónica (dirección IP, "
                "navegador, marca temporal, traza de verificación OTP e imagen de firma) con "
                "la exclusiva finalidad de ejecutar el contrato, coordinar la logística del "
                "servicio, cumplir obligaciones legales y conservar evidencia probatoria.",
            ),
        ),
        ContractClause(
            ordinal="CLÁUSULA DÉCIMO SEGUNDA",
            title="CONTRATACIÓN ELECTRÓNICA, VERIFICACIÓN OTP Y SELLO CRIPTOGRÁFICO",
            paragraphs=(
                "Las partes acuerdan expresamente la validez jurídica, eficacia y fuerza "
                "probatoria del presente contrato celebrado por medios electrónicos, al "
                "amparo de los artículos 141 y 141-A del Código Civil peruano y la Ley "
                "N° 27269, Ley de Firmas y Certificados Digitales.",
                "La manifestación de voluntad de EL COMITENTE se perfecciona mediante el "
                "acceso al enlace único remitido por WhatsApp, la verificación de un código "
                "temporal de un solo uso (OTP), el trazado de su firma manuscrita digital y "
                "la aceptación expresa de los términos. Al completarse el proceso, el sistema "
                "anexa la hoja final de Constancia de Firma Electrónica y aplica un sello "
                "criptográfico PAdES íntegro sobre la totalidad del documento PDF.",
            ),
        ),
        ContractClause(
            ordinal="CLÁUSULA DÉCIMO TERCERA",
            title="SOLUCIÓN DE CONTROVERSIAS, DOMICILIO Y JURISDICCIÓN",
            paragraphs=(
                f"Las partes señalan como sus domicilios válidos los indicados en la "
                f"comparecencia de este documento y reconocen el canal WhatsApp declarado "
                f"como medio válido de coordinación operativa. Toda controversia derivada de "
                f"la interpretación o ejecución de este contrato se procurará resolver en "
                f"trato directo de buena fe; de persistir, las partes se someten a la "
                f"jurisdicción de los Jueces y Tribunales del Distrito Judicial de {city}, "
                f"Perú, renunciando expresamente a cualquier otro fuero.",
            ),
        ),
    )
