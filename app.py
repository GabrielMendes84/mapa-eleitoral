import geopandas as gpd
import pandas as pd
import streamlit as st
from streamlit_folium import st_folium

from src.config import (
    CARGOS_DISPONIVEIS,
    CARGOS_MUNICIPAIS,
    DEFAULT_ANO,
    DEFAULT_TURNO,
    DEFAULT_UF,
    obter_faixas,
    sistema_eleitoral,
)
from src.election import (
    caminho_resultado,
    construir_mapa_eleitoral,
    slugify,
)
from src.extract import get_municipios_ibge
from src.tse import (
    codigo_ibge_para_tse,
    listar_candidatos,
)
from src.visualize import gerar_mapa_eleitoral


# =========================================================
# CONFIGURAÇÃO
# =========================================================

st.set_page_config(
    page_title="Mapa Eleitoral",
    page_icon="🗳️",
    layout="wide",
)

UFS = [
    "AC", "AL", "AP", "AM", "BA", "CE", "DF", "ES", "GO",
    "MA", "MT", "MS", "MG", "PA", "PB", "PR", "PE", "PI",
    "RJ", "RN", "RS", "RO", "RR", "SC", "SP", "SE", "TO",
]


# =========================================================
# CACHE / FUNÇÕES AUXILIARES
# =========================================================

@st.cache_data(show_spinner=False)
def carregar_municipios_ui(uf):
    return get_municipios_ibge(uf)


@st.cache_data(show_spinner=False)
def carregar_candidatos_ui(ano, uf, cargo, municipio_tse=None):
    return listar_candidatos(
        ano=ano,
        uf=uf,
        cargo=cargo,
        municipio_tse=municipio_tse,
    )


def descricao_candidato(linha):
    nome = str(linha.get("NM_URNA_CANDIDATO", ""))
    numero = str(linha.get("NR_CANDIDATO", ""))
    partido = str(linha.get("SG_PARTIDO", ""))
    return f"{nome} ({numero}) - {partido}"


def formatar_numero(valor):
    if pd.isna(valor):
        return "—"
    return f"{valor:,.0f}".replace(",", ".")


def formatar_percentual(valor):
    if pd.isna(valor):
        return "—"
    return f"{valor:.2f}%".replace(".", ",")


def carregar_ou_processar(
    ano,
    uf,
    turno,
    cargo,
    candidato,
    municipio_tse=None,
    municipio_ibge=None,
    nome_municipio=None,
):
    arquivo = caminho_resultado(
        ano=ano,
        uf=uf,
        cargo=cargo,
        candidato=candidato,
        municipio_tse=municipio_tse,
    )

    if arquivo.exists():
        return gpd.read_parquet(arquivo)

    return construir_mapa_eleitoral(
        ano=ano,
        uf=uf,
        turno=turno,
        cargo=cargo,
        candidato=candidato,
        municipio_tse=municipio_tse,
        municipio_ibge=municipio_ibge,
        nome_municipio=nome_municipio,
    )


def preparar_base_visivel(base, cargo, classes_selecionadas):
    base = base.copy()

    return base[
        base["classe_percentual"]
        .astype(str)
        .isin(classes_selecionadas)
    ].copy()


def resumo_base(base):
    validos = base["votos_validos"].dropna()
    votos = base["votos_candidato"].dropna()

    total_votos = votos.sum() if not votos.empty else 0
    total_validos = validos.sum() if not validos.empty else 0

    percentual = (
        100 * total_votos / total_validos
        if total_validos > 0
        else float("nan")
    )

    municipios_com_dados = int(base["votos_validos"].notna().sum())

    return {
        "votos": total_votos,
        "validos": total_validos,
        "percentual": percentual,
        "municipios": municipios_com_dados,
    }


def exibir_metricas(base):
    resumo = resumo_base(base)

    c1, c2, c3, c4 = st.columns(4)

    c1.metric("Votos", formatar_numero(resumo["votos"]))
    c2.metric("Votos válidos", formatar_numero(resumo["validos"]))
    c3.metric("% dos votos válidos", formatar_percentual(resumo["percentual"]))
    c4.metric("Municípios com dados", formatar_numero(resumo["municipios"]))


