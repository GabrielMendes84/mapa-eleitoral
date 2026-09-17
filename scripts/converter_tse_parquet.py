from __future__ import annotations

import argparse
import re
import shutil
import unicodedata
from collections import defaultdict
from pathlib import Path
from zipfile import ZipFile, is_zipfile

import pandas as pd
from tqdm import tqdm


# =========================================================
# CONFIGURAÇÃO
# =========================================================

ANOS_PADRAO = [
    2014,
    2016,
    2018,
    2020,
    2022,
    2024,
]

UFS = {
    "AC", "AL", "AP", "AM", "BA", "CE", "DF",
    "ES", "GO", "MA", "MT", "MS", "MG", "PA",
    "PB", "PR", "PE", "PI", "RJ", "RN", "RS",
    "RO", "RR", "SC", "SP", "SE", "TO",
}

BASE_DIR = (
    Path(__file__)
    .resolve()
    .parent
    .parent
)

ORIGEM = (
    BASE_DIR
    / "data"
    / "tse_historico"
)

DESTINO = (
    BASE_DIR
    / "data"
    / "parquet"
)

CHUNKSIZE = 250_000


# =========================================================
# UTILITÁRIOS
# =========================================================

def normalizar_texto(valor):

    if pd.isna(valor):
        return ""

    return str(valor).strip()


def normalizar_codigo(valor):

    texto = normalizar_texto(
        valor
    )

    if texto.endswith(".0"):
        texto = texto[:-2]

    if texto.isdigit():
        return str(
            int(texto)
        )

    return texto


def slug(texto):

    texto = unicodedata.normalize(
        "NFKD",
        str(texto),
    )

    texto = "".join(
        c
        for c in texto
        if not unicodedata.combining(c)
    )

    texto = (
        texto
        .upper()
        .strip()
    )

    texto = re.sub(
        r"[^A-Z0-9]+",
        "_",
        texto,
    )

    return texto.strip("_")


def zip_valido(caminho):

    return (
        caminho.exists()
        and caminho.stat().st_size > 0
        and is_zipfile(caminho)
    )


def membro_para_uf(nome):

    base = (
        Path(nome)
        .name
        .upper()
    )

    if base.endswith(
        "_BRASIL.CSV"
    ):
        return "BR"

    match = re.search(
        r"_([A-Z]{2})\.CSV$",
        base,
    )

    if (
        match
        and match.group(1) in UFS
    ):
        return match.group(1)

    return None


def listar_csvs_por_uf(
    caminho_zip,
    incluir_br=False,
):

    encontrados = {}

    with ZipFile(
        caminho_zip
    ) as zf:

        for nome in zf.namelist():

            if not (
                nome
                .lower()
                .endswith(".csv")
            ):
                continue

            uf = membro_para_uf(
                nome
            )

            if uf in UFS:

                encontrados[
                    uf
                ] = nome

            elif (
                incluir_br
                and uf == "BR"
            ):

                encontrados[
                    "BR"
                ] = nome

    return encontrados


def colunas_csv(
    zf,
    membro,
):

    with zf.open(
        membro
    ) as arquivo:

        df = pd.read_csv(
            arquivo,
            sep=";",
            encoding="latin-1",
            dtype="string",
            nrows=0,
        )

    return list(
        df.columns
    )


def escolher_coluna(
    colunas,
    opcoes,
    obrigatoria=True,
):

    mapa = {
        coluna.upper():
        coluna

        for coluna
        in colunas
    }

    for opcao in opcoes:

        if (
            opcao.upper()
            in mapa
        ):

            return mapa[
                opcao.upper()
            ]

    if obrigatoria:

        raise ValueError(
            "Nenhuma das colunas "
            "esperadas foi encontrada: "
            + ", ".join(opcoes)
            + "\nColunas disponíveis: "
            + ", ".join(colunas)
        )

    return None


# =========================================================
# CONTROLE DE PARTIÇÕES
# =========================================================

def marcador(
    dataset,
    ano,
    uf,
):

    return (
        DESTINO
        / dataset
        / f"ano={ano}"
        / f"uf={uf}"
        / "_SUCCESS"
    )


def ja_processado(
    dataset,
    ano,
    uf,
):

    return marcador(
        dataset,
        ano,
        uf,
    ).exists()


