from pathlib import Path
from zipfile import ZipFile, is_zipfile
import re
import subprocess
import unicodedata

import pandas as pd
import requests
from tqdm import tqdm

from src.config import (
    CARGOS_MUNICIPAIS,
    RAW_DIR,
    TSE_CROSSWALK_URL,
    tse_candidatos_url,
    tse_detalhe_votacao_url,
    tse_votacao_candidato_url,
)


# =========================================================
# PASTAS
# =========================================================

BASE_DIR = Path(__file__).resolve().parent.parent

TSE_HISTORICO_DIR = BASE_DIR / "data" / "tse_historico"
TSE_APOIO_DIR = TSE_HISTORICO_DIR / "apoio"

PARQUET_DIR = BASE_DIR / "data" / "parquet"

PARQUET_CANDIDATOS_DIR = (
    PARQUET_DIR / "candidatos"
)

PARQUET_VOTACAO_DIR = (
    PARQUET_DIR
    / "votacao_candidato_municipio"
)

PARQUET_APURACAO_DIR = (
    PARQUET_DIR
    / "apuracao_municipio"
)


# =========================================================
# HTTP
# =========================================================

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/152.0.0.0 Safari/537.36"
    ),
    "Accept": "*/*",
    "Accept-Language": "pt-BR,pt;q=0.9,en;q=0.8",
    "Referer": "https://dadosabertos.tse.jus.br/",
}

SESSION = requests.Session()
SESSION.headers.update(HEADERS)


# =========================================================
# UTILITÁRIOS
# =========================================================

def normalizar_codigo(valor):
    if pd.isna(valor):
        return None

    texto = str(valor).strip()

    if texto.endswith(".0"):
        texto = texto[:-2]

    if texto.isdigit():
        return str(int(texto))

    return texto


def slug(texto):
    """
    Mesma convenção usada pelo
    converter_tse_parquet.py.

    DEPUTADO FEDERAL
    ->
    DEPUTADO_FEDERAL
    """

    texto = unicodedata.normalize(
        "NFKD",
        str(texto),
    )

    texto = "".join(
        c
        for c in texto
        if not unicodedata.combining(c)
    )

    texto = texto.upper().strip()

    texto = re.sub(
        r"[^A-Z0-9]+",
        "_",
        texto,
    )

    return texto.strip("_")


def arquivo_zip_valido(caminho):
    caminho = Path(caminho)

    return (
        caminho.exists()
        and caminho.stat().st_size > 0
        and is_zipfile(caminho)
    )


def arquivo_parquet_valido(caminho):
    caminho = Path(caminho)

    return (
        caminho.exists()
        and caminho.is_file()
        and caminho.stat().st_size > 0
    )


def particao_parquet_concluida(pasta):
    pasta = Path(pasta)

    return (
        pasta.exists()
        and (pasta / "_SUCCESS").exists()
    )


# =========================================================
# LOCALIZAÇÃO DOS PARQUETS
# =========================================================

def caminho_parquet_candidatos(
    ano,
    uf,
    cargo=None,
):
    uf = str(uf).upper().strip()

    cargo = (
        str(cargo).upper().strip()
        if cargo
        else None
    )

    escopo = (
        "BR"
        if cargo == "PRESIDENTE"
        else uf
    )

    pasta = (
        PARQUET_CANDIDATOS_DIR
        / f"ano={int(ano)}"
        / f"uf={escopo}"
    )

    arquivo = (
        pasta
        / "dados.parquet"
    )

    if (
        particao_parquet_concluida(pasta)
        and arquivo_parquet_valido(arquivo)
    ):
        return arquivo

    return None


def caminho_parquet_votacao(
    ano,
    uf,
    cargo,
):
    uf = str(uf).upper().strip()

    pasta_uf = (
        PARQUET_VOTACAO_DIR
        / f"ano={int(ano)}"
        / f"uf={uf}"
    )

    arquivo = (
        pasta_uf
        / f"cargo={slug(cargo)}"
        / "dados.parquet"
    )

    if (
        particao_parquet_concluida(pasta_uf)
        and arquivo_parquet_valido(arquivo)
    ):
        return arquivo

    return None


