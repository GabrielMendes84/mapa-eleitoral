from pathlib import Path


# =========================================================
# PASTAS
# =========================================================

BASE_DIR = Path(__file__).resolve().parent.parent

DATA_DIR = BASE_DIR / "data"
RAW_DIR = DATA_DIR / "raw"
INTERIM_DIR = DATA_DIR / "interim"
PROCESSED_DIR = DATA_DIR / "processed"
OUTPUTS_DIR = BASE_DIR / "outputs"


# =========================================================
# CONFIGURAÇÕES PADRÃO
# =========================================================

DEFAULT_ANO = 2022
DEFAULT_UF = "MG"
DEFAULT_TURNO = 1


# =========================================================
# CARGOS E SISTEMAS ELEITORAIS
# =========================================================

CARGOS_PROPORCIONAIS = {
    "DEPUTADO FEDERAL",
    "DEPUTADO ESTADUAL",
    "DEPUTADO DISTRITAL",
    "VEREADOR",
}

CARGOS_MAJORITARIOS = {
    "PRESIDENTE",
    "GOVERNADOR",
    "SENADOR",
    "PREFEITO",
}

CARGOS_MUNICIPAIS = {
    "PREFEITO",
    "VEREADOR",
}

CARGOS_DISPONIVEIS = [
    "DEPUTADO FEDERAL",
    "DEPUTADO ESTADUAL",
    "DEPUTADO DISTRITAL",
    "SENADOR",
    "GOVERNADOR",
    "PRESIDENTE",
    "PREFEITO",
    "VEREADOR",
]


# =========================================================
# FAIXAS DE VOTAÇÃO
# =========================================================

BINS_PROPORCIONAIS = [
    0,
    2,
    5,
    10,
    20,
    float("inf"),
]

LABELS_PROPORCIONAIS = [
    "0% a <2%",
    "2% a <5%",
    "5% a <10%",
    "10% a <20%",
    "20% ou mais",
]

BINS_MAJORITARIOS = [
    0,
    35,
    50,
    65,
    float("inf"),
]

LABELS_MAJORITARIOS = [
    "Menos de 35%",
    "35% a <50%",
    "50% a <65%",
    "65% ou mais",
]


# =========================================================
# CORES DOS MAPAS
# =========================================================

CORES_PROPORCIONAIS = {
    "0% a <2%": "#ffffff",
    "2% a <5%": "#c6dbef",
    "5% a <10%": "#6baed6",
    "10% a <20%": "#2171b5",
    "20% ou mais": "#08306b",
    "Não concorreu": "#e5e7eb",
    "Sem dados": "#d1d5db",
}

CORES_MAJORITARIOS = {
    "Menos de 35%": "#ffffff",
    "35% a <50%": "#9ecae1",
    "50% a <65%": "#3182bd",
    "65% ou mais": "#08519c",
    "Não concorreu": "#e5e7eb",
    "Sem dados": "#d1d5db",
}


def sistema_eleitoral(cargo):
    cargo = str(cargo).upper().strip()

    if cargo in CARGOS_PROPORCIONAIS:
        return "proporcional"

    if cargo in CARGOS_MAJORITARIOS:
        return "majoritário"

    raise ValueError(f"Cargo não reconhecido: {cargo}")


def cargo_municipal(cargo):
    return str(cargo).upper().strip() in CARGOS_MUNICIPAIS


def obter_faixas(cargo):
    sistema = sistema_eleitoral(cargo)

    if sistema == "proporcional":
        return (
            BINS_PROPORCIONAIS,
            LABELS_PROPORCIONAIS,
            CORES_PROPORCIONAIS,
        )

    return (
        BINS_MAJORITARIOS,
        LABELS_MAJORITARIOS,
        CORES_MAJORITARIOS,
    )


# =========================================================
# IBGE
# =========================================================

def ibge_municipios_url(uf):
    uf = str(uf).upper().strip()

    return (
        "https://servicodados.ibge.gov.br/"
        f"api/v1/localidades/estados/{uf}/municipios"
    )


def ibge_malha_url(uf):
    uf = str(uf).upper().strip()

    return (
        "https://servicodados.ibge.gov.br/"
        f"api/v4/malhas/estados/{uf}"
    )


# =========================================================
# TSE
# =========================================================

def tse_candidatos_url(ano):
    return (
        "https://cdn.tse.jus.br/"
        "estatistica/sead/odsele/"
        f"consulta_cand/consulta_cand_{ano}.zip"
    )


def tse_votacao_candidato_url(ano):
    return (
        "https://cdn.tse.jus.br/"
        "estatistica/sead/odsele/"
        "votacao_candidato_munzona/"
        f"votacao_candidato_munzona_{ano}.zip"
    )


def tse_detalhe_votacao_url(ano):
    return (
        "https://cdn.tse.jus.br/"
        "estatistica/sead/odsele/"
        "detalhe_votacao_munzona/"
        f"detalhe_votacao_munzona_{ano}.zip"
    )


TSE_CROSSWALK_URL = (
    "https://cdn.tse.jus.br/"
    "estatistica/sead/odsele/"
    "municipio_tse_ibge/"
    "municipio_tse_ibge.zip"
)