def limpar_particao(
    dataset,
    ano,
    uf,
):

    pasta = (
        DESTINO
        / dataset
        / f"ano={ano}"
        / f"uf={uf}"
    )

    if pasta.exists():

        shutil.rmtree(
            pasta
        )

    pasta.mkdir(
        parents=True,
        exist_ok=True,
    )

    return pasta


def concluir_particao(
    dataset,
    ano,
    uf,
):

    arquivo = marcador(
        dataset,
        ano,
        uf,
    )

    arquivo.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    arquivo.write_text(
        "ok\n",
        encoding="utf-8",
    )


def escrever_parquet(
    dataframe,
    caminho,
):

    caminho.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    dataframe.to_parquet(
        caminho,
        index=False,
        engine="pyarrow",
        compression="snappy",
    )


# =========================================================
# CANDIDATOS
# =========================================================

def processar_candidatos_uf(
    ano,
    caminho_zip,
    membro,
    uf,
    force=False,
):

    dataset = "candidatos"

    if (
        not force
        and ja_processado(
            dataset,
            ano,
            uf,
        )
    ):

        print(
            f"  [skip] candidatos "
            f"{ano}/{uf} já processados"
        )

        return []

    pasta = limpar_particao(
        dataset,
        ano,
        uf,
    )

    with ZipFile(
        caminho_zip
    ) as zf:

        colunas = colunas_csv(
            zf,
            membro,
        )

        mapa = {
            "uf":
                escolher_coluna(
                    colunas,
                    ["SG_UF"],
                    obrigatoria=False,
                ),

            "sg_ue":
                escolher_coluna(
                    colunas,
                    ["SG_UE"],
                    obrigatoria=False,
                ),

            "nm_ue":
                escolher_coluna(
                    colunas,
                    ["NM_UE"],
                    obrigatoria=False,
                ),

            "cargo":
                escolher_coluna(
                    colunas,
                    ["DS_CARGO"],
                ),

            "sq":
                escolher_coluna(
                    colunas,
                    ["SQ_CANDIDATO"],
                ),

            "numero":
                escolher_coluna(
                    colunas,
                    ["NR_CANDIDATO"],
                ),

            "nome":
                escolher_coluna(
                    colunas,
                    ["NM_CANDIDATO"],
                    obrigatoria=False,
                ),

            "urna":
                escolher_coluna(
                    colunas,
                    ["NM_URNA_CANDIDATO"],
                ),

            "partido":
                escolher_coluna(
                    colunas,
                    ["SG_PARTIDO"],
                    obrigatoria=False,
                ),
        }

        usecols = list(
            dict.fromkeys(
                coluna
                for coluna
                in mapa.values()
                if coluna
            )
        )

        with zf.open(
            membro
        ) as arquivo:

            df = pd.read_csv(
                arquivo,
                sep=";",
                encoding="latin-1",
                dtype="string",
                usecols=usecols,
                low_memory=False,
            )

    saida = pd.DataFrame(
        {
            "ano":
                ano,

            "uf":
                (
                    df[
                        mapa["uf"]
                    ]
                    .map(
                        normalizar_texto
                    )
                    .str.upper()
                )
                if mapa["uf"]
                else uf,

            "sg_ue":
                (
                    df[
                        mapa["sg_ue"]
                    ]
                    .map(
                        normalizar_codigo
                    )
                )
                if mapa["sg_ue"]
                else "",

            "nm_ue":
                (
                    df[
                        mapa["nm_ue"]
                    ]
                    .map(
                        normalizar_texto
                    )
                    .str.upper()
                )
                if mapa["nm_ue"]
                else "",

            "cargo":
                (
                    df[
                        mapa["cargo"]
                    ]
                    .map(
                        normalizar_texto
                    )
                    .str.upper()
                ),

            "sq_candidato":
                (
                    df[
                        mapa["sq"]
                    ]
                    .map(
                        normalizar_codigo
                    )
                ),

            "numero_candidato":
                (
                    df[
                        mapa["numero"]
                    ]
                    .map(
                        normalizar_codigo
                    )
                ),

            "nome_candidato":
                (
                    df[
                        mapa["nome"]
                    ]
                    .map(
                        normalizar_texto
                    )
                    .str.upper()
                )
                if mapa["nome"]
                else "",

            "nome_urna_candidato":
                (
                    df[
                        mapa["urna"]
                    ]
                    .map(
                        normalizar_texto
                    )
                    .str.upper()
                ),

            "partido":
                (
                    df[
                        mapa["partido"]
                    ]
                    .map(
                        normalizar_texto
                    )
                    .str.upper()
                )
                if mapa["partido"]
                else "",
        }
    )

    saida = (
        saida
        .drop_duplicates(
            subset=[
                "sq_candidato"
            ]
        )
        .reset_index(
            drop=True
        )
    )

    escrever_parquet(
        saida,
        pasta
        / "dados.parquet",
    )

    concluir_particao(
        dataset,
        ano,
        uf,
    )

    return [
        {
            "dataset":
                dataset,

            "ano":
                ano,

            "uf":
                uf,

            "cargo":
                "*",

            "linhas":
                len(saida),

            "total":
                None,
        }
    ]