def caminho_parquet_apuracao(
    ano,
    uf,
    cargo,
):
    uf = str(uf).upper().strip()

    pasta_uf = (
        PARQUET_APURACAO_DIR
        / f"ano={int(ano)}"
        / f"uf={uf}"
    )

    arquivo = (
        pasta_uf
        / f"cargo={slug(cargo)}"
        / "dados.parquet"
    )

    if (
        particao_parquet_concluida(pasta_uf)
        and arquivo_parquet_valido(arquivo)
    ):
        return arquivo

    return None


# =========================================================
# LOCALIZAÇÃO DOS ZIPs
# =========================================================

def localizar_arquivo_tse(
    ano,
    nome_arquivo,
):
    candidatos = [
        (
            TSE_HISTORICO_DIR
            / str(int(ano))
            / nome_arquivo
        ),
        (
            RAW_DIR
            / nome_arquivo
        ),
    ]

    for caminho in candidatos:

        if arquivo_zip_valido(caminho):

            print(
                "[ok] Arquivo encontrado: "
                f"{caminho}"
            )

            return caminho

        if caminho.exists():

            print(
                "[aviso] Arquivo existente, "
                "mas inválido/corrompido: "
                f"{caminho}"
            )

    return None


def localizar_crosswalk():

    nome = "municipio_tse_ibge.zip"

    candidatos = [
        TSE_APOIO_DIR / nome,
        RAW_DIR / nome,
    ]

    for caminho in candidatos:

        if arquivo_zip_valido(caminho):

            print(
                "[ok] Crosswalk encontrado: "
                f"{caminho}"
            )

            return caminho

    return None


# =========================================================
# DOWNLOAD
# =========================================================

def baixar_arquivo(
    url,
    destino,
):

    destino = Path(destino)

    if arquivo_zip_valido(destino):

        print(
            f"[ok] Já existe: {destino}"
        )

        return destino

    if destino.exists():
        destino.unlink()

    destino.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    temporario = destino.with_suffix(
        destino.suffix
        + ".part"
    )

    if temporario.exists():
        temporario.unlink()

    print(
        f"Baixando {destino.name}..."
    )

    try:

        with SESSION.get(
            url,
            stream=True,
            timeout=(30, 900),
            allow_redirects=True,
        ) as response:

            if response.status_code == 403:
                raise PermissionError(
                    "HTTP 403"
                )

            response.raise_for_status()

            total = int(
                response.headers.get(
                    "content-length",
                    0,
                )
            )

            with open(
                temporario,
                "wb",
            ) as arquivo:

                with tqdm(
                    total=total,
                    unit="B",
                    unit_scale=True,
                    unit_divisor=1024,
                    desc=destino.name,
                ) as barra:

                    for bloco in (
                        response.iter_content(
                            chunk_size=1024 * 1024
                        )
                    ):

                        if bloco:

                            arquivo.write(
                                bloco
                            )

                            barra.update(
                                len(bloco)
                            )

    except PermissionError:

        print(
            "CDN bloqueou requests. "
            "Tentando curl.exe..."
        )

        if temporario.exists():
            temporario.unlink()

        comando = [
            "curl.exe",
            "-L",
            "--fail",
            "--retry",
            "4",
            "--retry-delay",
            "3",
            "-A",
            HEADERS["User-Agent"],
            "-e",
            HEADERS["Referer"],
            "-o",
            str(temporario),
            url,
        ]

        resultado = subprocess.run(
            comando,
            capture_output=True,
            text=True,
        )

        if resultado.returncode != 0:

            if temporario.exists():
                temporario.unlink()

            raise RuntimeError(
                "Não foi possível baixar "
                "o arquivo do TSE.\n"
                f"{resultado.stderr}"
            )

    except Exception:

        if temporario.exists():
            temporario.unlink()

        raise

    if not arquivo_zip_valido(
        temporario
    ):

        if temporario.exists():
            temporario.unlink()

        raise ValueError(
            "Arquivo recebido não é "
            "um ZIP válido."
        )

    temporario.replace(
        destino
    )

    print(
        "[ok] Download concluído: "
        f"{destino}"
    )

    return destino


