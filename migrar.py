import sqlite3

def migrar_banco():
    conexao = sqlite3.connect('financas.db')
    cursor = conexao.cursor()

    # ==========================================
    # 1. MIGRAÇÃO DE MÚLTIPLOS USUÁRIOS
    # ==========================================
    tabelas = ['gastos', 'compras', 'reservas']
    
    for tabela in tabelas:
        try:
            # Adiciona a coluna com valor padrão 1 (que é o seu ID de admin)
            cursor.execute(f"ALTER TABLE {tabela} ADD COLUMN usuario_id INTEGER DEFAULT 1")
            print(f"Coluna 'usuario_id' adicionada com sucesso na tabela: {tabela}")
        except sqlite3.OperationalError:
            print(f"A tabela {tabela} já possui a coluna 'usuario_id' ou não precisa de alteração.")
            
    # ==========================================
    # 2. MIGRAÇÃO DO CÉREBRO IA (HIR3)
    # ==========================================
    try:
        # Adiciona a coluna de telefone para vincular o WhatsApp ao usuário
        cursor.execute("ALTER TABLE usuarios ADD COLUMN telefone TEXT;")
        print("Coluna 'telefone' adicionada com sucesso na tabela: usuarios")
    except sqlite3.OperationalError:
        print("A tabela usuarios já possui a coluna 'telefone'.")

    # Atualiza o seu número principal para o usuário Admin (ID 1)
    try:
        cursor.execute("UPDATE usuarios SET telefone = '5586998168447' WHERE id = 1;")
        print("Número de WhatsApp vinculado ao Administrador (ID 1) com sucesso!")
    except Exception as e:
        print(f"Erro ao vincular número do Admin: {e}")

    # Salva todas as alterações no banco
    conexao.commit()
    conexao.close()
    print("Todas as migrações foram concluídas com sucesso!")

if __name__ == '__main__':
    migrar_banco()