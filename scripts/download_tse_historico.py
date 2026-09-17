from __future__ import annotations

import shutil
import subprocess
import sys
import time
import unicodedata
from pathlib import Path
from zipfile import is_zipfile

import requests
from tqdm import tqdm

ANOS = [2014, 2016, 2018, 2020, 2022, 2024]
CKAN_API = "https://dadosabertos.tse.jus.br/api/3/action/package_show"
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

BASE_DIR = Path(__file__).resolve().parent.parent
DESTINO_BASE = BASE_DIR / "data" / "tse_historico"
RAW_EXISTENTE = BASE_DIR / "data" / "raw"

ARQUIVOS = {
    "candidatos": {
        "nome": "consulta_cand_{ano}.zip",
        "package": "candidatos-{ano}",
        "termos": ["candidatos"],
        "url_fallback": (
            "https://cdn.tse.jus.br/estatistica/sead/odsele/"
            "consulta_cand/consulta_cand_{ano}.zip"
        ),
    },
    "votacao": {
        "nome": "votacao_candidato_munzona_{ano}.zip",
        "package": "resultados-{ano}",
        "termos": ["votacao nominal", "municipio", "zona"],
        "url_fallback": (
            "https://cdn.tse.jus.br/estatistica/sead/odsele/"
            "votacao_candidato_munzona/"
            "votacao_candidato_munzona_{ano}.zip"
        ),
    },
    "apuracao": {
        "nome": "detalhe_votacao_munzona_{ano}.zip",
        "package": "resultados-{ano}",
        "termos": ["detalhe da apuracao", "municipio", "zona"],
        "url_fallback": (
            "https://cdn.tse.jus.br/estatistica/sead/odsele/"
            "detalhe_votacao_munzona/"
            "detalhe_votacao_munzona_{ano}.zip"
        ),
    },
}

CROSSWALK_NOME = "municipio_tse_ibge.zip"
CROSSWALK_URL = (
    "https://cdn.tse.jus.br/estatistica/sead/odsele/"
    "municipio_tse_ibge/municipio_tse_ibge.zip"
)


def normalizar(texto: str) -> str:
    texto = unicodedata.normalize("NFKD", texto or "")
    texto = "".join(c for c in texto if not unicodedata.combining(c))
    return texto.lower().strip()


def arquivo_zip_valido(caminho: Path) -> bool:
    return caminho.exists() and caminho.stat().st_size > 0 and is_zipfile(caminho)


def tamanho_mb(caminho: Path) -> float:
    return caminho.stat().st_size / (1024 * 1024)


def copiar_se_ja_existe(nome: str, destino: Path) -> bool:
    origem = RAW_EXISTENTE / nome
    if not arquivo_zip_valido(origem):
        return False
    destino.parent.mkdir(parents=True, exist_ok=True)
    if arquivo_zip_valido(destino):
        return True
    print(f"  [reuso] Copiando arquivo já existente: {origem}")
    shutil.copy2(origem, destino)
    return True


def obter_package(package_id: str) -> dict:
    resposta = SESSION.get(CKAN_API, params={"id": package_id}, timeout=30)
    resposta.raise_for_status()
    payload = resposta.json()
    if not payload.get("success"):
        raise RuntimeError(f"CKAN não retornou sucesso para {package_id}")
    return payload["result"]


def localizar_recurso(package_id: str, termos: list[str]) -> str | None:
    try:
        package = obter_package(package_id)
    except Exception as erro:
        print(f"  [aviso] API CKAN indisponível: {erro}")
        return None

    termos_norm = [normalizar(t) for t in termos]
    for recurso in package.get("resources", []):
        nome = normalizar(recurso.get("name", ""))
        descricao = normalizar(recurso.get("description", ""))
        url = recurso.get("url", "")
        texto = f"{nome} {descricao} {normalizar(url)}"
        if all(termo in texto for termo in termos_norm):
            return url
    return None


def url_do_arquivo(tipo: str, ano: int) -> str:
    config = ARQUIVOS[tipo]
    url_api = localizar_recurso(
        package_id=config["package"].format(ano=ano),
        termos=config["termos"],
    )
    if url_api:
        print("  [api] URL descoberta pelo Portal de Dados Abertos.")
        return url_api
    print("  [fallback] Usando padrão oficial do CDN do TSE.")
    return config["url_fallback"].format(ano=ano)


def baixar_com_requests(url: str, destino_temp: Path) -> None:
    with SESSION.get(url, stream=True, timeout=(30, 900), allow_redirects=True) as resposta:
        if resposta.status_code == 403:
            raise PermissionError("HTTP 403")
        resposta.raise_for_status()
        total = int(resposta.headers.get("content-length", 0))
        with open(destino_temp, "wb") as arquivo:
            with tqdm(
                total=total,
                unit="B",
                unit_scale=True,
                unit_divisor=1024,
                desc=destino_temp.name.replace(".part", ""),
            ) as barra:
                for bloco in resposta.iter_content(chunk_size=1024 * 1024):
                    if bloco:
                        arquivo.write(bloco)
                        barra.update(len(bloco))