# =========================================================
# OBTENÇÃO DOS ZIPs
# =========================================================

def obter_arquivo_candidatos(
    ano,
):

    nome = (
        f"consulta_cand_{ano}.zip"
    )

    existente = localizar_arquivo_tse(
        ano,
        nome,
    )

    if existente:
        return existente

    destino = (
        TSE_HISTORICO_DIR
        / str(ano)
        / nome
    )

    return baixar_arquivo(
        tse_candidatos_url(ano),
        destino,
    )


def obter_arquivo_votos(
    ano,
):

    nome = (
        "votacao_candidato_"
        f"munzona_{ano}.zip"
    )

    existente = localizar_arquivo_tse(
        ano,
        nome,
    )

    if existente:
        return existente

    destino = (
        TSE_HISTORICO_DIR
        / str(ano)
        / nome
    )

    return baixar_arquivo(
        tse_votacao_candidato_url(ano),
        destino,
    )


def obter_arquivo_detalhe(
    ano,
):

    nome = (
        "detalhe_votacao_"
        f"munzona_{ano}.zip"
    )

    existente = localizar_arquivo_tse(
        ano,
        nome,
    )

    if existente:
        return existente

    destino = (
        TSE_HISTORICO_DIR
        / str(ano)
        / nome
    )

    return baixar_arquivo(
        tse_detalhe_votacao_url(ano),
        destino,
    )


def obter_arquivo_crosswalk():

    existente = localizar_crosswalk()

    if existente:
        return existente

    destino = (
        TSE_APOIO_DIR
        / "municipio_tse_ibge.zip"
    )

    return baixar_arquivo(
        TSE_CROSSWALK_URL,
        destino,
    )


# =========================================================
# LEITURA DE ZIP
# =========================================================

def encontrar_csv_no_zip(
    caminho_zip,
    escopo=None,
):

    caminho_zip = Path(
        caminho_zip
    )

    if not arquivo_zip_valido(
        caminho_zip
    ):

        raise ValueError(
            f"ZIP inválido: {caminho_zip}"
        )

    with ZipFile(
        caminho_zip
    ) as zip_file:

        arquivos = [
            nome
            for nome
            in zip_file.namelist()
            if nome
            .lower()
            .endswith(".csv")
        ]

    if not arquivos:

        raise ValueError(
            "Nenhum CSV encontrado."
        )

    if escopo:

        escopo = (
            str(escopo)
            .upper()
            .strip()
        )

        candidatos = [
            nome
            for nome
            in arquivos
            if Path(nome)
            .name
            .upper()
            .endswith(
                f"_{escopo}.CSV"
            )
        ]

        if candidatos:
            return candidatos[0]

    if len(arquivos) == 1:
        return arquivos[0]

    raise ValueError(
        "Não consegui identificar "
        "o CSV correto dentro do ZIP."
    )


def ler_csv_zip(
    caminho_zip,
    escopo=None,
    usecols=None,
):

    membro = encontrar_csv_no_zip(
        caminho_zip,
        escopo,
    )

    with ZipFile(
        caminho_zip
    ) as zip_file:

        with zip_file.open(
            membro
        ) as arquivo:

            return pd.read_csv(
                arquivo,
                sep=";",
                encoding="latin-1",
                dtype="string",
                usecols=usecols,
                low_memory=False,
            )


def iterar_csv_zip(
    caminho_zip,
    escopo,
    usecols,
    chunksize=200_000,
):

    membro = encontrar_csv_no_zip(
        caminho_zip,
        escopo,
    )

    with ZipFile(
        caminho_zip
    ) as zip_file:

        with zip_file.open(
            membro
        ) as arquivo:

            leitor = pd.read_csv(
                arquivo,
                sep=";",
                encoding="latin-1",
                dtype="string",
                usecols=usecols,
                chunksize=chunksize,
                low_memory=False,
            )

            for chunk in leitor:
                yield chunk


# =========================================================
# CROSSWALK TSE -> IBGE
# =========================================================