def exibir_tabela_individual(base):
    tabela = base[
        [
            "municipio_ibge",
            "votos_candidato",
            "votos_validos",
            "percentual_validos",
            "classe_percentual",
        ]
    ].copy()

    tabela = tabela[tabela["votos_validos"].notna()]
    tabela = tabela.sort_values(
        ["percentual_validos", "municipio_ibge"],
        ascending=[False, True],
    ).reset_index(drop=True)
    tabela.index += 1

    st.dataframe(
        tabela,
        use_container_width=True,
        column_config={
            "municipio_ibge": "Município",
            "votos_candidato": st.column_config.NumberColumn("Votos", format="%d"),
            "votos_validos": st.column_config.NumberColumn("Votos válidos", format="%d"),
            "percentual_validos": st.column_config.NumberColumn("% válidos", format="%.2f%%"),
            "classe_percentual": "Faixa",
        },
    )


def exibir_download_individual(base):
    nome = base["nome_candidato"].iloc[0]
    numero = base["numero_candidato"].iloc[0]
    cargo = base["cargo"].iloc[0]
    ano = base["ano"].iloc[0]
    uf = base["uf"].iloc[0]

    csv = (
        base.drop(columns="geometry")
        .to_csv(index=False)
        .encode("utf-8-sig")
    )

    st.download_button(
        "Baixar resultados em CSV",
        data=csv,
        file_name=(
            f"{ano}_{str(uf).lower()}_{slugify(cargo)}_"
            f"{numero}_{slugify(nome)}.csv"
        ),
        mime="text/csv",
    )


# =========================================================
# CABEÇALHO
# =========================================================

st.title("Mapa Eleitoral")
st.caption(
    "Análise geográfica da votação municipal com dados do TSE e malhas do IBGE."
)


# =========================================================
# SIDEBAR: ESCOPO
# =========================================================

with st.sidebar:
    st.header("Configuração")

    modo = st.radio(
        "Modo de análise",
        ["Individual", "Comparar dois candidatos"],
    )

    ano = st.number_input(
        "Ano da eleição",
        min_value=1994,
        max_value=2100,
        value=DEFAULT_ANO,
        step=2,
    )

    uf = st.selectbox(
        "UF",
        UFS,
        index=UFS.index(DEFAULT_UF),
    )

    turno = st.selectbox(
        "Turno",
        [1, 2],
        index=DEFAULT_TURNO - 1,
    )

    cargo = st.selectbox(
        "Cargo",
        CARGOS_DISPONIVEIS,
    )

    st.caption(
        f"Sistema: {sistema_eleitoral(cargo).capitalize()}"
    )


# =========================================================
# MUNICÍPIO PARA CARGOS MUNICIPAIS
# =========================================================

municipio_tse = None
municipio_ibge = None
nome_municipio = None

if cargo in CARGOS_MUNICIPAIS:
    try:
        municipios = carregar_municipios_ui(uf).copy()
        municipios = municipios.sort_values("municipio_ibge")

        nome_municipio = st.sidebar.selectbox(
            "Município da candidatura",
            municipios["municipio_ibge"].tolist(),
        )

        linha_municipio = municipios[
            municipios["municipio_ibge"].eq(nome_municipio)
        ].iloc[0]

        municipio_ibge = str(linha_municipio["codigo_ibge"]).zfill(7)
        municipio_tse = codigo_ibge_para_tse(uf, municipio_ibge)

    except Exception as erro:
        st.error("Não foi possível preparar a seleção de município.")
        st.exception(erro)
        st.stop()


# =========================================================
# CANDIDATOS
# =========================================================

try:
    candidatos = carregar_candidatos_ui(
        ano=ano,
        uf=uf,
        cargo=cargo,
        municipio_tse=municipio_tse,
    ).copy()
except Exception as erro:
    st.error("Não foi possível carregar os candidatos para esse recorte.")
    st.exception(erro)
    st.stop()

if candidatos.empty:
    st.warning(
        "Nenhum candidato foi encontrado para essa combinação de ano, UF, cargo e município."
    )
    st.stop()

candidatos["descricao"] = candidatos.apply(descricao_candidato, axis=1)

candidato_a_desc = st.sidebar.selectbox(
    "Candidato" if modo == "Individual" else "Candidato A",
    candidatos["descricao"].tolist(),
)

candidato_a = candidatos[
    candidatos["descricao"].eq(candidato_a_desc)
].iloc[0]

candidato_b = None

