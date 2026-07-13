import os # NOVO: Para ler variáveis de ambiente (esconder a chave secreta)
import requests
import secrets
from hir3_engine import analisar_mensagem_com_hir3
from flask import Flask, render_template, request, redirect, url_for, session, url_for, Response
import sqlite3
from datetime import datetime, timedelta
import pdfplumber
import pytesseract
from PIL import Image
from flask import request, jsonify
import csv
import io
import calendar
from werkzeug.security import generate_password_hash, check_password_hash # criptografar senhas

app = Flask(__name__)
# A chave agora busca do servidor; se não achar (rodando local), usa uma padrão
app.secret_key = os.environ.get('SECRET_KEY', 'chave_super_secreta_rafael_local')

# Configura a duração do "Manter conectado" para 30 dias na nuvem/navegador
app.permanent_session_lifetime = timedelta(minutes=15)

# ==============================================================================
# AREA DE BANCO DE DADOS
# ==============================================================================
def iniciar_banco():
    conexao = sqlite3.connect('financas.db')
    cursor = conexao.cursor()
    # Adicione na inicialização do banco de dados
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS erros_diagnosticados (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            erro_raw TEXT,
            diagnostico TEXT,
            sugestao_correcao TEXT,
            data_criacao DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    # Adicione este bloco junto com a criação das outras tabelas
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS logs_sistema (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            erro_raw TEXT,
            diagnostico TEXT,
            data_criacao DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS gastos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            descricao TEXT NOT NULL,
            categoria TEXT NOT NULL,
            valor REAL NOT NULL,
            quinzena INTEGER NOT NULL,
            status TEXT NOT NULL,
            data TEXT NOT NULL
        )
    ''')
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS reservas (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nome TEXT NOT NULL,
            meta REAL NOT NULL,
            guardado REAL DEFAULT 0
        )
    ''')

    # NOVA TABELA: Usuários e Senhas
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS usuarios (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            usuario TEXT UNIQUE NOT NULL,
            senha TEXT NOT NULL
        )
    ''')
    # Tabela de compras atualizada
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS compras (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            item TEXT NOT NULL,
            comprado INTEGER DEFAULT 0,
            valor REAL DEFAULT 0.0,
            mes TEXT DEFAULT ''
        )
    ''')
    # Tabela de Dívidas de Longo Prazo
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS dividas (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            usuario_id INTEGER,
            descricao TEXT,
            valor_total REAL,
            total_parcelas INTEGER,
            parcelas_pagas INTEGER DEFAULT 0,
            valor_parcela REAL,
            FOREIGN KEY(usuario_id) REFERENCES usuarios(id)
        )
    ''')

    # Cria a tabela de dívidas longas (se ela ainda não existir)
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS dividas (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        usuario_id INTEGER,
        descricao TEXT,
        valor_total REAL,
        total_parcelas INTEGER,
        parcelas_pagas INTEGER,
        valor_parcela REAL,
        status TEXT DEFAULT 'ATIVA'
    )
    ''')

    # === ATUALIZAÇÃO DA TABELA COMPRAS (MANTENDO DADOS ANTIGOS) ===
    try:
        cursor.execute("ALTER TABLE compras ADD COLUMN descricao TEXT")
    except:
        pass
    try:
        cursor.execute("ALTER TABLE compras ADD COLUMN quantidade INTEGER DEFAULT 1")
        cursor.execute("ALTER TABLE compras ADD COLUMN preco REAL DEFAULT 0.0")
        cursor.execute("ALTER TABLE compras ADD COLUMN valor REAL DEFAULT 0.0")
        cursor.execute("ALTER TABLE compras ADD COLUMN mes TEXT DEFAULT ''")
    except:
        pass
    conexao.commit()

    # === TABELA DE METAS ===
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS meta_compras (
            usuario_id INTEGER,
            mes TEXT,
            valor REAL DEFAULT 0.0,
            PRIMARY KEY (usuario_id, mes)
        )
    ''')
    conexao.commit()

    # === ATUALIZAÇÃO DA TABELA DÍVIDAS ===
    try:
        cursor.execute("ALTER TABLE dividas ADD COLUMN status TEXT DEFAULT 'ATIVA'")
    except:
        pass
    conexao.commit()

    # === CRIAÇÃO DO USUÁRIO ADMIN ===
    cursor.execute("SELECT * FROM usuarios WHERE usuario = 'admin'")
    if not cursor.fetchone():
        from werkzeug.security import generate_password_hash
        senha_criptografada = generate_password_hash('123')
        cursor.execute("INSERT INTO usuarios (usuario, senha) VALUES ('admin', ?)", (senha_criptografada,))

    conexao.commit()
    conexao.close()

    # === CORREÇÃO AUTOMÁTICA DE ESQUEMA (RODAR UMA VEZ) ===
    conexao_temp = sqlite3.connect('financas.db')
    cursor_temp = conexao_temp.cursor()

    # Lista de colunas necessárias e seus tipos
    colunas_necessarias = {
        'produto': 'TEXT',
        'quantidade': 'INTEGER DEFAULT 1',
        'preco': 'REAL DEFAULT 0.0',
        'mes': 'TEXT DEFAULT ""'
    }

    for col, tipo in colunas_necessarias.items():
        try:
            # Tenta adicionar a coluna
            cursor_temp.execute(f"ALTER TABLE compras ADD COLUMN {col} {tipo}")
        except sqlite3.OperationalError:
            # Se der erro (coluna já existe), ignora e continua
            pass

    conexao_temp.commit()
    conexao_temp.close()

# ==============================================================================
# ROTA DE GESTÃO DE USUÁRIOS (PROTEGIDA PARA ADMIN)
# ==============================================================================

@app.route('/usuarios', methods=['GET', 'POST'])
def usuarios():
    # 1. Verifica se está logado
    if 'logado' not in session:
        return redirect(url_for('login'))

    # 2. ID do admin
    admin_id = 1

    # 3. Verifica se é o admin
    if session.get('user_id') != admin_id:
        return render_template('telas/usuarios.html', usuarios=[], logs=[])

    conexao = sqlite3.connect('financas.db')
    conexao.row_factory = sqlite3.Row # Permite acessar colunas por nome
    cursor = conexao.cursor()

    if request.method == 'POST':
        # Cadastrar novo usuário
        if 'cadastrar' in request.form:
            novo_user = request.form.get('usuario')
            nova_senha = generate_password_hash(request.form.get('senha'))
            nova_licenca = request.form.get('licenca')

            try:
                cursor.execute("INSERT INTO usuarios (usuario, senha, licenca) VALUES (?, ?, ?)",
                               (novo_user, nova_senha, nova_licenca))
                conexao.commit()
            except sqlite3.IntegrityError:
                pass

        # Excluir usuário
        elif 'excluir' in request.form:
            id_del = request.form.get('id_usuario')
            cursor.execute("DELETE FROM usuarios WHERE id = ? AND id != 1", (id_del,))
            conexao.commit()

    # LEITURA DE USUÁRIOS
    cursor.execute("SELECT id, usuario, licenca FROM usuarios")
    lista_users = cursor.fetchall()

    # LEITURA DE LOGS (Com tratamento de erro caso a tabela não exista ainda)
    logs = []
    try:
        cursor.execute("SELECT * FROM logs_sistema ORDER BY id DESC LIMIT 50")
        logs = [dict(row) for row in cursor.fetchall()]
    except sqlite3.OperationalError:
        # Se a tabela não existir, retorna lista vazia
        logs = []

    conexao.close()

    # Enviamos 'usuarios' e 'logs' para o template
    return render_template('telas/usuarios.html', usuarios=lista_users, logs=logs)

# ==============================================================================
# ROTA DE GESTÃO DE LICENÇAS (ADMIN)
# ==============================================================================

@app.route('/licencas', methods=['GET', 'POST'])
def licencas():
    if 'logado' not in session or session.get('user_id') != 1:
        return "Acesso negado: Apenas o administrador pode gerenciar licenças.", 403

    conexao = sqlite3.connect('financas.db')
    conexao.row_factory = sqlite3.Row
    cursor = conexao.cursor()

    if request.method == 'POST':
        id_usuario = request.form.get('id_usuario')
        nova_licenca = request.form.get('nova_licenca')
        # Capturando do form no plural
        valor_raw = request.form.get('valor_licencas', '0')

        try:
            novo_valor = float(str(valor_raw).replace(',', '.'))
        except ValueError:
            novo_valor = 0.00

        # Salvando no banco no plural
        cursor.execute("UPDATE usuarios SET licenca = ?, valor_licencas = ? WHERE id = ?", (nova_licenca, novo_valor, id_usuario))
        conexao.commit()
        conexao.close() # Fechar conexão antes do redirect
        return redirect(url_for('licencas'))

    cursor.execute("SELECT COUNT(*) as total FROM usuarios")
    total_usuarios = cursor.fetchone()['total']

    # Buscando do banco no plural
    cursor.execute("SELECT id, usuario, licenca, valor_licencas FROM usuarios WHERE id != 1")
    lista_usuarios = cursor.fetchall()

    conexao.close()

    # A variável 'versao_atual' não é mais necessária aqui, pois o
    # @app.context_processor já a injeta automaticamente em todos os templates.

    return render_template('telas/licencas.html',
                           total_usuarios=total_usuarios,
                           usuarios=lista_usuarios)

# ==============================================================================
# ROTA DE LOGIN E LOGOULT (SALVA O ID DO USUÁRIO NA SESSÃO E VERIFICA LICENÇA)
# ==============================================================================

@app.route('/login', methods=['GET', 'POST'])
def login():
    erro = None
    sucesso = request.args.get('sucesso')

    if request.method == 'POST':
        usuario = request.form.get('usuario')
        senha_digitada = request.form.get('senha')
        manter_conectado = request.form.get('manter_conectado')

        conexao = sqlite3.connect('financas.db')
        # ATUALIZAÇÃO: Permite acessar as colunas pelo nome (ex: usuario_banco['licenca'])
        # sem quebrar a busca pelos números de índice [0] e [2] que você já utiliza
        conexao.row_factory = sqlite3.Row
        cursor = conexao.cursor()

        # BUSCAMOS O REGISTRO DO USUÁRIO
        # ATUALIZADO: Ignorando maiúsculas/minúsculas usando LOWER()
        cursor.execute("SELECT * FROM usuarios WHERE LOWER(usuario) = LOWER(?)", (usuario,))
        usuario_banco = cursor.fetchone()
        conexao.close()

        # O índice [2] é a senha, o índice [0] é o ID do usuário na tabela
        if usuario_banco and check_password_hash(usuario_banco[2], senha_digitada):

            # --- NOVA REGRA DE BLOQUEIO AQUI ---
            # Verifica se a licença do usuário está bloqueada, inativa ou vencida (ignorando o Admin, ID 1)
            if usuario_banco['licenca'] in ['Bloqueada', 'Inativa', 'Vencida'] and usuario_banco[0] != 1:
                erro = "Acesso Negado: Sua licença está inativa ou bloqueada. Contate o administrador."
                return render_template('login.html', erro=erro, sucesso=sucesso)
            # -----------------------------------

            session['logado'] = True

            # Salvamos o ID para filtrar os dados por usuário depois
            session['user_id'] = usuario_banco[0]

            # Salvamos o nome do usuário para o Avatar no topo da tela
            session['usuario'] = usuario_banco[1]

            # ATUALIZAÇÃO: Define se é Admin (True se o ID for 1, False se for outro)
            session['is_admin'] = (usuario_banco[0] == 1)

            if manter_conectado:
                session.permanent = True
            else:
                session.permanent = False

            return redirect(url_for('home'))
        else:
            erro = "Usuário ou senha inválidos!"

    return render_template('login.html', erro=erro, sucesso=sucesso)

@app.route('/logout')
def logout():
    session.pop('logado', None)
    return redirect(url_for('login'))

# --- NOVA ROTA: REDEFINIÇÃO DE SENHA CRIPTOGRAFADA ---
@app.route('/recuperar', methods=['GET', 'POST'])
def recuperar():
    erro = None
    if request.method == 'POST':
        usuario = request.form.get('usuario')
        nova_senha = request.form.get('nova_senha')

        conexao = sqlite3.connect('financas.db')
        cursor = conexao.cursor()

        # Verifica se o usuário digitado realmente existe no banco
        cursor.execute('SELECT * FROM usuarios WHERE usuario = ?', (usuario,))
        if cursor.fetchone():
            # Criptografa a nova senha antes de salvar
            nova_senha_hash = generate_password_hash(nova_senha)
            cursor.execute('UPDATE usuarios SET senha = ? WHERE usuario = ?', (nova_senha_hash, usuario))
            conexao.commit()
            conexao.close()
            # Redireciona para o login exibindo o aviso de sucesso
            return redirect(url_for('login', sucesso="Senha redefinida com sucesso! Use suas novas credenciais."))
        else:
            erro = "Usuário não encontrado no sistema!"
            conexao.close()

    return render_template('telas/recuperar.html', erro=erro)
# ==============================================================================
# MEU PERFIL
# ==============================================================================

@app.route('/perfil', methods=['GET', 'POST'])
def perfil():
    if 'logado' not in session: return redirect(url_for('login'))

    user_id = session['user_id']
    conexao = sqlite3.connect('financas.db')
    cursor = conexao.cursor()

    if request.method == 'POST':
        # Aqui no futuro podemos processar a atualização de senha ou nome
        pass

    cursor.execute("SELECT usuario FROM usuarios WHERE id = ?", (user_id,))
    usuario = cursor.fetchone()
    conexao.close()

    nome_usuario = usuario[0] if usuario else session.get('usuario', '')

    return render_template('perfil.html', nome_usuario=nome_usuario)

# ==============================================================================
# ROTA DE ATUALIZAÇÕES (CHANGELOG)
# ==============================================================================

@app.route('/atualizacoes')
def atualizacoes():
    if 'logado' not in session:
        return redirect(url_for('login'))
    return render_template('telas/atualizacoes.html')

@app.route('/renda', methods=['GET', 'POST'])
def renda():
    if 'logado' not in session:
        return redirect(url_for('login'))

    user_id = session.get('user_id') # Pega o ID de quem está logado

    conexao = sqlite3.connect('financas.db')
    conexao.row_factory = sqlite3.Row
    cursor = conexao.cursor()

    if request.method == 'POST':
        valor_raw = request.form.get('renda', '0')

        try:
            # Trata o valor substituindo vírgula por ponto para não dar erro
            nova_renda = float(str(valor_raw).replace(',', '.'))
        except ValueError:
            nova_renda = 0.00

        # MUDANÇA PRINCIPAL: Salva o valor no banco de dados APENAS para este usuário
        cursor.execute("UPDATE usuarios SET renda = ? WHERE id = ?", (nova_renda, user_id))
        conexao.commit()
        conexao.close()

        # Limpa qualquer valor antigo que estivesse na memória temporária do navegador
        session.pop('renda', None)

        return redirect(url_for('home'))

    # Se for apenas para abrir a tela (GET), busca o valor real no banco
    cursor.execute("SELECT renda FROM usuarios WHERE id = ?", (user_id,))
    resultado = cursor.fetchone()
    conexao.close()

    # Verifica se tem valor salvo, caso contrário exibe 0.00
    renda_atual = resultado['renda'] if resultado and resultado['renda'] is not None else 0.00

    return render_template('telas/renda.html', renda_bruta=renda_atual)

# --- AJUSTE NA FUNÇÃO DE CONEXÃO (ADICIONE ISSO NO SEU ARQUIVO) ---
def get_db_connection():
    conn = sqlite3.connect('financas.db')
    conn.row_factory = sqlite3.Row  # <--- ESSENCIAL PARA O g.descricao funcionar
    return conn

# ==============================================================================
# UPLOAD DE ARQUIVOS
# ==============================================================================

@app.route('/upload_extrato', methods=['POST'])
def processar_extrato_pdf():
    # 1. Recebe o arquivo PDF enviado pela tela do sistema
    arquivo_pdf = request.files.get('extrato')

    if not arquivo_pdf:
        return jsonify({"erro": "Nenhum PDF encontrado."}), 400

    texto_completo = ""

    # 2. Abre o PDF diretamente da memória (sem precisar salvar no disco)
    with pdfplumber.open(arquivo_pdf) as pdf:
        # 3. Passa por todas as páginas do documento
        for pagina in pdf.pages:
            # Extrai todo o texto da página atual
            texto_da_pagina = pagina.extract_text()

            if texto_da_pagina:
                texto_completo += texto_da_pagina + "\n"

    # =========================================================
    # 4. O Pulo do Gato: Mandar o 'texto_completo' para o Gemini
    # =========================================================

    prompt = f"""
    Você é um assistente financeiro. Leia o texto de extrato bancário abaixo.
    Retorne apenas um formato JSON com uma lista contendo: Data, Descrição e Valor.
    Texto do Extrato:
    {texto_completo}
    """

    # transacoes_json = gemini.gerar_resposta(prompt)

    # 5. Manda o resultado processado de volta para a sua tela HTML
    return jsonify({"status": "sucesso", "dados_extraidos": texto_completo})


@app.route('/upload_comprovante', methods=['POST'])
def processar_comprovante_imagem():
    # 1. Recebe a imagem (print/foto) enviada pela nova tela do sistema
    arquivo_img = request.files.get('comprovante')

    if not arquivo_img:
        return jsonify({"erro": "Nenhuma imagem encontrada."}), 400

    # 2. Abre a imagem diretamente da memória usando a biblioteca Pillow (PIL)
    imagem = Image.open(arquivo_img)

    # 3. O Pulo do Gato do OCR: Lê os pixels da imagem e converte em texto!
    texto_completo = pytesseract.image_to_string(imagem)

    # =========================================================
    # 4. Manda o 'texto_completo' (agora extraído da imagem) para o Gemini
    # =========================================================

    prompt = f"""
    Você é um assistente financeiro. Leia o texto extraído de um comprovante Pix/Boleto abaixo.
    Identifique e retorne apenas um formato JSON com uma lista contendo: Data do pagamento, Descrição (Para quem foi o Pix ou nome do Boleto) e Valor.
    Texto do Comprovante:
    {texto_completo}
    """

    # transacoes_json = gemini.gerar_resposta(prompt)

    # 5. Retorna para o HTML exatamente no mesmo formato do PDF
    return jsonify({"status": "sucesso", "dados_extraidos": texto_completo})

# ==============================================================================
# NOVO GASTO
# ==============================================================================

@app.route('/novo_gasto', methods=['GET', 'POST'])
def novo_gasto():
    user_id = session.get('user_id')
    if not user_id:
        return redirect(url_for('login'))

    if request.method == 'POST':
        descricao = request.form.get('descricao')
        valor = float(request.form.get('valor', '0').replace(',', '.'))
        categoria = request.form.get('categoria')
        data = request.form.get('data_gasto') or request.form.get('data')

        quinzena = request.form.get('quinzena')
        quinzena = int(quinzena) if quinzena else 0
        status = request.form.get('status', 'PAGO')

        conexao = sqlite3.connect('financas.db')
        cursor = conexao.cursor()

        cursor.execute('''
            INSERT INTO gastos (usuario_id, descricao, valor, categoria, data, quinzena, status)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        ''', (user_id, descricao, valor, categoria, data, quinzena, status))

        conexao.commit()
        conexao.close()
        return redirect(url_for('home'))

    return render_template('telas/novo_gasto.html')

@app.route('/editar_gasto/<int:id>', methods=['GET', 'POST'])
def editar_gasto(id):
    if 'user_id' not in session:
        return redirect(url_for('login'))

    user_id = session['user_id']
    conn = get_db_connection()
    cursor = conn.cursor()

    if request.method == 'POST':
        descricao = request.form['descricao']
        data = request.form['data_gasto'] # Capture o valor do input
        valor = request.form['valor']
        categoria = request.form['categoria']
        quinzena = request.form['quinzena']
        status = request.form['status']

        # CORREÇÃO: Mudei para 'data' para coincidir com o banco
        cursor.execute("""
            UPDATE gastos
            SET descricao=?, data=?, valor=?, categoria=?, quinzena=?, status=?
            WHERE id=? AND usuario_id=?
        """, (descricao, data, valor, categoria, quinzena, status, id, user_id))

        conn.commit()
        conn.close()
        return redirect('/')

    # GET: Busca o gasto atual
    cursor.execute("SELECT * FROM gastos WHERE id=? AND usuario_id=?", (id, user_id))
    gasto = cursor.fetchone()
    conn.close()

    if not gasto:
        return "Gasto não encontrado ou sem permissão", 404

    return render_template('telas/novo_gasto.html', gasto=gasto)

@app.route('/excluir_gasto/<int:id>', methods=['POST'])
def excluir_gasto(id):
    if 'logado' not in session:
        return redirect(url_for('login'))

    user_id = session['user_id']
    conexao = sqlite3.connect('financas.db')
    cursor = conexao.cursor()

    try:
        # Segurança: Garante que o gasto pertence ao usuário ativo antes de deletar
        cursor.execute("DELETE FROM gastos WHERE id = ? AND usuario_id = ?", (id, user_id))
        conexao.commit()
    except Exception as e:
        print(f"Erro ao excluir gasto: {e}")
    finally:
        conexao.close()

    # Captura o mês que estava filtrado para não perder a navegação do usuário
    mes_filtro = request.form.get('mes_filtro')
    if mes_filtro:
        return redirect(url_for('home', mes=mes_filtro))

    return redirect(url_for('home'))

@app.route('/duplicar', methods=['GET', 'POST'])
def duplicar():
    if 'logado' not in session:
        return redirect(url_for('login'))

    user_id = session['user_id'] # Captura o usuário logado

    if request.method == 'POST':
        mes_origem = request.form.get('mes_origem')
        mes_destino = request.form.get('mes_destino')

        if mes_origem and mes_destino:
            conexao = sqlite3.connect('financas.db')
            conexao.row_factory = sqlite3.Row
            cursor = conexao.cursor()

            # CORREÇÃO: Filtramos apenas gastos do usuário logado
            cursor.execute('SELECT * FROM gastos WHERE data LIKE ? AND usuario_id = ?',
                           (mes_origem + '%', user_id))
            gastos_origem = cursor.fetchall()

            ano_dest, mes_dest = map(int, mes_destino.split('-'))

            for gasto in gastos_origem:
                dia_origem = int(gasto['data'][8:10])
                ultimo_dia_mes_dest = calendar.monthrange(ano_dest, mes_dest)[1]
                dia_dest = min(dia_origem, ultimo_dia_mes_dest)
                nova_data = f"{ano_dest:04d}-{mes_dest:02d}-{dia_dest:02d}"

                # CORREÇÃO: Incluímos o usuario_id no novo insert
                cursor.execute('''
                    INSERT INTO gastos (descricao, categoria, valor, quinzena, status, data, usuario_id)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                ''', (gasto['descricao'], gasto['categoria'], gasto['valor'],
                      gasto['quinzena'], 'PENDENTE', nova_data, user_id))

            conexao.commit()
            conexao.close()
            return redirect(url_for('home', mes=mes_destino))

    return render_template('telas/duplicar.html')

# ==============================================================================
# ROTA DE DIVIDAS
# ==============================================================================

@app.route('/dividas', methods=['GET'])
def dividas():
    user_id = session.get('user_id')
    if not user_id:
        return redirect(url_for('login'))

    conexao = sqlite3.connect('financas.db')
    conexao.row_factory = sqlite3.Row
    cursor = conexao.cursor()

    # Busca todas as dívidas para listar nos cards da nova interface
    cursor.execute("SELECT * FROM dividas WHERE usuario_id = ? ORDER BY id DESC", (user_id,))
    lista_dividas = cursor.fetchall()
    conexao.close()

    # Renderiza a nova tela única enviando a lista de contratos
    return render_template('telas/gestao_dividas.html', dividas=lista_dividas)


@app.route('/nova_divida', methods=['GET', 'POST'])
def nova_divida():
    user_id = session.get('user_id')
    if not user_id:
        return redirect(url_for('login'))

    if request.method == 'POST':
        descricao = request.form.get('descricao')
        valor_parcela = float(request.form.get('valor', '0').replace(',', '.'))
        valor_total_divida = float(request.form.get('valor_total_divida', '0').replace(',', '.'))
        total_parcelas = int(request.form.get('total_parcelas', '1'))

        # ATUALIZAÇÃO: Capturando a categoria (dinâmica) e data (opcional) de forma segura
        categoria = request.form.get('categoria', 'Dívida / Empréstimo')
        data_gasto = request.form.get('data_gasto', '') # Se não preencher, o Python entende como string vazia e não quebra

        conexao = sqlite3.connect('financas.db')
        cursor = conexao.cursor()

        # Nota: As variáveis 'categoria' e 'data_gasto' foram capturadas acima.
        # Caso o seu banco de dados possua essas colunas, basta adicioná-las no INSERT abaixo.
        cursor.execute('''
            INSERT INTO dividas (usuario_id, descricao, valor_total, total_parcelas, parcelas_pagas, valor_parcela, status)
            VALUES (?, ?, ?, ?, 0, ?, 'ATIVA')
        ''', (user_id, descricao, valor_total_divida, total_parcelas, valor_parcela))

        conexao.commit()
        conexao.close()

        return redirect('/dividas')

    # Se acessar por GET direto, redireciona para a tela principal
    return redirect('/dividas')


@app.route('/editar_divida/<int:id>', methods=['GET', 'POST'])
def editar_divida(id):
    user_id = session.get('user_id')
    if not user_id:
        return redirect(url_for('login'))

    conexao = sqlite3.connect('financas.db')
    conexao.row_factory = sqlite3.Row
    cursor = conexao.cursor()

    if request.method == 'POST':
        descricao = request.form.get('descricao')
        valor_total = float(request.form.get('valor_total', '0').replace(',', '.'))
        total_parcelas = int(request.form.get('total_parcelas', '1'))
        valor_parcela = float(request.form.get('valor_parcela', '0').replace(',', '.'))
        parcelas_pagas = int(request.form.get('parcelas_pagas', '0'))

        cursor.execute('''
            UPDATE dividas
            SET descricao = ?, valor_total = ?, total_parcelas = ?, valor_parcela = ?, parcelas_pagas = ?
            WHERE id = ? AND usuario_id = ?
        ''', (descricao, valor_total, total_parcelas, valor_parcela, parcelas_pagas, id, user_id))

        conexao.commit()
        conexao.close()
        return redirect('/dividas')

    # Se for GET, busca os dados da dívida e manda para a TELA ÚNICA
    cursor.execute("SELECT * FROM dividas WHERE id = ? AND usuario_id = ?", (id, user_id))
    divida = cursor.fetchone()
    conexao.close()

    return render_template('telas/gestao_dividas.html', divida=divida)


@app.route('/pagar_parcela/<int:id>', methods=['POST'])
def pagar_parcela(id):
    user_id = session.get('user_id')
    if not user_id:
        return redirect(url_for('login'))

    conexao = sqlite3.connect('financas.db')
    cursor = conexao.cursor()

    cursor.execute("SELECT parcelas_pagas, total_parcelas FROM dividas WHERE id = ? AND usuario_id = ?", (id, user_id))
    divida = cursor.fetchone()

    if divida:
        parcelas_pagas = divida[0]
        total_parcelas = divida[1]

        if parcelas_pagas < total_parcelas:
            nova_quantidade = parcelas_pagas + 1
            status = 'CONCLUIDA' if nova_quantidade == total_parcelas else 'ATIVA'

            cursor.execute("UPDATE dividas SET parcelas_pagas = ?, status = ? WHERE id = ?", (nova_quantidade, status, id))
            conexao.commit()

    conexao.close()
    return redirect('/dividas')


@app.route('/quitar_divida/<int:id>', methods=['POST'])
def quitar_divida(id):
    user_id = session.get('user_id')
    conexao = sqlite3.connect('financas.db')
    cursor = conexao.cursor()

    cursor.execute("UPDATE dividas SET parcelas_pagas = total_parcelas, status = 'CONCLUIDA' WHERE id = ? AND usuario_id = ?", (id, user_id))

    conexao.commit()
    conexao.close()
    return redirect('/dividas')


@app.route('/excluir_divida/<int:id>', methods=['POST'])
def excluir_divida(id):
    user_id = session.get('user_id')
    conexao = sqlite3.connect('financas.db')
    cursor = conexao.cursor()

    cursor.execute("DELETE FROM dividas WHERE id = ? AND usuario_id = ?", (id, user_id))

    conexao.commit()
    conexao.close()
    return redirect('/dividas')

# ==============================================================================
# ROTA RESERVAS E OBJETIVOS
# ==============================================================================

@app.route('/reservas', methods=['GET', 'POST'])
def reservas():
    if 'logado' not in session:
        return redirect(url_for('login'))

    user_id = session['user_id']
    conexao = sqlite3.connect('financas.db')
    conexao.row_factory = sqlite3.Row
    cursor = conexao.cursor()

    if request.method == 'POST':
        if 'novo_objetivo' in request.form:
            nome = request.form.get('nome')
            try:
                # ATUALIZAÇÃO: Replace adicionado para aceitar vírgulas
                meta = float(request.form.get('meta', '0').replace(',', '.'))
                # CORREÇÃO: Inserindo o usuario_id
                cursor.execute('INSERT INTO reservas (nome, meta, guardado, usuario_id) VALUES (?, ?, 0, ?)', (nome, meta, user_id))
                conexao.commit()
            except ValueError:
                pass

        elif 'adicionar_saldo' in request.form:
            id_reserva = request.form.get('id_reserva')
            try:
                # ATUALIZAÇÃO: Replace adicionado para aceitar vírgulas
                valor_adicionar = float(request.form.get('valor_adicionar', '0').replace(',', '.'))
                # CORREÇÃO: Adicionado filtro 'AND usuario_id = ?' para segurança
                cursor.execute('UPDATE reservas SET guardado = guardado + ? WHERE id = ? AND usuario_id = ?', (valor_adicionar, id_reserva, user_id))
                conexao.commit()
            except ValueError:
                pass

        return redirect(url_for('reservas'))

    # CORREÇÃO: Filtrando o SELECT pelo usuario_id
    cursor.execute('SELECT * FROM reservas WHERE usuario_id = ? ORDER BY id DESC', (user_id,))
    lista_reservas = cursor.fetchall()
    conexao.close()

    return render_template('telas/reservas.html', reservas=lista_reservas)

@app.route('/editar_reserva/<int:id>', methods=['POST'])
def editar_reserva(id):
    if 'logado' not in session:
        return redirect(url_for('login'))

    user_id = session['user_id']
    nome = request.form.get('nome')

    try:
        # Pega a nova meta e blinda contra vírgulas (ex: 5000,00 vira 5000.00)
        meta = float(request.form.get('meta', '0').replace(',', '.'))

        conexao = sqlite3.connect('financas.db')
        cursor = conexao.cursor()

        # O filtro 'AND usuario_id = ?' garante que ninguém edite a meta de outra pessoa
        cursor.execute('''
            UPDATE reservas
            SET nome = ?, meta = ?
            WHERE id = ? AND usuario_id = ?
        ''', (nome, meta, id, user_id))

        conexao.commit()
        conexao.close()
    except ValueError:
        pass

    return redirect('/reservas')

@app.route('/excluir_reserva/<int:id>', methods=['POST'])
def excluir_reserva(id):
    if 'logado' not in session:
        return redirect(url_for('login'))

    user_id = session['user_id']

    conexao = sqlite3.connect('financas.db')
    cursor = conexao.cursor()

    # Exclui a meta (Apenas se pertencer ao usuário logado)
    cursor.execute("DELETE FROM reservas WHERE id = ? AND usuario_id = ?", (id, user_id))

    conexao.commit()
    conexao.close()

    return redirect('/reservas')

@app.route('/atualizar_status/<int:id_gasto>', methods=['POST'])
def atualizar_status(id_gasto):
    if 'logado' not in session:
        return redirect(url_for('login'))

    user_id = session['user_id']
    mes_filtro = request.args.get('mes')
    conexao = sqlite3.connect('financas.db')
    cursor = conexao.cursor()

    # CORREÇÃO: Adicionado filtro 'AND usuario_id = ?' para buscar apenas o gasto do usuário logado
    cursor.execute('SELECT status FROM gastos WHERE id = ? AND usuario_id = ?', (id_gasto, user_id))
    resultado = cursor.fetchone()

    if resultado:
        status_atual = resultado[0]
        novo_status = 'PAGO' if status_atual == 'PENDENTE' else 'PENDENTE'

        # CORREÇÃO: Adicionado filtro 'AND usuario_id = ?' na atualização
        cursor.execute('UPDATE gastos SET status = ? WHERE id = ? AND usuario_id = ?',
                       (novo_status, id_gasto, user_id))
        conexao.commit()

    conexao.close()

    return redirect(url_for('home', mes=mes_filtro))

# ==============================================================================
# ROTA DA CALCULADORA
# ==============================================================================

@app.route('/calculadora')
def calculadora():
    if 'logado' not in session:
        return redirect(url_for('login'))
    return render_template('telas/calculadora.html')

# ==============================================================================
# ROTA DA LISTA DE COMPRAS (AGORA COM EDIÇÃO IN-LINE)
# ==============================================================================

def parse_valor(texto, padrao=0.0):
    """Converte string de valor BR para float com segurança."""
    if not texto:
        return padrao
    try:
        texto = str(texto).strip()
        if ',' in texto:
            texto = texto.replace('.', '').replace(',', '.')
        return float(texto)
    except (ValueError, AttributeError):
        return padrao

@app.route('/compras', methods=['GET', 'POST'])
def compras():
    user_id = session.get('user_id')
    if not user_id:
        return redirect(url_for('login'))

    mes_atual = datetime.now().strftime('%Y-%m')

    conexao = sqlite3.connect('financas.db')
    conexao.row_factory = sqlite3.Row
    cursor = conexao.cursor()

    # Criação das tabelas
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS lista_compras (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            usuario_id INTEGER,
            descricao TEXT,
            quantidade INTEGER DEFAULT 1,
            preco REAL DEFAULT 0.0,
            total_item REAL,
            mes TEXT
        )
    ''')
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS meta_compras (
            usuario_id INTEGER,
            mes TEXT,
            valor REAL DEFAULT 0.0,
            PRIMARY KEY (usuario_id, mes)
        )
    ''')
    conexao.commit()

    if request.method == 'POST':
        if 'valor_meta' in request.form:
            valor_meta = parse_valor(request.form.get('valor_meta'))
            cursor.execute('''
                INSERT INTO meta_compras (usuario_id, mes, valor)
                VALUES (?, ?, ?)
                ON CONFLICT(usuario_id, mes) DO UPDATE SET valor = excluded.valor
            ''', (user_id, mes_atual, valor_meta))
            conexao.commit()
            conexao.close()
            return redirect('/compras')

        elif 'descricao' in request.form:
            descricao = request.form.get('descricao', '').strip()
            quantidade = int(request.form.get('quantidade', 1))
            preco = parse_valor(request.form.get('preco'))
            total_item = quantidade * preco

            if descricao:
                cursor.execute('''
                    INSERT INTO lista_compras (usuario_id, descricao, quantidade, preco, total_item, mes)
                    VALUES (?, ?, ?, ?, ?, ?)
                ''', (user_id, descricao, quantidade, preco, total_item, mes_atual))
                conexao.commit()
            conexao.close()
            return redirect('/compras')

    # LEITURA E PROCESSAMENTO BLINDADO
    cursor.execute("SELECT * FROM lista_compras WHERE usuario_id = ? AND mes = ?", (user_id, mes_atual))
    itens_bd = cursor.fetchall()

    itens = []
    total_lista = 0.0

    for row in itens_bd:
        d = dict(row)
        # LÓGICA DE BLINDAGEM: Se 'total_item' não existir ou for nulo, calcula agora
        qtd = d.get('quantidade') or 1
        preco = d.get('preco') or 0.0
        d['total_item'] = d.get('total_item') if d.get('total_item') is not None else (qtd * preco)

        total_lista += d['total_item']
        itens.append(d)

    cursor.execute("SELECT valor FROM meta_compras WHERE usuario_id = ? AND mes = ?", (user_id, mes_atual))
    meta_row = cursor.fetchone()
    meta_valor = meta_row['valor'] if meta_row else 0.0

    saldo_meta = meta_valor - total_lista
    porcentagem_meta = round((total_lista / meta_valor * 100), 1) if meta_valor > 0 else 0

    conexao.close()

    return render_template('telas/compras.html',
                           itens=itens,
                           total_lista=total_lista,
                           meta_valor=meta_valor,
                           saldo_meta=saldo_meta,
                           porcentagem_meta=porcentagem_meta)

@app.route('/exportar_compras_csv')
def exportar_compras_csv():
    user_id = session.get('user_id')
    if not user_id: return redirect(url_for('login'))
    mes_atual = datetime.now().strftime('%Y-%m')

    conexao = sqlite3.connect('financas.db')
    cursor = conexao.cursor()
    cursor.execute("SELECT descricao, quantidade, preco FROM lista_compras WHERE usuario_id = ? AND mes = ?", (user_id, mes_atual))
    itens = cursor.fetchall()
    conexao.close()

    output = io.StringIO()
    output.write('\ufeff')
    writer = csv.writer(output, delimiter=';')
    writer.writerow(['Descricao', 'Quantidade', 'Preco'])
    for item in itens:
        preco_br = str(item[2]).replace('.', ',')
        writer.writerow([item[0], item[1], preco_br])

    output.seek(0)
    return Response(output.getvalue(), mimetype="text/csv; charset=utf-8",
                    headers={"Content-Disposition": "attachment;filename=lista_compras.csv"})

@app.route('/importar_compras_csv', methods=['POST'])
def importar_compras_csv():
    user_id = session.get('user_id')
    if not user_id: return redirect(url_for('login'))
    mes_atual = datetime.now().strftime('%Y-%m')
    file = request.files.get('arquivo_csv')

    if file:
        try: conteudo = file.stream.read().decode("utf-8-sig")
        except: conteudo = file.stream.read().decode("latin-1")

        stream = io.StringIO(conteudo, newline=None)
        reader = csv.reader(stream, delimiter=';')
        next(reader, None)

        conexao = sqlite3.connect('financas.db')
        cursor = conexao.cursor()
        for row in reader:
            if len(row) >= 3:
                try:
                    descricao = row[0].strip()
                    qtd = int(row[1])
                    preco = parse_valor(row[2])
                    if descricao:
                        cursor.execute("INSERT INTO lista_compras (usuario_id, descricao, quantidade, preco, total_item, mes) VALUES (?, ?, ?, ?, ?, ?)",
                                       (user_id, descricao, qtd, preco, qtd * preco, mes_atual))
                except: continue
        conexao.commit()
        conexao.close()
    return redirect('/compras')

@app.route('/excluir_compra/<int:id>', methods=['POST'])
def excluir_compra(id):
    user_id = session.get('user_id')
    if not user_id: return redirect(url_for('login'))
    conexao = sqlite3.connect('financas.db')
    cursor = conexao.cursor()
    cursor.execute("DELETE FROM lista_compras WHERE id = ? AND usuario_id = ?", (id, user_id))
    conexao.commit()
    conexao.close()
    return redirect('/compras')

# ==============================================================================
# DASHBOARD --------------------------------------------------------------------
# ==============================================================================
@app.route('/', methods=['GET'])
def home():
    if 'logado' not in session:
        return redirect(url_for('login'))

    user_id = session['user_id'] # Captura o usuário logado

    # Abrimos a conexão com o banco mais cedo para poder buscar a renda do usuário
    conexao = sqlite3.connect('financas.db')
    conexao.row_factory = sqlite3.Row
    cursor = conexao.cursor()

    # --- ATUALIZAÇÃO CRÍTICA AQUI: Busca a renda fixa e individual no banco de dados ---
    cursor.execute("SELECT renda FROM usuarios WHERE id = ?", (user_id,))
    resultado_usuario = cursor.fetchone()

    # Garante que a renda seja tratada como NÚMERO (float), vinda do banco, e não mais da sessão temporária
    try:
        if resultado_usuario and resultado_usuario['renda'] is not None:
            renda_atual = float(resultado_usuario['renda'])
        else:
            renda_atual = 0.00
    except (ValueError, TypeError):
        renda_atual = 0.00
    # -----------------------------------------------------------------------------------

    mes_atual = datetime.now().strftime('%Y-%m')
    mes_filtro = request.args.get('mes', mes_atual)

    cursor.execute('SELECT * FROM gastos WHERE data LIKE ? AND usuario_id = ? ORDER BY data DESC',
                   (mes_filtro + '%', user_id))
    lista_gastos = cursor.fetchall()

    # CORREÇÃO 2: Força o valor de cada gasto a ser lido como float na hora de somar
    total_gastos = sum(float(gasto['valor']) for gasto in lista_gastos)

    # 1. Gráfico de Ondas (Agrupado por dia via Banco de Dados)
    cursor.execute('''
        SELECT substr(data, 9, 2) as dia, SUM(valor) as total
        FROM gastos
        WHERE data LIKE ? AND usuario_id = ?
        GROUP BY dia ORDER BY dia
    ''', (mes_filtro + '%', user_id))

    dados_grafico = cursor.fetchall()
    dias_grafico = [row['dia'] for row in dados_grafico]
    # Força a leitura do gráfico em float também
    valores_grafico = [float(row['total']) for row in dados_grafico]

    conexao.close()

    # --- CÁLCULOS DO DASHBOARD ---

    # 2. Gráfico Donut (Agrupado por Categoria via Python - Muito rápido!)
    categorias_dict = {}
    for g in lista_gastos:
        cat = g['categoria']
        # Converte para float na divisão por categorias
        categorias_dict[cat] = categorias_dict.get(cat, 0) + float(g['valor'])

    labels_categorias = list(categorias_dict.keys())
    valores_categorias = list(categorias_dict.values())

    # CORREÇÃO 3: Convertendo a quinzena para string na hora de comparar
    total_q1 = sum(float(g['valor']) for g in lista_gastos if str(g['quinzena']) == '1')
    total_q2 = sum(float(g['valor']) for g in lista_gastos if str(g['quinzena']) == '2')
    perc_q1 = round((total_q1 / total_gastos * 100), 1) if total_gastos > 0 else 0
    perc_q2 = round((total_q2 / total_gastos * 100), 1) if total_gastos > 0 else 0

    total_pago = sum(float(g['valor']) for g in lista_gastos if g['status'] == 'PAGO')
    total_pendente = sum(float(g['valor']) for g in lista_gastos if g['status'] == 'PENDENTE')
    perc_pago = round((total_pago / total_gastos * 100), 1) if total_gastos > 0 else 0
    perc_pendente = round((total_pendente / total_gastos * 100), 1) if total_gastos > 0 else 0

    # Ordena o TOP 3 forçando o valor como número, para não ordenar como texto
    top3_gastos = sorted(lista_gastos, key=lambda x: float(x['valor']), reverse=True)[:3]

    # CORREÇÃO 4: O CÁLCULO FINAL DE DEDUÇÃO (Agora ambos são números flutuantes reais)
    disponivel_geral = renda_atual - total_gastos

    # Formatação Final para o Visual (R$)
    renda_formatada = f"{renda_atual:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    gastos_formatado = f"{total_gastos:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    disponivel_formatado = f"{disponivel_geral:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    total_q1_fmt = f"{total_q1:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    total_q2_fmt = f"{total_q2:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    total_pago_fmt = f"{total_pago:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    total_pendente_fmt = f"{total_pendente:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")

    # Retorno Limpo sem Variáveis Duplicadas
    return render_template('index.html',
                           renda_total=renda_formatada,
                           gastos_totais=gastos_formatado,
                           valor_disponivel=disponivel_formatado,
                           gastos=lista_gastos,
                           mes_filtro=mes_filtro,
                           dias_grafico=dias_grafico,
                           valores_grafico=valores_grafico,
                           labels_categorias=labels_categorias,
                           valores_categorias=valores_categorias,
                           perc_q1=perc_q1, perc_q2=perc_q2,
                           total_q1=total_q1_fmt, total_q2=total_q2_fmt,
                           perc_pago=perc_pago, perc_pendente=perc_pendente,
                           total_pago=total_pago_fmt, total_pendente=total_pendente_fmt,
                           top3_gastos=top3_gastos)

# ==============================================================================
# ROTA DE RELATÓRIOS (EXCLUSIVA PREMIUM)
# ==============================================================================

@app.route('/relatorios_avancados')
def relatorios_avancados():
    if 'logado' not in session:
        return redirect(url_for('login'))

    user_id = session.get('user_id')
    mes_atual = datetime.now().strftime('%Y-%m')
    mes_filtro = request.args.get('mes', mes_atual)

    conexao = sqlite3.connect('financas.db')
    conexao.row_factory = sqlite3.Row
    cursor = conexao.cursor()

    # 1. Verifica a licença do usuário atual
    cursor.execute("SELECT licenca FROM usuarios WHERE id = ?", (user_id,))
    user_db = cursor.fetchone()

    # Se não for Premium (e não for o Admin ID 1), barra o acesso
    if user_db and user_db['licenca'] != 'Premium' and user_id != 1:
        conexao.close()
        return render_template('telas/bloqueado.html')

    # 2. Se for Premium, faz todo o processamento de dados!
    cursor.execute('SELECT * FROM gastos WHERE data LIKE ? AND usuario_id = ? ORDER BY data DESC', (mes_filtro + '%', user_id))
    lista_gastos = cursor.fetchall()

    total_gastos = sum(float(g['valor']) for g in lista_gastos)

    # Gráfico de Ondas
    cursor.execute('''SELECT substr(data, 9, 2) as dia, SUM(valor) as total FROM gastos
                      WHERE data LIKE ? AND usuario_id = ? GROUP BY dia ORDER BY dia''', (mes_filtro + '%', user_id))
    dados_grafico = cursor.fetchall()
    dias_grafico = [row['dia'] for row in dados_grafico]
    valores_grafico = [float(row['total']) for row in dados_grafico]

    # ==========================================
    # BUSCA DE DÍVIDAS PARA O RELATÓRIO
    # ==========================================
    cursor.execute("SELECT * FROM dividas WHERE usuario_id = ?", (user_id,))
    dividas_banco = cursor.fetchall()

    lista_dividas_relatorio = []
    for d in dividas_banco:
        divida = dict(d)

        total_p = divida['total_parcelas']
        pagas = divida['parcelas_pagas']
        valor_parc = divida['valor_parcela']

        # Cálculos de amortização e saldo restante
        divida['perc_paga'] = round((pagas / total_p) * 100, 1) if total_p > 0 else 0
        divida['saldo_restante'] = (total_p - pagas) * valor_parc

        lista_dividas_relatorio.append(divida)

        # BUSCA DE RESERVAS PARA O RELATÓRIO
        cursor.execute("SELECT * FROM reservas WHERE usuario_id = ?", (user_id,))
        lista_reservas_relatorio = cursor.fetchall()

    # Fechamos a conexão apenas após buscar as dívidas também
    conexao.close()

    # Cálculos de Categoria (Donut)
    categorias_dict = {}
    for g in lista_gastos:
        cat = g['categoria']
        categorias_dict[cat] = categorias_dict.get(cat, 0) + float(g['valor'])

    # Porcentagens
    total_q1 = sum(float(g['valor']) for g in lista_gastos if str(g['quinzena']) == '1')
    total_q2 = sum(float(g['valor']) for g in lista_gastos if str(g['quinzena']) == '2')
    perc_q1 = round((total_q1 / total_gastos * 100), 1) if total_gastos > 0 else 0
    perc_q2 = round((total_q2 / total_gastos * 100), 1) if total_gastos > 0 else 0

    total_pago = sum(float(g['valor']) for g in lista_gastos if g['status'] == 'PAGO')
    total_pendente = sum(float(g['valor']) for g in lista_gastos if g['status'] == 'PENDENTE')
    perc_pago = round((total_pago / total_gastos * 100), 1) if total_gastos > 0 else 0
    perc_pendente = round((total_pendente / total_gastos * 100), 1) if total_gastos > 0 else 0

    top3_gastos = sorted(lista_gastos, key=lambda x: float(x['valor']), reverse=True)[:3]

    return render_template('telas/relatorios_avancados.html',
                           mes_filtro=mes_filtro,
                           dias_grafico=dias_grafico, valores_grafico=valores_grafico,
                           labels_categorias=list(categorias_dict.keys()), valores_categorias=list(categorias_dict.values()),
                           perc_q1=perc_q1, perc_q2=perc_q2,
                           perc_pago=perc_pago, perc_pendente=perc_pendente,
                           top3_gastos=top3_gastos,
                           dividas=lista_dividas_relatorio, reservas=lista_reservas_relatorio)

# ==============================================================================
# BOOT IA HIR3
# ==============================================================================

from flask import request, jsonify
import json
import sqlite3
import google.generativeai as genai

# ==============================================================================
# CONFIGURAÇÃO DO GOOGLE GEMINI (CÉREBRO DO HIR3)
# ==============================================================================
# Insira sua chave de API gerada no Google AI Studio
genai.configure(api_key="SUA_CHAVE_API_AQUI")

# Usamos o modelo 'flash' pois é focado em velocidade e respostas rápidas (ideal para bots)
modelo_hir3 = genai.GenerativeModel('gemini-1.5-flash')

# O token de verificação da API do WhatsApp
TOKEN_VERIFICACAO = "minhas_financas_secreto_123"

# ==============================================================================
# CÉREBRO DO HIR3 (INTEGRAÇÃO IA)
# ==============================================================================
def analisar_mensagem_com_hir3(texto_usuario):
    # Este é o 'Prompt de Sistema'. Ele programa a personalidade e as regras do hir3.
    prompt = f"""
    Você é o 'hir3', um assistente financeiro de Inteligência Artificial para WhatsApp.
    O usuário vai te enviar uma mensagem e você DEVE extrair as informações e me devolver ÚNICA e EXCLUSIVAMENTE um objeto JSON válido, sem nenhuma formatação Markdown em volta.

    Regras de ação:
    1. Se o usuário relatar um gasto (ex: "comprei um lanche por 20", "gastei 50 no uber"):
       Retorne o JSON: {{"acao": "registrar_gasto", "valor": <float>, "descricao": "<texto resumido>", "categoria": "<adivinhe a categoria: Alimentação, Transporte, Saúde, Habitação, Lazer ou Outros>", "mensagem_hir3": "<Sua resposta amigável e curta confirmando o registro>"}}

    2. Se o usuário perguntar sobre saldo ou pedir resumo:
       Retorne o JSON: {{"acao": "consultar_saldo", "mensagem_hir3": "<Uma frase engraçada e curta avisando que vai calcular o saldo>"}}

    3. Se for qualquer outra coisa (oi, bom dia, dúvida):
       Retorne o JSON: {{"acao": "conversar", "mensagem_hir3": "<Sua resposta carismática como assistente hir3>"}}

    Mensagem do usuário: "{texto_usuario}"
    """

    try:
        # Envia a mensagem para o Gemini
        resposta = modelo_hir3.generate_content(prompt)

        # Limpa o texto caso a IA tente colocar "```json" em volta do código
        texto_limpo = resposta.text.replace('```json', '').replace('```', '').strip()

        # Transforma o texto do Gemini em um dicionário Python real
        dados_ia = json.loads(texto_limpo)
        return dados_ia

    except Exception as e:
        print(f"Falha de conexão com o Gemini: {e}")
        # Se a internet falhar ou a API der erro, o hir3 não quebra, ele avisa:
        return {
            "acao": "conversar",
            "mensagem_hir3": "Ops! Meu cérebro de silício deu uma travada rápida. Pode repetir?"
        }

# ==========================================
# ROTA DO WEBHOOK DO WHATSAPP
# ==========================================
@app.route('/whatsapp-webhook', methods=['GET', 'POST'])
def webhook_whatsapp():

    # 1. VERIFICAÇÃO DE SEGURANÇA (MÉTODO GET)
    if request.method == 'GET':
        mode = request.args.get('hub.mode')
        token = request.args.get('hub.verify_token')
        challenge = request.args.get('hub.challenge')

        if mode and token:
            if mode == 'subscribe' and token == TOKEN_VERIFICACAO:
                print("WEBHOOK VERIFICADO COM SUCESSO!")
                return challenge, 200
            else:
                return 'Token de verificação inválido', 403
        return 'Página de Webhook Ativa', 200

    # 2. RECEBIMENTO E PROCESSAMENTO (MÉTODO POST)
    if request.method == 'POST':
        dados = request.json

        try:
            mensagens = dados.get('entry', [])[0].get('changes', [])[0].get('value', {}).get('messages', [])

            if mensagens:
                mensagem_atual = mensagens[0]
                telefone_remetente = mensagem_atual.get('from')
                texto_recebido = mensagem_atual.get('text', {}).get('body', '').strip()

                print(f"[{telefone_remetente}] enviou: {texto_recebido}")

                # BUSCA SE O NÚMERO EXISTE NO BANCO DE DADOS ANTES DA IA
                conexao = sqlite3.connect('financas.db')
                conexao.row_factory = sqlite3.Row
                cursor = conexao.cursor()

                cursor.execute("SELECT id, usuario FROM usuarios WHERE telefone = ?", (telefone_remetente,))
                usuario_banco = cursor.fetchone()

                # Bloqueio de segurança: Se o número não existir no banco, ele para aqui.
                if not usuario_banco:
                    conexao.close()
                    print(f"Alerta: Número desconhecido tentou interagir ({telefone_remetente})")
                    return jsonify({"status": "recebido"}), 200

                # ----------------------------------------------------
                # O HIR3 ASSUME O COMANDO AQUI (AGORA COM GEMINI)
                # ----------------------------------------------------
                decisao_ia = analisar_mensagem_com_hir3(texto_recebido)
                user_id = usuario_banco['id'] # Pega o ID dinâmico do usuário validado

                # AÇÃO: REGISTRAR GASTO
                if decisao_ia.get('acao') == 'registrar_gasto':
                    cursor.execute('''
                        INSERT INTO gastos (usuario_id, descricao, valor, categoria, status)
                        VALUES (?, ?, ?, ?, 'PAGO')
                    ''', (user_id, decisao_ia['descricao'], float(decisao_ia['valor']), decisao_ia['categoria']))

                    conexao.commit()
                    print(f"hir3 salvou: {decisao_ia['descricao']} - R${decisao_ia['valor']} ({decisao_ia['categoria']})")

                # AÇÃO: RECUPERAR SENHA
                elif decisao_ia.get('acao') == 'recuperar_senha':
                    # Gera uma senha aleatória segura
                    senha_provisoria = f"hir3-{secrets.token_hex(2)}"
                    senha_criptografada = generate_password_hash(senha_provisoria)

                    cursor.execute("UPDATE usuarios SET senha = ? WHERE id = ?", (senha_criptografada, user_id))
                    conexao.commit()

                    # Atualiza o texto de resposta para entregar a nova senha
                    decisao_ia['mensagem_hir3'] = f"🔑 Operação Concluída! Zerei sua senha de acesso. Use a senha temporária abaixo para entrar e altere-a imediatamente no seu perfil:\n\n👉 *{senha_provisoria}*"
                    print(f"hir3 resetou a senha do usuário: {usuario_banco['usuario']}")

                # AÇÃO: CONSULTAR SALDO
                elif decisao_ia.get('acao') == 'consultar_saldo':
                    print("hir3 está consultando o saldo...")

                # Fecha a conexão após executar as ações
                conexao.close()

                # AQUI VOCÊ ENVIA A RESPOSTA DE VOLTA PARA O WHATSAPP
                enviar_whatsapp(telefone_remetente, decisao_ia.get('mensagem_hir3'))
                print(f"Resposta do hir3: {decisao_ia.get('mensagem_hir3')}")
                # ----------------------------------------------------

        except Exception as e:
            print(f"Erro ao processar mensagem com hir3: {e}")

        return jsonify({"status": "recebido"}), 200

# ==============================================================================
# CENTRAL DE LOGS
# ==============================================================================

import google.generativeai

def diagnosticar_erro_com_ia(erro_traceback):
    # Exemplo simples de integração
    prompt = f"Analise este erro de Python Flask e me dê um diagnóstico simples e como corrigir: {erro_traceback}"

    # Aqui você chamaria sua API.
    # Para o exemplo, vamos simular a resposta da IA:
    response = "Diagnóstico: Erro de coluna não encontrada. Sugestão: Rode o comando ALTER TABLE."

    return response

@app.route('/analisar_erro/<int:log_id>', methods=['POST'])
def analisar_erro(log_id):
    # Pega o erro específico da sua central de logs
    erro = "..." # Busca o erro bruto no seu arquivo de log ou banco
    diagnostico = diagnosticar_erro_com_ia(erro)

    # Salva no banco de erros diagnosticados
    # cursor.execute("INSERT INTO erros_diagnosticados ...")
    return redirect('/logs')

# ==============================================================================
# CONFIGURAÇÕES OFICIAIS DA META (WHATSAPP)
# ==============================================================================
# Vamos preencher essas duas variáveis depois de criar o App no Facebook
TOKEN_META = "EAAOvB9xIg9IBR2opZA3LJRZBLiw0pwoZC8Y2HMZC6Kqz0zGVuw3AZAJKrYL1oPBkoumNxq0HvviLtzCfhYWNzExOPw4hjQu1OKOlTNcWEwJOEqZBZBelYZAo7i6JskXfttABzYEZBlV7selq8LxKZBw3SIl0LmIZATfZCrPJwL08Ckl2zQjAdqZCOQR3r5W9oCjsl9FENmeKPuzd9QZC30ZBBCgxHT1LwVHaDGzZBdukZA4KZAeDF2IwiBIBXJaXJyHmKCnrjfrZCvNIQZCMmp5AZCPJFUduIBGZCv"
ID_TELEFONE = "1110613762144660"

def enviar_whatsapp(telefone_destino, texto_mensagem):
    """
    A 'Boca' do hir3: Envia a mensagem de volta para o WhatsApp do usuário.
    """
    # A URL oficial da API do WhatsApp Cloud
    url = f"https://graph.facebook.com/v18.0/{ID_TELEFONE}/messages"

    headers = {
        "Authorization": f"Bearer {TOKEN_META}",
        "Content-Type": "application/json"
    }

    # O pacote JSON no formato exato que a Meta exige
    payload = {
        "messaging_product": "whatsapp",
        "recipient_type": "individual",
        "to": telefone_destino,
        "type": "text",
        "text": {
            "preview_url": False,
            "body": texto_mensagem
        }
    }

    try:
        resposta = requests.post(url, headers=headers, json=payload)
        if resposta.status_code == 200:
            print(f"✅ Mensagem enviada com sucesso para {telefone_destino}!")
        else:
            print(f"❌ Erro da Meta ao enviar mensagem: {resposta.text}")
    except Exception as e:
        print(f"❌ Falha de comunicação com os servidores da Meta: {e}")

# Centralizador de variáveis globais para todas as telas
@app.context_processor
def inject_global_vars():
    # Defina aqui a versão centralizada
    versao = "1.5.2"

    # Gera a data automaticamente (ex: "Julho 2026")
    data_formatada = datetime.now().strftime('%B %Y').capitalize()

    return dict(
        versao_atual=versao,
        data_atual=data_formatada
    )

if __name__ == '__main__':
    app.run(debug=True)