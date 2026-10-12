from getpass import getpass

from app.db import get_connection
from app.security import hash_password


def main():
    username = input("Nome do utilizador: ").strip()

    if not username or len(username) > 64:
        raise SystemExit("Nome inválido.")

    password = getpass("Palavra-passe: ")
    confirmation = getpass("Confirma a palavra-passe: ")

    if password != confirmation:
        raise SystemExit("As palavras-passe não coincidem.")

    if len(password) < 12:
        raise SystemExit(
            "Usa uma palavra-passe com pelo menos 12 caracteres."
        )

    password_hash = hash_password(password)

    with get_connection() as conn:
        existing = conn.execute(
            "SELECT 1 FROM users WHERE username = %s",
            (username,),
        ).fetchone()

        if existing:
            raise SystemExit("Esse utilizador já existe.")

        conn.execute(
            """
            INSERT INTO users (username, password_hash, role)
            VALUES (%s, %s, 'user')
            """,
            (username, password_hash),
        )

    print(f"Utilizador '{username}' criado com sucesso.")


if __name__ == "__main__":
    main()