# =========================================================
# VOTAÇÃO POR CANDIDATO
# =========================================================

def processar_votacao_uf(
    ano,
    caminho_zip,
    membro,
    uf,
    force=False,
):

    dataset = (
        "votacao_candidato_municipio"
    )

    if (
        not force
        and ja_processado(
            dataset,
            ano,
            uf,
        )
    ):

        print(
            f"  [skip] votação "
            f"{ano}/{uf} já processada"
        )

        return []

    pasta = limpar_particao(
        dataset,
        ano,
        uf,
    )

    parciais = []

    totais_entrada = defaultdict(
        int
    )

    with ZipFile(
        caminho_zip
    ) as zf:

        colunas = colunas_csv(
            zf,
            membro,
        )

        mapa = {
            "turno":
                escolher_coluna(
                    colunas,
                    ["NR_TURNO"],
                ),

            "uf":
                escolher_coluna(
                    colunas,
                    ["SG_UF"],
                    obrigatoria=False,
                ),

            "cargo":
                escolher_coluna(
                    colunas,
                    ["DS_CARGO"],
                ),

            "sq":
                escolher_coluna(
                    colunas,
                    ["SQ_CANDIDATO"],
                ),

            "numero":
                escolher_coluna(
                    colunas,
                    ["NR_CANDIDATO"],
                    obrigatoria=False,
                ),

            "urna":
                escolher_coluna(
                    colunas,
                    ["NM_URNA_CANDIDATO"],
                    obrigatoria=False,
                ),

            "partido":
                escolher_coluna(
                    colunas,
                    ["SG_PARTIDO"],
                    obrigatoria=False,
                ),

            "codigo_tse":
                escolher_coluna(
                    colunas,
                    ["CD_MUNICIPIO"],
                ),

            "municipio":
                escolher_coluna(
                    colunas,
                    ["NM_MUNICIPIO"],
                ),

            "votos":
                escolher_coluna(
                    colunas,
                    [
                        "QT_VOTOS_NOMINAIS_VALIDOS",
                        "QT_VOTOS_NOMINAIS",
                    ],
                ),
        }

        usecols = list(
            dict.fromkeys(
                coluna
                for coluna
                in mapa.values()
                if coluna
            )
        )

        with zf.open(
            membro
        ) as arquivo:

            leitor = pd.read_csv(
                arquivo,
                sep=";",
                encoding="latin-1",
                dtype="string",
                usecols=usecols,
                chunksize=CHUNKSIZE,
                low_memory=False,
            )

            for chunk in tqdm(
                leitor,
                desc=(
                    f"    votação "
                    f"{ano}/{uf}"
                ),
                unit="chunk",
            ):

                tmp = pd.DataFrame(
                    {
                        "ano":
                            ano,

                        "turno":
                            pd.to_numeric(
                                chunk[
                                    mapa["turno"]
                                ],
                                errors="coerce",
                            )
                            .fillna(0)
                            .astype("int16"),

                        "uf":
                            (
                                chunk[
                                    mapa["uf"]
                                ]
                                .map(
                                    normalizar_texto
                                )
                                .str.upper()
                            )
                            if mapa["uf"]
                            else uf,

                        "cargo":
                            (
                                chunk[
                                    mapa["cargo"]
                                ]
                                .map(
                                    normalizar_texto
                                )
                                .str.upper()
                            ),

                        "sq_candidato":
                            (
                                chunk[
                                    mapa["sq"]
                                ]
                                .map(
                                    normalizar_codigo
                                )
                            ),

                        "numero_candidato":
                            (
                                chunk[
                                    mapa["numero"]
                                ]
                                .map(
                                    normalizar_codigo
                                )
                            )
                            if mapa["numero"]
                            else "",

                        "nome_urna_candidato":
                            (
                                chunk[
                                    mapa["urna"]
                                ]
                                .map(
                                    normalizar_texto
                                )
                                .str.upper()
                            )
                            if mapa["urna"]
                            else "",

                        "partido":
                            (
                                chunk[
                                    mapa["partido"]
                                ]
                                .map(
                                    normalizar_texto
                                )
                                .str.upper()
                            )
                            if mapa["partido"]
                            else "",

                        "codigo_tse":
                            (
                                chunk[
                                    mapa["codigo_tse"]
                                ]
                                .map(
                                    normalizar_codigo
                                )
                            ),

                        "municipio":
                            (
                                chunk[
                                    mapa["municipio"]
                                ]
                                .map(
                                    normalizar_texto
                                )
                                .str.upper()
                            ),

                        "votos_candidato":
                            pd.to_numeric(
                                chunk[
                                    mapa["votos"]
                                ],
                                errors="coerce",
                            )
                            .fillna(0)
                            .astype("int64"),
                    }
                )

                totais = (
                    tmp
                    .groupby(
                        [
                            "turno",
                            "cargo",
                        ],
                        dropna=False,
                    )[
                        "votos_candidato"
                    ]
                    .sum()
                )

                for chave, valor in (
                    totais.items()
                ):

                    totais_entrada[
                        chave
                    ] += int(valor)

                chaves = [
                    "ano",
                    "turno",
                    "uf",
                    "cargo",
                    "sq_candidato",
                    "numero_candidato",
                    "nome_urna_candidato",
                    "partido",
                    "codigo_tse",
                    "municipio",
                ]

                parcial = (
                    tmp
                    .groupby(
                        chaves,
                        as_index=False,
                        dropna=False,
                    )[
                        "votos_candidato"
                    ]
                    .sum()
                )

                parciais.append(
                    parcial
                )

    if not parciais:

        raise ValueError(
            "Nenhum dado de votação "
            f"encontrado em {ano}/{uf}"
        )

    consolidado = pd.concat(
        parciais,
        ignore_index=True,
    )

    chaves = [
        "ano",
        "turno",
        "uf",
        "cargo",
        "sq_candidato",
        "numero_candidato",
        "nome_urna_candidato",
        "partido",
        "codigo_tse",
        "municipio",
    ]

    consolidado = (
        consolidado
        .groupby(
            chaves,
            as_index=False,
            dropna=False,
        )[
            "votos_candidato"
        ]
        .sum()
    )

    manifesto = []

    for cargo, df_cargo in (
        consolidado
        .groupby(
            "cargo",
            sort=True,
        )
    ):

        cargo_slug = slug(
            cargo
        )

        pasta_cargo = (
            pasta
            / f"cargo={cargo_slug}"
        )

        df_cargo = (
            df_cargo
            .reset_index(
                drop=True
            )
        )

        escrever_parquet(
            df_cargo,
            pasta_cargo
            / "dados.parquet",
        )

        totais_saida = (
            df_cargo
            .groupby(
                [
                    "turno",
                    "cargo",
                ]
            )[
                "votos_candidato"
            ]
            .sum()
        )

        for chave, valor_saida in (
            totais_saida.items()
        ):

            valor_entrada = (
                totais_entrada[
                    chave
                ]
            )

            if (
                int(valor_saida)
                != int(valor_entrada)
            ):

                raise ValueError(
                    "Falha de validação "
                    "em votação "
                    f"{ano}/{uf}/{cargo}: "
                    f"entrada={valor_entrada}, "
                    f"saída={int(valor_saida)}"
                )

        manifesto.append(
            {
                "dataset":
                    dataset,

                "ano":
                    ano,

                "uf":
                    uf,

                "cargo":
                    cargo,

                "linhas":
                    len(df_cargo),

                "total":
                    int(
                        df_cargo[
                            "votos_candidato"
                        ].sum()
                    ),
            }
        )

    concluir_particao(
        dataset,
        ano,
        uf,
    )

    return manifesto


