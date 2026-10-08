"""Zonas tarifarias de la contingencia de movilidad (RN-03, escenario C).

Distritos de Lima Metropolitana y del Callao agrupados por cercanía a la base de operaciones.
La asignación es un supuesto pendiente de validar con el negocio; un distrito desconocido se
asigna a la zona 3 para no cobrar de menos (el encargado puede corregirlo con el override).
"""

import unicodedata

from app.domain.value_objects.mobility import MobilityZone

_ZONE_1 = (
    "Lima",
    "Breña",
    "Jesús María",
    "Lince",
    "Pueblo Libre",
    "Magdalena del Mar",
    "San Miguel",
    "San Isidro",
    "Miraflores",
    "Surquillo",
    "La Victoria",
    "San Borja",
    "San Luis",
    "Rímac",
)
_ZONE_2 = (
    "Santiago de Surco",
    "Barranco",
    "Chorrillos",
    "La Molina",
    "Ate",
    "Santa Anita",
    "El Agustino",
    "San Martín de Porres",
    "Los Olivos",
    "Independencia",
    "San Juan de Miraflores",
    "Callao",
    "Bellavista",
    "La Perla",
    "La Punta",
    "Carmen de la Legua Reynoso",
)
_ZONE_3 = (
    "Ancón",
    "Carabayllo",
    "Chaclacayo",
    "Cieneguilla",
    "Comas",
    "Lurigancho",
    "Lurín",
    "Pachacámac",
    "Pucusana",
    "Puente Piedra",
    "Punta Hermosa",
    "Punta Negra",
    "San Bartolo",
    "San Juan de Lurigancho",
    "Santa María del Mar",
    "Santa Rosa",
    "Villa El Salvador",
    "Villa María del Triunfo",
    "Ventanilla",
    "Mi Perú",
)

_ALIASES = {
    "cercado de lima": "lima",
    "lima cercado": "lima",
    "surco": "santiago de surco",
    "magdalena": "magdalena del mar",
    "sjl": "san juan de lurigancho",
    "sjm": "san juan de miraflores",
    "smp": "san martin de porres",
    "vmt": "villa maria del triunfo",
    "ves": "villa el salvador",
    "chosica": "lurigancho",
}


def normalize_district(name: str) -> str:
    """Minúsculas, sin tildes y con espacios colapsados (``" SAN  Isidro "`` → ``san isidro``)."""

    decomposed = unicodedata.normalize("NFKD", name)
    without_accents = "".join(char for char in decomposed if not unicodedata.combining(char))
    return " ".join(without_accents.casefold().split())


def _build_table() -> dict[str, MobilityZone]:
    table: dict[str, MobilityZone] = {}
    for zone, districts in (
        (MobilityZone.ZONE_1, _ZONE_1),
        (MobilityZone.ZONE_2, _ZONE_2),
        (MobilityZone.ZONE_3, _ZONE_3),
    ):
        for district in districts:
            table[normalize_district(district)] = zone
    return table


DISTRICT_ZONES: dict[str, MobilityZone] = _build_table()


def zone_for_district(district: str) -> MobilityZone:
    """Zona del distrito; los desconocidos (y los textos vacíos) caen en la zona 3."""

    key = normalize_district(district)
    key = _ALIASES.get(key, key)
    return DISTRICT_ZONES.get(key, MobilityZone.ZONE_3)
