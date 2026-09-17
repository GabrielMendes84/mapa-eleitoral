import argparse

from src.config import (
    CARGOS_MUNICIPAIS,
    DEFAULT_ANO,
    DEFAULT_TURNO,
    DEFAULT_UF,
)
from src.election import construir_mapa_eleitoral
from src.tse import (
    codigo_ibge_para_tse,
    encontrar_candidato_por_numero,
)
from src.visualize import gerar_mapa_eleitoral


def main():
    parser = argparse.ArgumentParser(
        description=(
            "Gera uma análise geográfica da votação municipal de um candidato."
        )
    )

    parser.add_argument("--ano", type=int, default=DEFAULT_ANO)
    parser.add_argument("--uf", type=str, default=DEFAULT_UF)
    parser.add_argument("--turno", type=int, default=DEFAULT_TURNO)
    parser.add_argument("--cargo", type=str, required=True)
    parser.add_argument("--numero", type=str, required=True)
    parser.add_argument(
        "--codigo-ibge",
        type=str,
        default=None,
        help=(
            "Código IBGE do município. Obrigatório para PREFEITO e VEREADOR."
        ),
    )
    parser.add_argument(
        "--nome-municipio",
        type=str,
        default=None,
        help="Nome amigável do município para metadados/título.",
    )

    args = parser.parse_args()

    uf = args.uf.upper()
    cargo = args.cargo.upper()

    municipio_tse = None
    municipio_ibge = None

    if cargo in CARGOS_MUNICIPAIS:
        if not args.codigo_ibge:
            parser.error(
                "Para PREFEITO ou VEREADOR, informe --codigo-ibge."
            )

        municipio_ibge = str(args.codigo_ibge).zfill(7)
        municipio_tse = codigo_ibge_para_tse(uf, municipio_ibge)

    print("\n" + "=" * 50)
    print("MAPA ELEITORAL")
    print("=" * 50)
    print(f"Ano: {args.ano}")
    print(f"UF: {uf}")
    print(f"Turno: {args.turno}")
    print(f"Cargo: {cargo}")
    print(f"Número: {args.numero}")

    if municipio_ibge:
        print(f"Município IBGE: {municipio_ibge}")
        print(f"Município TSE: {municipio_tse}")

    candidato = encontrar_candidato_por_numero(
        ano=args.ano,
        uf=uf,
        cargo=cargo,
        numero=args.numero,
        municipio_tse=municipio_tse,
    )

    print("\nCandidato encontrado:")
    print(candidato.to_string())

    base = construir_mapa_eleitoral(
        ano=args.ano,
        uf=uf,
        turno=args.turno,
        cargo=cargo,
        candidato=candidato,
        municipio_tse=municipio_tse,
        municipio_ibge=municipio_ibge,
        nome_municipio=args.nome_municipio,
    )

    gerar_mapa_eleitoral(base, salvar=True)

    base_com_dados = base[base["votos_validos"].notna()]
    total_votos = base_com_dados["votos_candidato"].fillna(0).sum()
    total_validos = base_com_dados["votos_validos"].fillna(0).sum()
    percentual_geral = (
        100 * total_votos / total_validos
        if total_validos > 0
        else float("nan")
    )

    print("\n" + "=" * 50)
    print("PIPELINE CONCLUÍDO")
    print("=" * 50)
    print(f"Municípios com dados: {len(base_com_dados)}")
    print(f"Votos do candidato: {total_votos:,.0f}")
    print(f"Votos válidos do cargo: {total_validos:,.0f}")
    print(f"Percentual: {percentual_geral:.2f}%")


if __name__ == "__main__":
    main()
