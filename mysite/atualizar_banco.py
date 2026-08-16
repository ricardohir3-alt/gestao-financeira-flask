import sqlite3

print("Iniciando verificação do banco de dados...")

# Conectando ao banco de dados
conn = sqlite3.connect('/home/Hir3solutions/mysite/financas.db')
cursor = conn.cursor()

# Lista de todas as colunas novas que o sistema precisa
novas_colunas = [
    ("modulos_liberados", "TEXT"),
    ("ativo", "INTEGER DEFAULT 1"),
    ("validade_licenca", "TEXT"),
    ("email", "TEXT"),
    ("ultimo_acesso", "TEXT")
]

# Tenta adicionar cada coluna
for nome_coluna, tipo_coluna in novas_colunas:
    try:
        cursor.execute(f"ALTER TABLE usuarios ADD COLUMN {nome_coluna} {tipo_coluna}")
        print(f"✅ Coluna '{nome_coluna}' adicionada com sucesso!")
    except sqlite3.OperationalError as e:
        # Se a coluna já existir, ele ignora o erro e avisa que está tudo certo
        if "duplicate column name" in str(e).lower():
            print(f"⚡ Coluna '{nome_coluna}' já existe. Tudo certo!")
        else:
            print(f"❌ Erro na coluna '{nome_coluna}': {e}")

conn.commit()
conn.close()

print("\n🚀 Atualização do banco de dados concluída!")