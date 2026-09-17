import geopandas as gpd
import pandas as pd

from src.config import (
    DEFAULT_UF,
    RAW_DIR,
    INTERIM_DIR,
)
from src.extract import (
    get_municipios_ibge,
    get_malha_municipios,
)


def carregar_municipios(uf=DEFAULT_UF):
    uf = str(uf).upper().strip()
    arquivo = INTERIM_DIR / f"municipios_{uf.lower()}_ibge.csv"

    if not arquivo.exists():
        get_municipios_ibge(uf)

    return pd.read_csv(
        arquivo,
        dtype={"codigo_ibge": "string"},
    )


def carregar_malha(uf=DEFAULT_UF):
    uf = str(uf).upper().strip()
    arquivo = RAW_DIR / f"malha_municipios_{uf.lower()}.geojson"

    if not arquivo.exists():
        get_malha_municipios(uf)

    mapa = gpd.read_file(arquivo)

    if "codarea" not in mapa.columns:
        raise ValueError(
            "A malha do IBGE não contém a coluna 'codarea'. "
            f"Colunas encontradas: {mapa.columns.tolist()}"
        )

    mapa["codarea"] = mapa["codarea"].astype(str)
    return mapa


def criar_base_geografica(uf=DEFAULT_UF):
    """Une a lista oficial de municípios do IBGE à geometria municipal."""
    uf = str(uf).upper().strip()

    municipios = carregar_municipios(uf)
    mapa = carregar_malha(uf)

    codigos_municipios = set(municipios["codigo_ibge"])
    codigos_mapa = set(mapa["codarea"])

    faltando = codigos_municipios - codigos_mapa
    sobrando = codigos_mapa - codigos_municipios

    if faltando or sobrando:
        raise ValueError(
            "Os códigos da API de Localidades e da API de Malhas não coincidem. "
            f"Sem geometria: {len(faltando)} | Sem município: {len(sobrando)}"
        )

    mapa = mapa.rename(columns={"codarea": "codigo_ibge"})

    base_geo = mapa.merge(
        municipios,
        on="codigo_ibge",
        how="left",
        validate="one_to_one",
    )

    base_geo = base_geo[
        [
            "codigo_ibge",
            "municipio_ibge",
            "geometry",
        ]
    ]

    if len(base_geo) != len(municipios):
        raise ValueError(
            "Quantidade de municípios e geometrias não coincide. "
            f"Municípios: {len(municipios)} | Geometrias: {len(base_geo)}"
        )

    INTERIM_DIR.mkdir(parents=True, exist_ok=True)
    arquivo_saida = INTERIM_DIR / f"municipios_{uf.lower()}_geometria.parquet"
    base_geo.to_parquet(arquivo_saida, index=False)

    print(f"\nBase geográfica de {uf}: {len(base_geo)} municípios.")
    return base_geo


if __name__ == "__main__":
    criar_base_geografica()
