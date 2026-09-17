import re
import unicodedata

import pandas as pd

from src.config import (
    CARGOS_MUNICIPAIS,
    PROCESSED_DIR,
    obter_faixas,
    sistema_eleitoral,
)
from src.transform import criar_base_geografica
from src.tse import (
    carregar_crosswalk,
    extrair_votos_candidato,
    extrair_votos_validos,
)


def slugify(texto):
    texto = unicodedata.normalize("NFKD", str(texto))
    texto = "".join(
        caractere
        for caractere in texto
        if not unicodedata.combining(caractere)
    )
    texto = texto.lower()
    texto = re.sub(r"[^a-z0-9]+", "_", texto)
    return texto.strip("_")


def prefixo_resultado(
    ano,
    uf,
    cargo,
    candidato,
    municipio_tse=None,
):
    nome = slugify(candidato["NM_URNA_CANDIDATO"])
    cargo_slug = slugify(cargo)

    partes = [
        str(ano),
        str(uf).lower(),
        cargo_slug,
    ]

    if str(cargo).upper() in CARGOS_MUNICIPAIS:
        if municipio_tse is None:
            raise ValueError("Cargo municipal exige municipio_tse no nome do resultado.")
        partes.append(str(municipio_tse))

    partes.extend([
        str(candidato["NR_CANDIDATO"]),
        nome,
    ])

    return "_".join(partes)


def caminho_resultado(
    ano,
    uf,
    cargo,
    candidato,
    municipio_tse=None,
):
    prefixo = prefixo_resultado(
        ano=ano,
        uf=uf,
        cargo=cargo,
        candidato=candidato,
        municipio_tse=municipio_tse,
    )

    return PROCESSED_DIR / f"{prefixo}.parquet"


def construir_mapa_eleitoral(
    ano,
    uf,
    turno,
    cargo,
    candidato,
    municipio_tse=None,
    municipio_ibge=None,
    nome_municipio=None,
):
    uf = str(uf).upper().strip()
    cargo = str(cargo).upper().strip()
    municipal = cargo in CARGOS_MUNICIPAIS

    if municipal and municipio_tse is None:
        raise ValueError("PREFEITO e VEREADOR exigem o município da candidatura.")

    print("\nConstruindo base geográfica...")
    geo = criar_base_geografica(uf)

    print("\nExtraindo votos do candidato...")
    votos = extrair_votos_candidato(
        ano=ano,
        uf=uf,
        turno=turno,
        cargo=cargo,
        sq_candidato=candidato["SQ_CANDIDATO"],
    )

    print("\nExtraindo votos válidos...")
    validos = extrair_votos_validos(
        ano=ano,
        uf=uf,
        turno=turno,
        cargo=cargo,
        codigo_tse_municipio=(municipio_tse if municipal else None),
    )

    print("\nCarregando correspondência TSE -> IBGE...")
    crosswalk = carregar_crosswalk(uf)

    # =====================================================
    # VOTOS + VÁLIDOS
    # =====================================================

    eleitoral = validos.merge(
        votos[["codigo_tse", "votos_candidato"]],
        on="codigo_tse",
        how="left",
        validate="one_to_one",
    )

    eleitoral["votos_candidato"] = (
        eleitoral["votos_candidato"]
        .fillna(0)
        .astype(int)
    )

    # =====================================================
    # TSE -> IBGE
    # =====================================================

    eleitoral = eleitoral.merge(
        crosswalk,
        on="codigo_tse",
        how="left",
        validate="one_to_one",
    )

    if eleitoral["codigo_ibge"].isna().any():
        problemas = eleitoral[eleitoral["codigo_ibge"].isna()]
        raise ValueError(
            "Há municípios do TSE sem correspondência IBGE:\n"
            f"{problemas.head()}"
        )

    # =====================================================
    # GEOGRAFIA + ELEIÇÃO
    # =====================================================

    base = geo.merge(
        eleitoral[
            [
                "codigo_ibge",
                "codigo_tse",
                "votos_candidato",
                "votos_validos",
            ]
        ],
        on="codigo_ibge",
        how="left",
        validate="one_to_one",
    )

    # Em cargos estaduais/nacionais, esperamos dado eleitoral
    # em todos os municípios da UF selecionada.
    if not municipal and base["votos_validos"].isna().any():
        problemas = base[base["votos_validos"].isna()]
        raise ValueError(
            "Há municípios sem dados eleitorais:\n"
            f"{problemas.head()}"
        )

    # =====================================================
    # FEATURE ENGINEERING
    # =====================================================

    base["percentual_validos"] = pd.NA

    mask_validos = (
        base["votos_validos"].notna()
        & base["votos_validos"].gt(0)
    )

    base.loc[mask_validos, "percentual_validos"] = (
        100
        * base.loc[mask_validos, "votos_candidato"]
        / base.loc[mask_validos, "votos_validos"]
    )

    base["percentual_validos"] = pd.to_numeric(
        base["percentual_validos"],
        errors="coerce",
    )

    bins, labels, _ = obter_faixas(cargo)

    base["classe_percentual"] = pd.cut(
        base["percentual_validos"],
        bins=bins,
        labels=labels,
        right=False,
        include_lowest=True,
    ).astype("string")

    if municipal:
        base["classe_percentual"] = (
            base["classe_percentual"]
            .fillna("Não concorreu")
        )
    else:
        base["classe_percentual"] = (
            base["classe_percentual"]
            .fillna("Sem dados")
        )

    # =====================================================
    # METADADOS
    # =====================================================

    base["ano"] = int(ano)
    base["uf"] = uf
    base["turno"] = int(turno)
    base["cargo"] = cargo
    base["sistema_eleitoral"] = sistema_eleitoral(cargo)
    base["sq_candidato"] = candidato["SQ_CANDIDATO"]
    base["numero_candidato"] = candidato["NR_CANDIDATO"]
    base["nome_candidato"] = candidato["NM_URNA_CANDIDATO"]
    base["partido"] = candidato.get("SG_PARTIDO", "")
    base["municipio_candidatura_tse"] = (
        str(municipio_tse) if municipio_tse is not None else ""
    )
    base["municipio_candidatura_ibge"] = (
        str(municipio_ibge) if municipio_ibge is not None else ""
    )
    base["municipio_candidatura_nome"] = nome_municipio or ""

    # =====================================================
    # SALVAR
    # =====================================================

    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)

    prefixo = prefixo_resultado(
        ano=ano,
        uf=uf,
        cargo=cargo,
        candidato=candidato,
        municipio_tse=municipio_tse,
    )

    parquet = PROCESSED_DIR / f"{prefixo}.parquet"
    csv = PROCESSED_DIR / f"{prefixo}.csv"

    base.to_parquet(parquet, index=False)
    base.drop(columns="geometry").to_csv(
        csv,
        index=False,
        encoding="utf-8-sig",
    )

    print(f"\nArquivo criado:\n{parquet}")

    return base