# =========================================================
# APURAÇÃO / VOTOS VÁLIDOS
# =========================================================

def processar_apuracao_uf(
    ano,
    caminho_zip,
    membro,
    uf,
    force=False,
):

    dataset = (
        "apuracao_municipio"
    )

    if (
        not force
        and ja_processado(
            dataset,
            ano,
            uf,
        )
    ):

        print(
            f"  [skip] apuração "
            f"{ano}/{uf} já processada"
        )

        return []

    pasta = limpar_particao(
        dataset,
        ano,
        uf,
    )

    parciais = []

    totais_entrada = defaultdict(
        int
    )

    with ZipFile(
        caminho_zip
    ) as zf:

        colunas = colunas_csv(
            zf,
            membro,
        )

        mapa = {
            "turno":
                escolher_coluna(
                    colunas,
                    ["NR_TURNO"],
                ),

            "uf":
                escolher_coluna(
                    colunas,
                    ["SG_UF"],
                    obrigatoria=False,
                ),

            "cargo":
                escolher_coluna(
                    colunas,
                    ["DS_CARGO"],
                ),

            "codigo_tse":
                escolher_coluna(
                    colunas,
                    ["CD_MUNICIPIO"],
                ),

            "municipio":
                escolher_coluna(
                    colunas,
                    ["NM_MUNICIPIO"],
                ),

            "validos":
                escolher_coluna(
                    colunas,
                    [
                        "QT_TOTAL_VOTOS_VALIDOS",
                        "QT_VOTOS_VALIDOS",
                    ],
                ),
        }

        usecols = list(
            dict.fromkeys(
                coluna
                for coluna
                in mapa.values()
                if coluna
            )
        )

        with zf.open(
            membro
        ) as arquivo:

            leitor = pd.read_csv(
                arquivo,
                sep=";",
                encoding="latin-1",
                dtype="string",
                usecols=usecols,
                chunksize=CHUNKSIZE,
                low_memory=False,
            )

            for chunk in tqdm(
                leitor,
                desc=(
                    f"    apuração "
                    f"{ano}/{uf}"
                ),
                unit="chunk",
            ):

                tmp = pd.DataFrame(
                    {
                        "ano":
                            ano,

                        "turno":
                            pd.to_numeric(
                                chunk[
                                    mapa["turno"]
                                ],
                                errors="coerce",
                            )
                            .fillna(0)
                            .astype("int16"),

                        "uf":
                            (
                                chunk[
                                    mapa["uf"]
                                ]
                                .map(
                                    normalizar_texto
                                )
                                .str.upper()
                            )
                            if mapa["uf"]
                            else uf,

                        "cargo":
                            (
                                chunk[
                                    mapa["cargo"]
                                ]
                                .map(
                                    normalizar_texto
                                )
                                .str.upper()
                            ),

                        "codigo_tse":
                            (
                                chunk[
                                    mapa["codigo_tse"]
                                ]
                                .map(
                                    normalizar_codigo
                                )
                            ),

                        "municipio":
                            (
                                chunk[
                                    mapa["municipio"]
                                ]
                                .map(
                                    normalizar_texto
                                )
                                .str.upper()
                            ),

                        "votos_validos":
                            pd.to_numeric(
                                chunk[
                                    mapa["validos"]
                                ],
                                errors="coerce",
                            )
                            .fillna(0)
                            .astype("int64"),
                    }
                )

                totais = (
                    tmp
                    .groupby(
                        [
                            "turno",
                            "cargo",
                        ],
                        dropna=False,
                    )[
                        "votos_validos"
                    ]
                    .sum()
                )

                for chave, valor in (
                    totais.items()
                ):

                    totais_entrada[
                        chave
                    ] += int(valor)

                chaves = [
                    "ano",
                    "turno",
                    "uf",
                    "cargo",
                    "codigo_tse",
                    "municipio",
                ]

                parcial = (
                    tmp
                    .groupby(
                        chaves,
                        as_index=False,
                        dropna=False,
                    )[
                        "votos_validos"
                    ]
                    .sum()
                )

                parciais.append(
                    parcial
                )

    if not parciais:

        raise ValueError(
            "Nenhum dado de apuração "
            f"encontrado em {ano}/{uf}"
        )

    consolidado = pd.concat(
        parciais,
        ignore_index=True,
    )

    chaves = [
        "ano",
        "turno",
        "uf",
        "cargo",
        "codigo_tse",
        "municipio",
    ]

    consolidado = (
        consolidado
        .groupby(
            chaves,
            as_index=False,
            dropna=False,
        )[
            "votos_validos"
        ]
        .sum()
    )

    manifesto = []

    for cargo, df_cargo in (
        consolidado
        .groupby(
            "cargo",
            sort=True,
        )
    ):

        cargo_slug = slug(
            cargo
        )

        pasta_cargo = (
            pasta
            / f"cargo={cargo_slug}"
        )

        df_cargo = (
            df_cargo
            .reset_index(
                drop=True
            )
        )

        escrever_parquet(
            df_cargo,
            pasta_cargo
            / "dados.parquet",
        )

        totais_saida = (
            df_cargo
            .groupby(
                [
                    "turno",
                    "cargo",
                ]
            )[
                "votos_validos"
            ]
            .sum()
        )

        for chave, valor_saida in (
            totais_saida.items()
        ):

            valor_entrada = (
                totais_entrada[
                    chave
                ]
            )

            if (
                int(valor_saida)
                != int(valor_entrada)
            ):

                raise ValueError(
                    "Falha de validação "
                    "em apuração "
                    f"{ano}/{uf}/{cargo}: "
                    f"entrada={valor_entrada}, "
                    f"saída={int(valor_saida)}"
                )

        manifesto.append(
            {
                "dataset":
                    dataset,

                "ano":
                    ano,

                "uf":
                    uf,

                "cargo":
                    cargo,

                "linhas":
                    len(df_cargo),

                "total":
                    int(
                        df_cargo[
                            "votos_validos"
                        ].sum()
                    ),
            }
        )

    concluir_particao(
        dataset,
        ano,
        uf,
    )

    return manifesto