def baixar_com_curl(url: str, destino_temp: Path) -> None:
    comando = [
        "curl.exe", "-L", "--fail", "--retry", "4", "--retry-delay", "3",
        "-A", HEADERS["User-Agent"], "-e", HEADERS["Referer"],
        "-o", str(destino_temp), url,
    ]
    resultado = subprocess.run(comando)
    if resultado.returncode != 0:
        raise RuntimeError(f"curl.exe falhou com código {resultado.returncode}")


def baixar(url: str, destino: Path) -> str:
    destino.parent.mkdir(parents=True, exist_ok=True)

    if arquivo_zip_valido(destino):
        print(f"  [ok] Já existe: {destino.name} ({tamanho_mb(destino):,.1f} MB)")
        return "existente"

    if copiar_se_ja_existe(destino.name, destino):
        print(f"  [ok] Reutilizado: {destino.name} ({tamanho_mb(destino):,.1f} MB)")
        return "reutilizado"

    temporario = destino.with_suffix(destino.suffix + ".part")
    if temporario.exists():
        temporario.unlink()

    inicio = time.time()
    try:
        baixar_com_requests(url, temporario)
    except PermissionError:
        print("  [403] CDN bloqueou requests. Tentando curl.exe...")
        if temporario.exists():
            temporario.unlink()
        baixar_com_curl(url, temporario)
    except Exception as erro:
        if temporario.exists():
            temporario.unlink()
        raise RuntimeError(f"Erro no download: {erro}") from erro

    if not arquivo_zip_valido(temporario):
        if temporario.exists():
            temporario.unlink()
        raise ValueError(f"O arquivo recebido não é um ZIP válido. URL: {url}")

    temporario.replace(destino)
    duracao = time.time() - inicio
    print(
        f"  [ok] Concluído: {destino.name} | "
        f"{tamanho_mb(destino):,.1f} MB | {duracao / 60:.1f} min"
    )
    return "baixado"


def baixar_historico() -> None:
    DESTINO_BASE.mkdir(parents=True, exist_ok=True)
    resumo = {"baixado": 0, "existente": 0, "reutilizado": 0, "erro": 0}

    print("=" * 70)
    print("DOWNLOAD DO HISTÓRICO ELEITORAL DO TSE")
    print("Anos:", ", ".join(map(str, ANOS)))
    print("Destino:", DESTINO_BASE)
    print("=" * 70)

    for ano in ANOS:
        print("\n" + "=" * 70)
        print(f"ELEIÇÃO {ano}")
        print("=" * 70)

        pasta_ano = DESTINO_BASE / str(ano)
        pasta_ano.mkdir(parents=True, exist_ok=True)

        for tipo, config in ARQUIVOS.items():
            nome = config["nome"].format(ano=ano)
            destino = pasta_ano / nome
            print(f"\n[{tipo.upper()}] {nome}")

            try:
                url = url_do_arquivo(tipo, ano)
                print(f"  URL: {url}")
                status = baixar(url, destino)
                resumo[status] += 1
            except Exception as erro:
                resumo["erro"] += 1
                print(f"  [ERRO] {erro}")

    print("\n" + "=" * 70)
    print("ARQUIVO DE APOIO: CÓDIGOS TSE -> IBGE")
    print("=" * 70)

    try:
        status = baixar(
            CROSSWALK_URL,
            DESTINO_BASE / "apoio" / CROSSWALK_NOME,
        )
        resumo[status] += 1
    except Exception as erro:
        resumo["erro"] += 1
        print(f"  [ERRO] {erro}")

    print("\n" + "=" * 70)
    print("RESUMO")
    print("=" * 70)
    print(f"Baixados agora : {resumo['baixado']}")
    print(f"Já existentes  : {resumo['existente']}")
    print(f"Reutilizados   : {resumo['reutilizado']}")
    print(f"Erros          : {resumo['erro']}")
    print(f"Arquivos eleitorais esperados: {len(ANOS) * len(ARQUIVOS)}")
    print("Arquivo adicional de apoio: 1")

    if resumo["erro"] == 0:
        print("\nTudo concluído com sucesso.")
    else:
        print(
            "\nAlguns arquivos falharam. Execute o script novamente: "
            "os downloads válidos serão ignorados e apenas os faltantes serão tentados."
        )


if __name__ == "__main__":
    try:
        baixar_historico()
    except KeyboardInterrupt:
        print("\nDownload interrompido pelo usuário.")
        sys.exit(130)
