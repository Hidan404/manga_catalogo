#!/usr/bin/env python3
"""Promove a conta para role 'admin' direto no banco de producao.

Uso:
    1. No painel do Render, va em Postgres > Connections e copie a
       "External Database URL".
    2. Adicione no .env desta pasta (nunca compartilhe esse valor):
         DATABASE_URL="postgresql://..."
    3. Rode:
         python3 promover_admin.py

Promove a conta de MANGA_EMAIL (do mesmo .env). Sem efeito na API:
a role e lida do banco a cada request, entao passa a valer na hora.
"""

import os
import re
import sys
from pathlib import Path

from dotenv import load_dotenv
from sqlalchemy import create_engine, text
from sqlalchemy.exc import SQLAlchemyError

PASTA_SCRIPT = Path(__file__).resolve().parent
load_dotenv(PASTA_SCRIPT / ".env")


def normalizar_url(url: str) -> str:
    # Normaliza qualquer variante (postgres://, postgresql://,
    # postgresql+psycopg:// do Supabase) para o driver psycopg2.
    url = re.sub(r"^postgres(ql)?(\+\w+)?://", "postgresql+psycopg2://", url)
    # Supabase exige SSL na conexao direta
    if "sslmode=" not in url:
        url += ("&" if "?" in url else "?") + "sslmode=require"
    return url


def main():
    url = os.environ.get("DATABASE_URL")
    email = os.environ.get("MANGA_EMAIL")
    if not url:
        sys.exit("Defina DATABASE_URL no .env (URL do Postgres do Render).")
    if not email:
        sys.exit("Defina MANGA_EMAIL no .env (conta a ser promovida).")

    engine = create_engine(normalizar_url(url))
    try:
        with engine.begin() as conn:
            existe = conn.execute(
                text("SELECT id, role FROM usuarios WHERE email = :email"),
                {"email": email},
            ).fetchone()
            if not existe:
                sys.exit(f"Nenhuma conta com o e-mail {email} no banco.")
            id_usuario, role_atual = existe
            if role_atual == "admin":
                print(f"Conta {email} (id {id_usuario}) ja e admin. Nada a fazer.")
                return
            conn.execute(
                text("UPDATE usuarios SET role = 'admin' WHERE email = :email"),
                {"email": email},
            )
        print(f"Conta {email} (id {id_usuario}) promovida: 'user' -> 'admin'.")
        print("Vale imediatamente — sem redeploy. Rode o manga_sync.py agora.")
    except SQLAlchemyError as exc:
        sys.exit(f"Erro de banco: {exc.__class__.__name__} (verifique DATABASE_URL).")
    finally:
        engine.dispose()


if __name__ == "__main__":
    main()