if modo == "Comparar dois candidatos":
    opcoes_b = candidatos[
        ~candidatos["SQ_CANDIDATO"].eq(candidato_a["SQ_CANDIDATO"])
    ].copy()

    if opcoes_b.empty:
        st.warning("Não há um segundo candidato disponível para comparação nesse recorte.")
        st.stop()

    candidato_b_desc = st.sidebar.selectbox(
        "Candidato B",
        opcoes_b["descricao"].tolist(),
    )

    candidato_b = opcoes_b[
        opcoes_b["descricao"].eq(candidato_b_desc)
    ].iloc[0]


gerar = st.sidebar.button(
    "Gerar análise",
    type="primary",
    use_container_width=True,
)


# =========================================================
# PROCESSAMENTO
# =========================================================

if gerar:
    try:
        with st.spinner("Processando dados eleitorais..."):
            base_a = carregar_ou_processar(
                ano=ano,
                uf=uf,
                turno=turno,
                cargo=cargo,
                candidato=candidato_a,
                municipio_tse=municipio_tse,
                municipio_ibge=municipio_ibge,
                nome_municipio=nome_municipio,
            )

            st.session_state["base_a"] = base_a
            st.session_state["modo_ativo"] = modo

            if candidato_b is not None:
                base_b = carregar_ou_processar(
                    ano=ano,
                    uf=uf,
                    turno=turno,
                    cargo=cargo,
                    candidato=candidato_b,
                    municipio_tse=municipio_tse,
                    municipio_ibge=municipio_ibge,
                    nome_municipio=nome_municipio,
                )
                st.session_state["base_b"] = base_b
            else:
                st.session_state.pop("base_b", None)

    except Exception as erro:
        st.error("Ocorreu um erro durante o processamento.")
        st.exception(erro)
        st.stop()


if "base_a" not in st.session_state:
    st.info("Escolha os parâmetros na barra lateral e clique em **Gerar análise**.")
    st.stop()

base_a = st.session_state["base_a"].copy()
modo_ativo = st.session_state.get("modo_ativo", "Individual")


# =========================================================
# ANÁLISE INDIVIDUAL
# =========================================================

if modo_ativo == "Individual":
    nome = base_a["nome_candidato"].iloc[0]
    numero = base_a["numero_candidato"].iloc[0]
    partido = base_a["partido"].iloc[0]
    cargo_base = base_a["cargo"].iloc[0]

    st.subheader(f"{nome} ({numero}) - {partido}")
    st.caption(
        f"{cargo_base.title()} | {base_a['uf'].iloc[0]} | {base_a['ano'].iloc[0]} | "
        f"Sistema {base_a['sistema_eleitoral'].iloc[0]}"
    )

    exibir_metricas(base_a)

    st.divider()
    st.subheader("Distribuição territorial")

    _, labels, _ = obter_faixas(cargo_base)

    classes_selecionadas = st.multiselect(
        "Faixas exibidas no mapa",
        options=labels,
        default=labels,
    )

    base_mapa = preparar_base_visivel(
        base_a,
        cargo_base,
        classes_selecionadas,
    )

    if base_mapa.empty:
        st.warning("Nenhum município corresponde às faixas selecionadas.")
    else:
        mapa = gerar_mapa_eleitoral(base_mapa, salvar=False)
        st_folium(
            mapa,
            width=None,
            height=700,
            returned_objects=[],
            key=f"mapa_individual_{base_a['sq_candidato'].iloc[0]}",
        )

    st.divider()
    st.subheader("Resultados por município")
    exibir_tabela_individual(base_a)

    st.divider()
    st.subheader("Municípios por faixa de votação")

    distribuicao = (
        base_a[base_a["votos_validos"].notna()]
        ["classe_percentual"]
        .astype(str)
        .value_counts()
        .reindex(labels, fill_value=0)
        .rename_axis("Faixa")
        .reset_index(name="Municípios")
    )

    st.bar_chart(
        distribuicao,
        x="Faixa",
        y="Municípios",
    )

    st.divider()
    exibir_download_individual(base_a)


# =========================================================
# COMPARAÇÃO
# =========================================================