def carregar_crosswalk(
    uf,
):

    uf = (
        str(uf)
        .upper()
        .strip()
    )

    arquivo = (
        obter_arquivo_crosswalk()
    )

    tabela = ler_csv_zip(
        arquivo
    )

    def localizar(opcoes):

        for coluna in opcoes:

            if coluna in tabela.columns:
                return coluna

        return None

    coluna_tse = localizar(
        [
            "CD_MUNICIPIO_TSE",
            "COD_TSE",
            "CODIGO_TSE",
        ]
    )

    coluna_ibge = localizar(
        [
            "CD_MUNICIPIO_IBGE",
            "COD_IBGE",
            "CODIGO_IBGE",
        ]
    )

    coluna_uf = localizar(
        [
            "SG_UF",
            "UF",
        ]
    )

    if (
        coluna_tse is None
        or coluna_ibge is None
    ):

        raise ValueError(
            "Colunas de códigos "
            "TSE/IBGE não encontradas."
        )

    if coluna_uf:

        tabela = tabela[
            tabela[
                coluna_uf
            ]
            .astype(str)
            .str.upper()
            .eq(uf)
        ].copy()

    crosswalk = tabela[
        [
            coluna_tse,
            coluna_ibge,
        ]
    ].copy()

    crosswalk = crosswalk.rename(
        columns={
            coluna_tse:
                "codigo_tse",

            coluna_ibge:
                "codigo_ibge",
        }
    )

    crosswalk[
        "codigo_tse"
    ] = (
        crosswalk[
            "codigo_tse"
        ]
        .map(
            normalizar_codigo
        )
    )

    crosswalk[
        "codigo_ibge"
    ] = (
        crosswalk[
            "codigo_ibge"
        ]
        .map(
            normalizar_codigo
        )
        .astype("string")
        .str.zfill(7)
    )

    return (
        crosswalk
        .drop_duplicates()
        .reset_index(
            drop=True
        )
    )


def codigo_ibge_para_tse(
    uf,
    codigo_ibge,
):

    codigo_ibge = (
        str(codigo_ibge)
        .zfill(7)
    )

    crosswalk = carregar_crosswalk(
        uf
    )

    resultado = crosswalk[
        crosswalk[
            "codigo_ibge"
        ].eq(
            codigo_ibge
        )
    ]

    if resultado.empty:

        raise ValueError(
            f"Código IBGE {codigo_ibge} "
            "não encontrado."
        )

    return resultado.iloc[0][
        "codigo_tse"
    ]


# =========================================================
# CANDIDATOS
# =========================================================