# =========================================================
# PROCESSAR UM ANO
# =========================================================

def processar_ano(
    ano,
    ufs_selecionadas=None,
    force=False,
):

    pasta_ano = (
        ORIGEM
        / str(ano)
    )

    arquivos = {
        "candidatos":
            pasta_ano
            / f"consulta_cand_{ano}.zip",

        "votacao":
            pasta_ano
            / (
                "votacao_candidato_"
                f"munzona_{ano}.zip"
            ),

        "apuracao":
            pasta_ano
            / (
                "detalhe_votacao_"
                f"munzona_{ano}.zip"
            ),
    }

    faltantes = [
        str(caminho)

        for caminho
        in arquivos.values()

        if not zip_valido(
            caminho
        )
    ]

    if faltantes:

        print(
            f"\n[aviso] {ano}: "
            "ainda faltam ZIPs válidos:"
        )

        for item in faltantes:

            print(
                "   ",
                item,
            )

        print(
            "   Ano ignorado "
            "nesta execução."
        )

        return []

    print(
        "\n"
        + "=" * 72
    )

    print(
        f"PROCESSANDO {ano}"
    )

    print(
        "=" * 72
    )

    membros_candidatos = (
        listar_csvs_por_uf(
            arquivos[
                "candidatos"
            ],
            incluir_br=True,
        )
    )

    membros_votacao = (
        listar_csvs_por_uf(
            arquivos[
                "votacao"
            ]
        )
    )

    membros_apuracao = (
        listar_csvs_por_uf(
            arquivos[
                "apuracao"
            ]
        )
    )

    ufs_disponiveis = sorted(
        set(
            membros_votacao
        )
        &
        set(
            membros_apuracao
        )
    )

    if ufs_selecionadas:

        ufs_disponiveis = [
            uf
            for uf
            in ufs_disponiveis
            if uf
            in ufs_selecionadas
        ]

    manifesto = []

    # Arquivo nacional útil para
    # candidatos à Presidência.

    if (
        "BR"
        in membros_candidatos
        and not ufs_selecionadas
    ):

        print(
            f"\n[CANDIDATOS] "
            f"{ano}/BR"
        )

        manifesto += (
            processar_candidatos_uf(
                ano,
                arquivos[
                    "candidatos"
                ],
                membros_candidatos[
                    "BR"
                ],
                "BR",
                force,
            )
        )

    for uf in ufs_disponiveis:

        print(
            f"\n--- "
            f"{ano}/{uf} ---"
        )

        # -------------------------------------
        # Candidatos
        # -------------------------------------

        if (
            uf
            in membros_candidatos
        ):

            print(
                "[1/3] Candidatos"
            )

            manifesto += (
                processar_candidatos_uf(
                    ano,
                    arquivos[
                        "candidatos"
                    ],
                    membros_candidatos[
                        uf
                    ],
                    uf,
                    force,
                )
            )

        else:

            print(
                "  [aviso] "
                "CSV de candidatos "
                "da UF não encontrado."
            )

        # -------------------------------------
        # Votação
        # -------------------------------------

        print(
            "[2/3] Votação "
            "por candidato → município"
        )

        manifesto += (
            processar_votacao_uf(
                ano,
                arquivos[
                    "votacao"
                ],
                membros_votacao[
                    uf
                ],
                uf,
                force,
            )
        )

        # -------------------------------------
        # Apuração
        # -------------------------------------

        print(
            "[3/3] Apuração "
            "→ município"
        )

        manifesto += (
            processar_apuracao_uf(
                ano,
                arquivos[
                    "apuracao"
                ],
                membros_apuracao[
                    uf
                ],
                uf,
                force,
            )
        )

    return manifesto