else:
    if "base_b" not in st.session_state:
        st.warning("Gere novamente a análise selecionando dois candidatos.")
        st.stop()

    base_b = st.session_state["base_b"].copy()

    nome_a = base_a["nome_candidato"].iloc[0]
    nome_b = base_b["nome_candidato"].iloc[0]

    st.subheader("Comparação de votação municipal")
    st.caption(
        f"{base_a['cargo'].iloc[0].title()} | {base_a['uf'].iloc[0]} | "
        f"{base_a['ano'].iloc[0]} | Sistema {base_a['sistema_eleitoral'].iloc[0]}"
    )

    col_a, col_b = st.columns(2)

    with col_a:
        st.markdown(
            f"### {nome_a} ({base_a['numero_candidato'].iloc[0]}) - {base_a['partido'].iloc[0]}"
        )
        exibir_metricas(base_a)

    with col_b:
        st.markdown(
            f"### {nome_b} ({base_b['numero_candidato'].iloc[0]}) - {base_b['partido'].iloc[0]}"
        )
        exibir_metricas(base_b)

    st.divider()

    _, labels, _ = obter_faixas(base_a["cargo"].iloc[0])

    classes_comparacao = st.multiselect(
        "Faixas exibidas nos mapas",
        options=labels,
        default=labels,
        key="classes_comparacao",
    )

    mapa_col_a, mapa_col_b = st.columns(2)

    base_mapa_a = preparar_base_visivel(
        base_a,
        base_a["cargo"].iloc[0],
        classes_comparacao,
    )
    base_mapa_b = preparar_base_visivel(
        base_b,
        base_b["cargo"].iloc[0],
        classes_comparacao,
    )

    with mapa_col_a:
        st.markdown(f"#### {nome_a}")
        if not base_mapa_a.empty:
            mapa_a = gerar_mapa_eleitoral(base_mapa_a, salvar=False)
            st_folium(
                mapa_a,
                width=None,
                height=620,
                returned_objects=[],
                key=f"mapa_a_{base_a['sq_candidato'].iloc[0]}",
            )

    with mapa_col_b:
        st.markdown(f"#### {nome_b}")
        if not base_mapa_b.empty:
            mapa_b = gerar_mapa_eleitoral(base_mapa_b, salvar=False)
            st_folium(
                mapa_b,
                width=None,
                height=620,
                returned_objects=[],
                key=f"mapa_b_{base_b['sq_candidato'].iloc[0]}",
            )

    st.divider()
    st.subheader("Comparação municipal")

    tabela_a = base_a[
        [
            "codigo_ibge",
            "municipio_ibge",
            "votos_candidato",
            "percentual_validos",
        ]
    ].rename(
        columns={
            "votos_candidato": "votos_a",
            "percentual_validos": "percentual_a",
        }
    )

    tabela_b = base_b[
        [
            "codigo_ibge",
            "votos_candidato",
            "percentual_validos",
        ]
    ].rename(
        columns={
            "votos_candidato": "votos_b",
            "percentual_validos": "percentual_b",
        }
    )

    comparacao = tabela_a.merge(
        tabela_b,
        on="codigo_ibge",
        how="inner",
        validate="one_to_one",
    )

    comparacao = comparacao[
        comparacao["percentual_a"].notna()
        | comparacao["percentual_b"].notna()
    ].copy()

    comparacao["diferenca_pp_a_menos_b"] = (
        comparacao["percentual_a"]
        - comparacao["percentual_b"]
    )

    comparacao = comparacao.sort_values("municipio_ibge")

    st.dataframe(
        comparacao,
        use_container_width=True,
        column_config={
            "codigo_ibge": "Código IBGE",
            "municipio_ibge": "Município",
            "votos_a": f"Votos - {nome_a}",
            "percentual_a": st.column_config.NumberColumn(
                f"% - {nome_a}",
                format="%.2f%%",
            ),
            "votos_b": f"Votos - {nome_b}",
            "percentual_b": st.column_config.NumberColumn(
                f"% - {nome_b}",
                format="%.2f%%",
            ),
            "diferenca_pp_a_menos_b": st.column_config.NumberColumn(
                "Diferença A - B (p.p.)",
                format="%.2f",
            ),
        },
    )

    csv_comparacao = comparacao.to_csv(index=False).encode("utf-8-sig")

    st.download_button(
        "Baixar comparação em CSV",
        data=csv_comparacao,
        file_name=(
            f"comparacao_{base_a['ano'].iloc[0]}_"
            f"{str(base_a['uf'].iloc[0]).lower()}_"
            f"{slugify(base_a['cargo'].iloc[0])}_"
            f"{slugify(nome_a)}_x_{slugify(nome_b)}.csv"
        ),
        mime="text/csv",
    )