def listar_candidatos(
    ano,
    uf,
    cargo,
    municipio_tse=None,
):

    uf = (
        str(uf)
        .upper()
        .strip()
    )

    cargo = (
        str(cargo)
        .upper()
        .strip()
    )

    parquet = (
        caminho_parquet_candidatos(
            ano,
            uf,
            cargo,
        )
    )

    # =====================================================
    # PARQUET
    # =====================================================

    if parquet:

        print(
            "[rápido] Candidatos "
            "via Parquet:"
        )

        print(
            parquet
        )

        candidatos = (
            pd.read_parquet(
                parquet
            )
        )

        candidatos[
            "cargo"
        ] = (
            candidatos[
                "cargo"
            ]
            .astype("string")
            .str.strip()
            .str.upper()
        )

        candidatos = candidatos[
            candidatos[
                "cargo"
            ].eq(
                cargo
            )
        ].copy()

        if cargo in CARGOS_MUNICIPAIS:

            if municipio_tse is None:

                raise ValueError(
                    "Para PREFEITO ou VEREADOR, "
                    "selecione o município."
                )

            codigo_alvo = (
                normalizar_codigo(
                    municipio_tse
                )
            )

            candidatos = candidatos[
                candidatos[
                    "sg_ue"
                ]
                .map(
                    normalizar_codigo
                )
                .eq(
                    codigo_alvo
                )
            ].copy()

        candidatos = (
            candidatos.rename(
                columns={
                    "sq_candidato":
                        "SQ_CANDIDATO",

                    "numero_candidato":
                        "NR_CANDIDATO",

                    "nome_candidato":
                        "NM_CANDIDATO",

                    "nome_urna_candidato":
                        "NM_URNA_CANDIDATO",

                    "partido":
                        "SG_PARTIDO",

                    "cargo":
                        "DS_CARGO",

                    "sg_ue":
                        "SG_UE",

                    "nm_ue":
                        "NM_UE",
                }
            )
        )

    # =====================================================
    # ZIP
    # =====================================================

    else:

        print(
            "[fallback] Parquet de "
            "candidatos não encontrado. "
            "Usando ZIP."
        )

        arquivo = (
            obter_arquivo_candidatos(
                ano
            )
        )

        escopo = (
            "BR"
            if cargo == "PRESIDENTE"
            else uf
        )

        candidatos = (
            ler_csv_zip(
                arquivo,
                escopo,
            )
        )

        candidatos[
            "DS_CARGO"
        ] = (
            candidatos[
                "DS_CARGO"
            ]
            .astype("string")
            .str.strip()
            .str.upper()
        )

        candidatos = candidatos[
            candidatos[
                "DS_CARGO"
            ].eq(
                cargo
            )
        ].copy()

        if cargo in CARGOS_MUNICIPAIS:

            if municipio_tse is None:

                raise ValueError(
                    "Para PREFEITO ou VEREADOR, "
                    "selecione o município."
                )

            codigo_alvo = (
                normalizar_codigo(
                    municipio_tse
                )
            )

            if (
                "SG_UE"
                in candidatos.columns
            ):

                candidatos = candidatos[
                    candidatos[
                        "SG_UE"
                    ]
                    .map(
                        normalizar_codigo
                    )
                    .eq(
                        codigo_alvo
                    )
                ].copy()

    # =====================================================
    # PADRONIZAÇÃO
    # =====================================================

    colunas = [
        "SQ_CANDIDATO",
        "NR_CANDIDATO",
        "NM_CANDIDATO",
        "NM_URNA_CANDIDATO",
        "SG_PARTIDO",
        "DS_CARGO",
        "SG_UE",
        "NM_UE",
    ]

    colunas = [
        coluna
        for coluna
        in colunas
        if coluna
        in candidatos.columns
    ]

    candidatos = candidatos[
        colunas
    ].copy()

    if (
        "SQ_CANDIDATO"
        in candidatos.columns
    ):

        candidatos = (
            candidatos
            .drop_duplicates(
                subset=[
                    "SQ_CANDIDATO"
                ]
            )
        )

    if (
        "NM_URNA_CANDIDATO"
        in candidatos.columns
    ):

        candidatos = (
            candidatos
            .sort_values(
                "NM_URNA_CANDIDATO"
            )
        )

    return (
        candidatos
        .reset_index(
            drop=True
        )
    )


def encontrar_candidato_por_numero(
    ano,
    uf,
    cargo,
    numero,
    municipio_tse=None,
):

    candidatos = listar_candidatos(
        ano=ano,
        uf=uf,
        cargo=cargo,
        municipio_tse=municipio_tse,
    )

    numero = str(
        numero
    ).strip()

    resultado = candidatos[
        candidatos[
            "NR_CANDIDATO"
        ]
        .astype("string")
        .str.strip()
        .eq(
            numero
        )
    ]

    if resultado.empty:

        raise ValueError(
            f"Candidato {numero} "
            "não encontrado."
        )

    if len(resultado) > 1:

        raise ValueError(
            "Mais de um candidato "
            "possui esse número."
        )

    return resultado.iloc[0]


# =========================================================
# VOTOS DO CANDIDATO
# =========================================================