# =========================================================
# MANIFESTO
# =========================================================

def salvar_manifesto(
    registros
):

    if not registros:
        return

    caminho = (
        DESTINO
        / "_manifesto_ultima_execucao.csv"
    )

    df = pd.DataFrame(
        registros
    )

    df.to_csv(
        caminho,
        index=False,
        encoding="utf-8-sig",
    )

    print(
        "\nManifesto salvo em:"
    )

    print(
        caminho
    )


# =========================================================
# ARGUMENTOS
# =========================================================

def parse_anos(
    texto
):

    if not texto:

        return ANOS_PADRAO

    return [
        int(item.strip())

        for item
        in texto.split(",")

        if item.strip()
    ]


def parse_ufs(
    texto
):

    if not texto:
        return None

    resultado = {
        item
        .strip()
        .upper()

        for item
        in texto.split(",")

        if item.strip()
    }

    invalidas = (
        resultado
        - UFS
    )

    if invalidas:

        raise ValueError(
            "UFs inválidas: "
            f"{sorted(invalidas)}"
        )

    return resultado


# =========================================================
# MAIN
# =========================================================

def main():

    parser = argparse.ArgumentParser(
        description=(
            "Converte o histórico "
            "eleitoral do TSE para "
            "uma Silver local "
            "em Parquet."
        )
    )

    parser.add_argument(
        "--anos",
        help=(
            "Ex.: 2022 ou "
            "2018,2022,2024. "
            "Padrão: 2014 a 2024."
        ),
    )

    parser.add_argument(
        "--ufs",
        help=(
            "Ex.: MG ou MG,SP. "
            "Padrão: todas."
        ),
    )

    parser.add_argument(
        "--force",
        action="store_true",
        help=(
            "Reprocessa partições "
            "já concluídas."
        ),
    )

    args = (
        parser.parse_args()
    )

    anos = parse_anos(
        args.anos
    )

    ufs = parse_ufs(
        args.ufs
    )

    DESTINO.mkdir(
        parents=True,
        exist_ok=True,
    )

    print(
        "=" * 72
    )

    print(
        "TSE → SILVER LOCAL "
        "EM PARQUET"
    )

    print(
        "=" * 72
    )

    print(
        "Origem :",
        ORIGEM,
    )

    print(
        "Destino:",
        DESTINO,
    )

    print(
        "Anos   :",
        anos,
    )

    print(
        "UFs    :",
        sorted(ufs)
        if ufs
        else "todas",
    )

    print()

    print(
        "Os ZIPs originais "
        "NÃO serão apagados."
    )

    manifesto = []

    for ano in anos:

        try:

            manifesto += (
                processar_ano(
                    ano,
                    ufs_selecionadas=ufs,
                    force=args.force,
                )
            )

        except Exception as erro:

            print(
                f"\n[ERRO] "
                f"{ano}: {erro}"
            )

            print(
                "Você pode executar "
                "novamente. Partições "
                "concluídas serão "
                "ignoradas."
            )

    salvar_manifesto(
        manifesto
    )

    print(
        "\n"
        + "=" * 72
    )

    print(
        "CONVERSÃO ENCERRADA"
    )

    print(
        "=" * 72
    )

    print(
        "Partições concluídas "
        "recebem um arquivo "
        "_SUCCESS."
    )

    print(
        "Ao rodar novamente, "
        "elas são ignoradas."
    )


if __name__ == "__main__":
    main()