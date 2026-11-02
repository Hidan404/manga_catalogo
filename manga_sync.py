#!/usr/bin/env python3
"""Sincroniza mangás e livros com a API Manga Livros.

Uso:
    python3 manga_sync.py obras/black_clover.json

Credenciais (lidas do .env na pasta do script ou do ambiente):
    .env:
        MANGA_EMAIL="seu@email.com"
        MANGA_SENHA="sua_senha"

O arquivo JSON deve conter:
    {
      "tipo": "manga",            // ou "livro"
      "obra": { ...campos da API... },
      "volumes_possuidos": [1,2]  // apenas para mangá
    }

Campos extras no JSON (ex.: "controle") são ignorados pelo script
e servem apenas como referência local (faltantes, ISBNs etc.).
"""

import json
import os
import sys
from pathlib import Path

import requests
from dotenv import load_dotenv

PASTA_SCRIPT = Path(__file__).resolve().parent
load_dotenv(PASTA_SCRIPT / ".env")

BASE_URL = os.environ.get("MANGA_API_URL", "https://api-manga-livros.onrender.com")


def log(msg):
    print(msg, flush=True)


def autenticar():
    email = os.environ.get("MANGA_EMAIL")
    senha = os.environ.get("MANGA_SENHA")
    if not email or not senha:
        sys.exit(
            "Credenciais nao encontradas. Crie o arquivo .env em "
            f"{PASTA_SCRIPT} com MANGA_EMAIL e MANGA_SENHA, "
            "ou exporte essas variaveis no ambiente."
        )
    resp = requests.post(
        f"{BASE_URL}/auth/login",
        json={"email": email, "senha": senha},
        timeout=60,
    )
    if resp.status_code != 200:
        sys.exit(f"Login falhou ({resp.status_code}): {resp.text}")
    token = resp.json().get("access_token")
    if not token:
        sys.exit(f"Resposta de login sem access_token: {resp.text}")
    role = resp.json().get("role") or "desconhecida"
    log(f"Login OK (role: {role}).")
    if role != "admin":
        log(
            "AVISO: a API exige role 'admin' para criar mangas/livros "
            "(POST retorna 403 'Acesso negado' para role 'user')."
        )
    return {"Authorization": f"Bearer {token}"}


def encontrar_por_titulo(headers, colecao, titulo):
    resp = requests.get(f"{BASE_URL}/{colecao}/", headers=headers, timeout=60)
    resp.raise_for_status()
    alvo = titulo.strip().casefold()
    for item in resp.json():
        if item.get("titulo", "").strip().casefold() == alvo:
            return item
    return None


def volumes_existentes(headers, manga_id):
    resp = requests.get(
        f"{BASE_URL}/mangas/{manga_id}/volumes", headers=headers, timeout=60
    )
    resp.raise_for_status()
    return {v["numero"]: v for v in resp.json()}


def enviar_volume(headers, manga_id, numero, comprado):
    resp = requests.post(
        f"{BASE_URL}/mangas/{manga_id}/volumes",
        headers=headers,
        json={"numero": numero, "comprado": comprado},
        timeout=60,
    )
    return resp


def sincronizar_manga(headers, dados):
    obra = dados["obra"]
    titulo = obra["titulo"]
    volumes = sorted(set(dados.get("volumes_possuidos", [])))

    existente = encontrar_por_titulo(headers, "mangas", titulo)
    if existente:
        manga_id = existente["id"]
        log(f"Manga ja cadastrado: '{titulo}' (id {manga_id}) — reutilizando.")
    else:
        resp = requests.post(
            f"{BASE_URL}/mangas/", headers=headers, json=obra, timeout=60
        )
        if resp.status_code in (401, 403):
            sys.exit(
                f"Erro ao criar manga ({resp.status_code}): {resp.text}\n"
                "Sua conta nao tem permissao de escrita. Use uma conta admin "
                "no .env ou ajuste o role da conta no backend."
            )
        if resp.status_code not in (200, 201):
            sys.exit(f"Erro ao criar manga ({resp.status_code}): {resp.text}")
        manga_id = resp.json()["id"]
        log(f"Manga criado: '{titulo}' (id {manga_id}).")

    ja_cadastrados = volumes_existentes(headers, manga_id)
    criados, pulados, erros = [], [], []

    for n in volumes:
        if n in ja_cadastrados:
            pulados.append(n)
            continue
        resp = enviar_volume(headers, manga_id, n, comprado=True)
        if resp.status_code in (200, 201):
            criados.append(n)
            log(f"  Volume {n}: criado (comprado=true).")
        else:
            erros.append((n, resp.status_code, resp.text))
            log(f"  Volume {n}: ERRO {resp.status_code} — {resp.text}")

    log("")
    log(f"Resumo '{titulo}': id={manga_id}")
    log(f"  Volumes criados : {criados or 'nenhum'}")
    log(f"  Ja existentes   : {pulados or 'nenhum'}")
    log(f"  Erros           : {len(erros)}")
    return manga_id


def sincronizar_livro(headers, dados):
    obra = dados["obra"]
    titulo = obra["titulo"]

    existente = encontrar_por_titulo(headers, "livros", titulo)
    if existente:
        log(f"Livro ja cadastrado: '{titulo}' (id {existente['id']}) — nada a fazer.")
        return existente["id"]

    resp = requests.post(f"{BASE_URL}/livros/", headers=headers, json=obra, timeout=60)
    if resp.status_code in (401, 403):
        sys.exit(
            f"Erro ao criar livro ({resp.status_code}): {resp.text}\n"
            "Sua conta nao tem permissao de escrita. Use uma conta admin "
            "no .env ou ajuste o role da conta no backend."
        )
    if resp.status_code not in (200, 201):
        sys.exit(f"Erro ao criar livro ({resp.status_code}): {resp.text}")
    livro_id = resp.json()["id"]
    log(f"Livro criado: '{titulo}' (id {livro_id}).")
    return livro_id


def main():
    if len(sys.argv) != 2:
        sys.exit(f"Uso: {sys.argv[0]} <arquivo_obra.json>")
    caminho = Path(sys.argv[1])
    if not caminho.exists():
        sys.exit(f"Arquivo nao encontrado: {caminho}")

    dados = json.loads(caminho.read_text(encoding="utf-8"))
    tipo = dados.get("tipo", "manga").lower()
    headers = autenticar()

    if tipo == "manga":
        sincronizar_manga(headers, dados)
    elif tipo == "livro":
        sincronizar_livro(headers, dados)
    else:
        sys.exit(f"Tipo desconhecido: {tipo!r} (use 'manga' ou 'livro').")


if __name__ == "__main__":
    main()