def extrair_votos_candidato(
    ano,
    uf,
    turno,
    cargo,
    sq_candidato,
):

    uf = (
        str(uf)
        .upper()
        .strip()
    )

    cargo = (
        str(cargo)
        .upper()
        .strip()
    )

    sq_candidato = (
        str(sq_candidato)
        .strip()
    )

    parquet = (
        caminho_parquet_votacao(
            ano,
            uf,
            cargo,
        )
    )

    # =====================================================
    # PARQUET
    # =====================================================

    if parquet:

        print(
            "[rápido] Votação "
            "via Parquet:"
        )

        print(
            parquet
        )

        votos = pd.read_parquet(
            parquet,
            columns=[
                "turno",
                "sq_candidato",
                "codigo_tse",
                "municipio",
                "votos_candidato",
            ],
        )

        votos = votos[
            votos[
                "turno"
            ]
            .astype(int)
            .eq(
                int(turno)
            )
            &
            votos[
                "sq_candidato"
            ]
            .astype("string")
            .str.strip()
            .eq(
                sq_candidato
            )
        ].copy()

        if votos.empty:

            raise ValueError(
                "Nenhum voto encontrado "
                "no Parquet."
            )

        votos[
            "codigo_tse"
        ] = (
            votos[
                "codigo_tse"
            ]
            .map(
                normalizar_codigo
            )
        )

        votos[
            "votos_candidato"
        ] = pd.to_numeric(
            votos[
                "votos_candidato"
            ],
            errors="coerce",
        ).fillna(0)

        votos = (
            votos
            .groupby(
                [
                    "codigo_tse",
                    "municipio",
                ],
                as_index=False,
            )
            .agg(
                votos_candidato=(
                    "votos_candidato",
                    "sum",
                )
            )
            .rename(
                columns={
                    "municipio":
                        "municipio_tse"
                }
            )
        )

        return votos

    # =====================================================
    # ZIP
    # =====================================================

    print(
        "[fallback] Parquet de votação "
        "não encontrado. Usando ZIP."
    )

    arquivo = (
        obter_arquivo_votos(
            ano
        )
    )

    escopo = (
        "BR"
        if cargo == "PRESIDENTE"
        else uf
    )

    usecols = [
        "SG_UF",
        "NR_TURNO",
        "DS_CARGO",
        "CD_MUNICIPIO",
        "NM_MUNICIPIO",
        "SQ_CANDIDATO",
        "QT_VOTOS_NOMINAIS_VALIDOS",
    ]

    partes = []

    for chunk in iterar_csv_zip(
        arquivo,
        escopo,
        usecols,
    ):

        mask = (
            chunk[
                "SG_UF"
            ]
            .astype("string")
            .str.upper()
            .eq(uf)
            &
            chunk[
                "NR_TURNO"
            ]
            .astype("string")
            .str.strip()
            .eq(
                str(turno)
            )
            &
            chunk[
                "DS_CARGO"
            ]
            .astype("string")
            .str.strip()
            .str.upper()
            .eq(cargo)
            &
            chunk[
                "SQ_CANDIDATO"
            ]
            .astype("string")
            .str.strip()
            .eq(
                sq_candidato
            )
        )

        filtrado = chunk.loc[
            mask
        ].copy()

        if not filtrado.empty:
            partes.append(
                filtrado
            )

    if not partes:

        raise ValueError(
            "Nenhum voto encontrado."
        )

    votos = pd.concat(
        partes,
        ignore_index=True,
    )

    votos[
        "QT_VOTOS_NOMINAIS_VALIDOS"
    ] = pd.to_numeric(
        votos[
            "QT_VOTOS_NOMINAIS_VALIDOS"
        ],
        errors="coerce",
    ).fillna(0)

    votos = (
        votos
        .groupby(
            [
                "CD_MUNICIPIO",
                "NM_MUNICIPIO",
            ],
            as_index=False,
        )
        .agg(
            votos_candidato=(
                "QT_VOTOS_NOMINAIS_VALIDOS",
                "sum",
            )
        )
        .rename(
            columns={
                "CD_MUNICIPIO":
                    "codigo_tse",

                "NM_MUNICIPIO":
                    "municipio_tse",
            }
        )
    )

    votos[
        "codigo_tse"
    ] = (
        votos[
            "codigo_tse"
        ]
        .map(
            normalizar_codigo
        )
    )

    return votos


# =========================================================
# VOTOS VÁLIDOS
# =========================================================

