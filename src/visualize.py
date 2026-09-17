from pathlib import Path

import folium
import geopandas as gpd
from branca.element import Element

from src.config import OUTPUTS_DIR, obter_faixas
from src.election import slugify


# =========================================================
# CARREGAR BASE
# =========================================================

def carregar_parquet(caminho):
    caminho = Path(caminho)

    if not caminho.exists():
        raise FileNotFoundError(f"Arquivo não encontrado: {caminho}")

    return gpd.read_parquet(caminho)


# =========================================================
# PREPARAR BASE
# =========================================================

def preparar_base_mapa(base):
    base = base.copy()

    if not isinstance(base, gpd.GeoDataFrame):
        base = gpd.GeoDataFrame(base, geometry="geometry")

    if base.crs is None:
        raise ValueError("A geometria não possui CRS definido.")

    base = base.to_crs(epsg=4326)
    base = base[
        base.geometry.notna()
        & ~base.geometry.is_empty
    ].copy()

    try:
        base["geometry"] = base.geometry.make_valid()
    except AttributeError:
        pass

    base["codigo_ibge"] = (
        base["codigo_ibge"]
        .astype(str)
        .str.zfill(7)
    )

    base["classe_percentual"] = (
        base["classe_percentual"]
        .astype("string")
        .fillna("Sem dados")
        .astype(str)
    )

    base["votos_candidato_fmt"] = (
        base["votos_candidato"]
        .fillna(0)
        .astype(int)
        .map(lambda x: f"{x:,.0f}".replace(",", "."))
    )

    base["votos_validos_fmt"] = (
        base["votos_validos"]
        .fillna(0)
        .astype(int)
        .map(lambda x: f"{x:,.0f}".replace(",", "."))
    )

    base["percentual_fmt"] = (
        base["percentual_validos"]
        .fillna(0)
        .map(lambda x: f"{x:.2f}%".replace(".", ","))
    )

    return base


# =========================================================
# LEGENDA
# =========================================================

def adicionar_legenda(mapa, labels, cores, incluir_nao_concorreu=False):
    classes = list(labels)

    if incluir_nao_concorreu:
        classes.append("Não concorreu")

    itens = ""

    for classe in classes:
        cor = cores.get(classe, "#d1d5db")

        itens += f"""
        <div style="display:flex;align-items:center;margin-bottom:5px;">
            <span style="
                display:inline-block;
                width:18px;
                height:18px;
                background:{cor};
                margin-right:8px;
                border:1px solid #777;
            "></span>
            {classe}
        </div>
        """

    legenda = f"""
    <div style="
        position: fixed;
        bottom: 30px;
        right: 30px;
        width: 200px;
        z-index: 9999;
        background-color: white;
        border: 1px solid #999;
        border-radius: 6px;
        padding: 12px;
        font-size: 13px;
        box-shadow: 0 1px 5px rgba(0,0,0,0.25);
    ">
        <div style="font-weight:bold;margin-bottom:8px;">
            % dos votos válidos
        </div>
        {itens}
    </div>
    """

    mapa.get_root().html.add_child(Element(legenda))


# =========================================================
# TÍTULO
# =========================================================

def adicionar_titulo(mapa, titulo):
    html = f"""
    <div style="
        position: fixed;
        top: 15px;
        left: 50%;
        transform: translateX(-50%);
        z-index: 9999;
        background: rgba(255,255,255,0.94);
        padding: 10px 18px;
        border-radius: 6px;
        border: 1px solid #ccc;
        font-family: Arial, sans-serif;
        font-size: 18px;
        font-weight: bold;
        text-align: center;
    ">
        {titulo}
    </div>
    """

    mapa.get_root().html.add_child(Element(html))


# =========================================================
# MAPA
# =========================================================

def gerar_mapa_eleitoral(base, salvar=True):
    if base.empty:
        raise ValueError("A base eleitoral está vazia.")

    base = preparar_base_mapa(base)

    nome_candidato = base["nome_candidato"].iloc[0]
    numero_candidato = base["numero_candidato"].iloc[0]
    partido = base["partido"].iloc[0]
    cargo = base["cargo"].iloc[0]
    ano = base["ano"].iloc[0]
    uf = base["uf"].iloc[0]
    nome_municipio = base.get(
        "municipio_candidatura_nome",
        None,
    )

    _, labels, cores = obter_faixas(cargo)

    minx, miny, maxx, maxy = base.total_bounds
    centro_lat = (miny + maxy) / 2
    centro_lon = (minx + maxx) / 2

    mapa = folium.Map(
        location=[centro_lat, centro_lon],
        zoom_start=6,
        tiles=None,
        control_scale=True,
        prefer_canvas=True,
    )

    mapa.get_root().html.add_child(
        Element(
            """
            <style>
                .leaflet-container {
                    background: white !important;
                }
            </style>
            """
        )
    )

    def estilo(feature):
        classe = feature["properties"].get(
            "classe_percentual",
            "Sem dados",
        )

        return {
            "fillColor": cores.get(classe, "#d1d5db"),
            "color": "#6b7280",
            "weight": 0.55,
            "fillOpacity": 0.90,
        }

    def destaque(_feature):
        return {
            "color": "#111827",
            "weight": 2,
            "fillOpacity": 0.98,
        }

    folium.GeoJson(
        data=base.to_json(),
        name="Municípios",
        style_function=estilo,
        highlight_function=destaque,
        tooltip=folium.GeoJsonTooltip(
            fields=[
                "municipio_ibge",
                "votos_candidato_fmt",
                "votos_validos_fmt",
                "percentual_fmt",
                "classe_percentual",
            ],
            aliases=[
                "Município:",
                "Votos no candidato:",
                "Votos válidos:",
                "% dos votos válidos:",
                "Faixa:",
            ],
            localize=True,
            sticky=False,
            labels=True,
            style=(
                "background-color: white;"
                "color: #222;"
                "font-family: Arial;"
                "font-size: 13px;"
                "padding: 8px;"
            ),
        ),
    ).add_to(mapa)

    mapa.fit_bounds(
        [
            [miny, minx],
            [maxy, maxx],
        ]
    )

    incluir_nao_concorreu = "Não concorreu" in set(
        base["classe_percentual"].astype(str)
    )

    adicionar_legenda(
        mapa,
        labels=labels,
        cores=cores,
        incluir_nao_concorreu=incluir_nao_concorreu,
    )

    titulo = (
        f"{nome_candidato} ({numero_candidato}) - {partido}"
        f"<br>{str(cargo).title()} - {uf} - {ano}"
    )

    if nome_municipio is not None:
        valor = str(nome_municipio.iloc[0] if hasattr(nome_municipio, "iloc") else nome_municipio)
        if valor:
            titulo += f" - {valor}"

    adicionar_titulo(mapa, titulo)

    if salvar:
        OUTPUTS_DIR.mkdir(parents=True, exist_ok=True)

        nome_slug = slugify(nome_candidato)
        cargo_slug = slugify(cargo)

        arquivo = OUTPUTS_DIR / (
            f"mapa_{ano}_{str(uf).lower()}_"
            f"{cargo_slug}_{numero_candidato}_{nome_slug}.html"
        )

        mapa.save(arquivo)
        print(f"\nMapa salvo em:\n{arquivo}")

    return mapa


if __name__ == "__main__":
    print("Use carregar_parquet() e gerar_mapa_eleitoral().")
