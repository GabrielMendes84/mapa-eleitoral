import os

import pandas as pd
from databricks import sql


# =========================================================
# CONFIGURAÇÃO
# =========================================================

def obter_configuracao():
    """
    Obtém as informações de conexão
    armazenadas nas variáveis de ambiente.
    """

    hostname = os.getenv(
        "DATABRICKS_SERVER_HOSTNAME"
    )

    http_path = os.getenv(
        "DATABRICKS_HTTP_PATH"
    )

    faltando = []

    if not hostname:
        faltando.append(
            "DATABRICKS_SERVER_HOSTNAME"
        )

    if not http_path:
        faltando.append(
            "DATABRICKS_HTTP_PATH"
        )

    if faltando:
        raise EnvironmentError(
            "Variáveis de ambiente ausentes: "
            + ", ".join(faltando)
        )

    return hostname, http_path


# =========================================================
# CONEXÃO
# =========================================================

def conectar():
    """
    Cria uma conexão com o SQL Warehouse
    utilizando OAuth user-to-machine.
    """

    hostname, http_path = (
        obter_configuracao()
    )

    connection = sql.connect(
        server_hostname=hostname,
        http_path=http_path,
        auth_type="databricks-oauth",
        catalog="politica",
        schema="gold",
    )

    return connection


# =========================================================
# EXECUTAR QUERY
# =========================================================

def executar_query(
    query,
    parameters=None,
):
    """
    Executa uma consulta SQL e devolve
    o resultado como pandas DataFrame.
    """

    connection = conectar()

    try:

        cursor = connection.cursor()

        try:

            if parameters is None:

                cursor.execute(
                    query
                )

            else:

                cursor.execute(
                    query,
                    parameters,
                )

            resultado_arrow = (
                cursor.fetchall_arrow()
            )

            dataframe = (
                resultado_arrow.to_pandas()
            )

            return dataframe

        finally:

            cursor.close()

    finally:

        connection.close()


# =========================================================
# TESTE
# =========================================================

def testar_conexao():
    """
    Testa acesso à tabela Gold principal.
    """

    query = """
        SELECT
            COUNT(*) AS registros
        FROM politica.gold.resultado_candidato_municipio
    """

    return executar_query(
        query
    )


# =========================================================
# EXECUÇÃO DIRETA
# =========================================================

if __name__ == "__main__":

    print(
        "Testando conexão "
        "com o Databricks..."
    )

    resultado = testar_conexao()

    print(
        "\nConexão realizada com sucesso."
    )

    print(
        resultado
    )