def extrair_votos_validos(
    ano,
    uf,
    turno,
    cargo,
    codigo_tse_municipio=None,
):

    uf = (
        str(uf)
        .upper()
        .strip()
    )

    cargo = (
        str(cargo)
        .upper()
        .strip()
    )

    codigo_alvo = (
        normalizar_codigo(
            codigo_tse_municipio
        )
        if codigo_tse_municipio
        is not None
        else None
    )

    parquet = (
        caminho_parquet_apuracao(
            ano,
            uf,
            cargo,
        )
    )

    # =====================================================
    # PARQUET
    # =====================================================

    if parquet:

        print(
            "[rápido] Apuração "
            "via Parquet:"
        )

        print(
            parquet
        )

        validos = pd.read_parquet(
            parquet,
            columns=[
                "turno",
                "codigo_tse",
                "municipio",
                "votos_validos",
            ],
        )

        validos = validos[
            validos[
                "turno"
            ]
            .astype(int)
            .eq(
                int(turno)
            )
        ].copy()

        validos[
            "codigo_tse"
        ] = (
            validos[
                "codigo_tse"
            ]
            .map(
                normalizar_codigo
            )
        )

        if codigo_alvo:

            validos = validos[
                validos[
                    "codigo_tse"
                ].eq(
                    codigo_alvo
                )
            ].copy()

        if validos.empty:

            raise ValueError(
                "Nenhum dado de votos "
                "válidos encontrado "
                "no Parquet."
            )

        validos[
            "votos_validos"
        ] = pd.to_numeric(
            validos[
                "votos_validos"
            ],
            errors="coerce",
        ).fillna(0)

        validos = (
            validos
            .groupby(
                [
                    "codigo_tse",
                    "municipio",
                ],
                as_index=False,
            )
            .agg(
                votos_validos=(
                    "votos_validos",
                    "sum",
                )
            )
            .rename(
                columns={
                    "municipio":
                        "municipio_tse"
                }
            )
        )

        return validos

    # =====================================================
    # ZIP
    # =====================================================

    print(
        "[fallback] Parquet de apuração "
        "não encontrado. Usando ZIP."
    )

    arquivo = (
        obter_arquivo_detalhe(
            ano
        )
    )

    escopo = (
        "BR"
        if cargo == "PRESIDENTE"
        else uf
    )

    usecols = [
        "SG_UF",
        "NR_TURNO",
        "DS_CARGO",
        "CD_MUNICIPIO",
        "NM_MUNICIPIO",
        "QT_TOTAL_VOTOS_VALIDOS",
    ]

    partes = []

    for chunk in iterar_csv_zip(
        arquivo,
        escopo,
        usecols,
    ):

        mask = (
            chunk[
                "SG_UF"
            ]
            .astype("string")
            .str.upper()
            .eq(uf)
            &
            chunk[
                "NR_TURNO"
            ]
            .astype("string")
            .str.strip()
            .eq(
                str(turno)
            )
            &
            chunk[
                "DS_CARGO"
            ]
            .astype("string")
            .str.strip()
            .str.upper()
            .eq(
                cargo
            )
        )

        if codigo_alvo:

            codigos = (
                chunk[
                    "CD_MUNICIPIO"
                ]
                .map(
                    normalizar_codigo
                )
            )

            mask = (
                mask
                &
                codigos.eq(
                    codigo_alvo
                )
            )

        filtrado = chunk.loc[
            mask
        ].copy()

        if not filtrado.empty:

            partes.append(
                filtrado
            )

    if not partes:

        raise ValueError(
            "Nenhum dado de votos "
            "válidos encontrado."
        )

    validos = pd.concat(
        partes,
        ignore_index=True,
    )

    validos[
        "QT_TOTAL_VOTOS_VALIDOS"
    ] = pd.to_numeric(
        validos[
            "QT_TOTAL_VOTOS_VALIDOS"
        ],
        errors="coerce",
    ).fillna(0)

    validos = (
        validos
        .groupby(
            [
                "CD_MUNICIPIO",
                "NM_MUNICIPIO",
            ],
            as_index=False,
        )
        .agg(
            votos_validos=(
                "QT_TOTAL_VOTOS_VALIDOS",
                "sum",
            )
        )
        .rename(
            columns={
                "CD_MUNICIPIO":
                    "codigo_tse",

                "NM_MUNICIPIO":
                    "municipio_tse",
            }
        )
    )

    validos[
        "codigo_tse"
    ] = (
        validos[
            "codigo_tse"
        ]
        .map(
            normalizar_codigo
        )
    )

    return validos