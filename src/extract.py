import json

import geopandas as gpd
import pandas as pd
import requests

from src.config import (
    DEFAULT_UF,
    RAW_DIR,
    INTERIM_DIR,
    ibge_municipios_url,
    ibge_malha_url,
)


def get_municipios_ibge(uf=DEFAULT_UF):
    """Consulta a API de Localidades do IBGE e salva dados brutos e tratados."""
    uf = str(uf).upper().strip()

    print(f"Consultando municípios do IBGE para {uf}...")

    response = requests.get(
        ibge_municipios_url(uf),
        timeout=30,
    )
    response.raise_for_status()
    dados = response.json()

    RAW_DIR.mkdir(parents=True, exist_ok=True)
    INTERIM_DIR.mkdir(parents=True, exist_ok=True)

    arquivo_json = RAW_DIR / f"municipios_{uf.lower()}_ibge.json"
    with open(arquivo_json, "w", encoding="utf-8") as arquivo:
        json.dump(dados, arquivo, ensure_ascii=False, indent=2)

    municipios = pd.DataFrame(dados)[["id", "nome"]].copy()
    municipios = municipios.rename(
        columns={
            "id": "codigo_ibge",
            "nome": "municipio_ibge",
        }
    )
    municipios["codigo_ibge"] = municipios["codigo_ibge"].astype(str)

    arquivo_csv = INTERIM_DIR / f"municipios_{uf.lower()}_ibge.csv"
    municipios.to_csv(arquivo_csv, index=False, encoding="utf-8-sig")

    print(f"Municípios encontrados: {len(municipios)}")
    return municipios


def get_malha_municipios(uf=DEFAULT_UF):
    """Consulta a API de Malhas do IBGE e salva a malha municipal em GeoJSON."""
    uf = str(uf).upper().strip()

    print(f"\nConsultando malha municipal de {uf}...")

    params = {
        "formato": "application/vnd.geo+json",
        "qualidade": "minima",
        "intrarregiao": "municipio",
    }

    response = requests.get(
        ibge_malha_url(uf),
        params=params,
        timeout=120,
    )
    response.raise_for_status()

    RAW_DIR.mkdir(parents=True, exist_ok=True)
    arquivo_geojson = RAW_DIR / f"malha_municipios_{uf.lower()}.geojson"

    with open(arquivo_geojson, "wb") as arquivo:
        arquivo.write(response.content)

    mapa = gpd.read_file(arquivo_geojson)
    print(f"Geometrias encontradas: {len(mapa)}")
    return mapa


def main():
    municipios = get_municipios_ibge()
    mapa = get_malha_municipios()

    print("\nMunicípios:", len(municipios))
    print("Geometrias:", len(mapa))
    print("Colunas:", mapa.columns.tolist())


if __name__ == "__main__":
    main()
