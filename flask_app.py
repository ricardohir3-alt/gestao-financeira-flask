# 1. Bibliotecas Nativas do Python (Já vêm instaladas)
import os
import shutil
import platform
import secrets
import sqlite3
import csv
import io
import calendar
from datetime import datetime, timedelta

# 2. Bibliotecas Externas (Instaladas via pip)
import flask  # <--- ESSENCIAL para mostrar a versão na tela de sistema!
from flask import Flask, render_template, request, redirect, url_for, session, Response, jsonify, flash
import requests
import pdfplumber
import pytesseract
from PIL import Image
from werkzeug.security import generate_password_hash, check_password_hash

# 3. Seus Módulos Locais (Seus próprios arquivos)
from hir3_engine import analisar_mensagem_com_hir3

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
# ROTA DE LOGIN E LOGOULT (SALVA O ID DO USUÁRIO NA SESSÃO E VERIFICA LICENÇA)
# ==============================================================================

@app.route('/login', methods=['GET', 'POST'])
def login():
    erro = None
    sucesso = request.args.get('sucesso')

    if request.method == 'POST':
        usuario = request.form.get('usuario')
        senha_digitada = request.form.get('senha')
        # CORREÇÃO 1: Nome exato que está no HTML
        manter_conectado = request.form.get('lembrar')

        # CORREÇÃO 2: Caminho absoluto do PythonAnywhere
        conexao = sqlite3.connect('/home/Hir3solutions/mysite/financas.db')
        conexao.row_factory = sqlite3.Row
        cursor = conexao.cursor()

        # BUSCAMOS O REGISTRO DO USUÁRIO (Ignorando maiúsculas/minúsculas)
        cursor.execute("SELECT * FROM usuarios WHERE LOWER(usuario) = LOWER(?)", (usuario,))
        usuario_banco = cursor.fetchone()
        conexao.close()

        if usuario_banco and check_password_hash(usuario_banco['senha'], senha_digitada):

            # --- NOVA REGRA DE BLOQUEIO AQUI ---
            if usuario_banco['licenca'] in ['Bloqueada', 'Inativa', 'Vencida'] and usuario_banco[0] != 1:
                erro = "Acesso Negado: Sua licença está inativa ou bloqueada. Contate o administrador."
                return render_template('login.html', erro=erro, sucesso=sucesso)
            # -----------------------------------

            session['logado'] = True
            session['user_id'] = usuario_banco[0]
            session['usuario'] = usuario_banco['usuario']

            # =================================================================
            # A MÁGICA DO ADMIN ACONTECE AQUI
            # =================================================================
            dict_usuario = dict(usuario_banco)
            is_admin_db = dict_usuario.get('is_admin', 0)

            session['is_admin'] = (usuario_banco[0] == 1 or is_admin_db == 1)
            # =================================================================

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
    session.clear()
    return redirect(url_for('login'))

@app.route('/recuperar_senha', methods=['GET', 'POST'])
def recuperar():
    erro = None
    if request.method == 'POST':
        usuario = request.form.get('usuario')
        senha_atual = request.form.get('senha_atual') # NOVO CAMPO
        nova_senha = request.form.get('nova_senha')

        conexao = sqlite3.connect('/home/Hir3solutions/mysite/financas.db')
        conexao.row_factory = sqlite3.Row # Permite buscar colunas por nome
        cursor = conexao.cursor()

        # Busca o usuário ignorando maiúsculas/minúsculas
        cursor.execute('SELECT * FROM usuarios WHERE LOWER(usuario) = LOWER(?)', (usuario,))
        usuario_banco = cursor.fetchone()

        if usuario_banco:
            # A MÁGICA DA SEGURANÇA AQUI: Verifica se a senha atual está correta
            if check_password_hash(usuario_banco['senha'], senha_atual):
                # Se a senha atual bater, criptografa e salva a nova
                nova_senha_hash = generate_password_hash(nova_senha)

                # Usamos usuario_banco['usuario'] para garantir a grafia original do banco
                cursor.execute('UPDATE usuarios SET senha = ? WHERE usuario = ?', (nova_senha_hash, usuario_banco['usuario']))
                conexao.commit()
                conexao.close()

                return redirect(url_for('login', sucesso="Senha alterada com sucesso! Faça login com a nova senha."))
            else:
                erro = "A senha atual está incorreta. Operação cancelada!"
                conexao.close()
        else:
            erro = "Usuário não encontrado no sistema!"
            conexao.close()

    return render_template('telas/recuperar.html', erro=erro)

# ==============================================================================
# DASHBOARD
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
# ROTA DE GESTÃO DE USUÁRIOS (PROTEGIDA PARA ADMIN)
# ==============================================================================

@app.route('/usuarios', methods=['GET', 'POST'])
def usuarios():
    # 1. Verifica se está logado
    if 'logado' not in session:
        return redirect(url_for('login'))

    # 3. TRAVA DE SEGURANÇA CORRIGIDA
    # Agora a trava verifica se a flag 'is_admin' está verdadeira na sessão.
    # O "Admin Master" (ID 1) e qualquer usuário promovido a admin passarão por aqui.
    if not session.get('is_admin'):
        # Renderiza a tela correta (gestao_usuarios) sem precisar consultar o banco de dados.
        # O HTML vai ver que 'is_admin' é falso e vai exibir a tela linda de Acesso Restrito!
        return render_template('telas/gestao_usuarios.html')

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

        # Editar usuário (ATUALIZADO COM VALOR E MÓDULOS)
        elif 'editar' in request.form:
            id_edit = request.form.get('id_usuario_edit')
            novo_nome = request.form.get('novo_nome')
            nova_licenca = request.form.get('nova_licenca')
            novo_valor_raw = request.form.get('novo_valor', '0')
            novos_modulos = request.form.get('novos_modulos', 'Todos')

            # Converte a vírgula do valor em ponto para salvar no banco
            try:
                novo_valor = float(str(novo_valor_raw).replace(',', '.'))
            except ValueError:
                novo_valor = 0.00

            try:
                # Atualiza nome, licença, valor e módulos
                cursor.execute("""
                    UPDATE usuarios
                    SET usuario = ?, licenca = ?, valor_licencas = ?, modulos_liberados = ?
                    WHERE id = ?
                """, (novo_nome, nova_licenca, novo_valor, novos_modulos, id_edit))
                conexao.commit()
            except sqlite3.OperationalError:
                # Se a coluna modulos_liberados ainda não existir, atualiza sem ela para não travar
                cursor.execute("UPDATE usuarios SET usuario = ?, licenca = ?, valor_licencas = ? WHERE id = ?",
                               (novo_nome, nova_licenca, novo_valor, id_edit))
                conexao.commit()
            except sqlite3.Error as e:
                print(f"Erro ao atualizar usuário: {e}")

        # Excluir usuário
        elif 'excluir' in request.form:
            id_del = request.form.get('id_usuario')
            cursor.execute("DELETE FROM usuarios WHERE id = ? AND id != 1", (id_del,))
            conexao.commit()

    # LEITURA DE USUÁRIOS (COM TRATAMENTO DE SEGURANÇA)
    try:
        cursor.execute("SELECT id, usuario, licenca, valor_licencas, modulos_liberados FROM usuarios")
        lista_users = cursor.fetchall()
    except sqlite3.OperationalError:
        # Se a coluna de módulos ainda não existir no banco, cria uma estrutura falsa temporária
        cursor.execute("SELECT id, usuario, licenca, valor_licencas, 'Todos' as modulos_liberados FROM usuarios")
        lista_users = cursor.fetchall()

    # LEITURA DE LOGS
    logs = []
    try:
        cursor.execute("SELECT * FROM logs_sistema ORDER BY id DESC LIMIT 50")
        logs = [dict(row) for row in cursor.fetchall()]
    except sqlite3.OperationalError:
        logs = []

    conexao.close()

    # ==========================================
    # DADOS DINÂMICOS DO SISTEMA (NOVO)
    # ==========================================

    # 1. Tamanho do Banco de Dados
    db_size_mb = 0.0
    if os.path.exists('financas.db'):
        db_size_mb = round(os.path.getsize('financas.db') / (1024 * 1024), 2)

    # 2. Tamanho da Pasta de Uploads
    uploads_size_mb = 0.0
    uploads_path = 'static/uploads' # Ajuste se sua pasta for diferente
    if os.path.exists(uploads_path):
        total_size = 0
        for dirpath, _, filenames in os.walk(uploads_path):
            for f in filenames:
                fp = os.path.join(dirpath, f)
                if not os.path.islink(fp):
                    total_size += os.path.getsize(fp)
        uploads_size_mb = round(total_size / (1024 * 1024), 2)

    # 3. Uso do Disco Rígido do Servidor
    try:
        total_disk, used_disk, free_disk = shutil.disk_usage("/")
        disk_percent = int((used_disk / total_disk) * 100)
    except:
        disk_percent = 0

    # 4. Agrupando as métricas para enviar ao HTML
    sys_info = {
        'db_size': str(db_size_mb).replace('.', ','),
        'uploads_size': str(uploads_size_mb).replace('.', ','),
        'disk_percent': disk_percent,
        'python_version': platform.python_version(),
        'flask_version': flask.__version__,
        'app_version': 'v1.5.4'
    }

    # Enviamos 'usuarios', 'logs' e 'sys_info' para o template
    return render_template('telas/gestao_usuarios.html', usuarios=lista_users, logs=logs, sys_info=sys_info)

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
        valor_raw = request.form.get('valor_licencas', '0')

        try:
            novo_valor = float(str(valor_raw).replace(',', '.'))
        except ValueError:
            novo_valor = 0.00

        cursor.execute("UPDATE usuarios SET licenca = ?, valor_licencas = ? WHERE id = ?", (nova_licenca, novo_valor, id_usuario))
        conexao.commit()
        conexao.close()
        return redirect(url_for('licencas'))

    cursor.execute("SELECT COUNT(*) as total FROM usuarios")
    total_usuarios = cursor.fetchone()['total']

    cursor.execute("SELECT id, usuario, licenca, valor_licencas FROM usuarios WHERE id != 1")
    lista_usuarios = cursor.fetchall()

    conexao.close()

    return render_template('telas/licencas.html',
                           total_usuarios=total_usuarios,
                           usuarios=lista_usuarios)

@app.route('/tornar_admin/<int:id>', methods=['POST'])
def tornar_admin(id):
    # 1. TRAVA DE SEGURANÇA: Verifica se quem clicou é o Admin Master (ID 1)
    if session.get('user_id') != 1:
        flash('Acesso negado. Apenas o administrador master pode promover usuários.', 'error')
        return redirect(url_for('usuarios'))

    try:
        # 2. Conecta ao banco de dados SQLite
        conn = sqlite3.connect('/home/Hir3solutions/mysite/financas.db')
        cursor = conn.cursor()

        # 3. Atualiza o nível de acesso do usuário no banco.
        # ATENÇÃO: Esta linha VAI FALHAR se a coluna 'is_admin' não existir na sua tabela 'usuarios'
        cursor.execute("UPDATE usuarios SET is_admin = 1 WHERE id = ?", (id,))

        # 4. Salva a alteração e fecha a conexão
        conn.commit()
        conn.close()

        flash('Usuário promovido a Administrador com sucesso!', 'success')

    except sqlite3.OperationalError as e:
        flash('Erro de banco de dados: Você precisa criar a coluna "is_admin" na tabela "usuarios"!', 'error')
        print(f"Erro SQLite: {e}")
    except Exception as e:
        flash(f'Erro ao promover usuário: {str(e)}', 'error')
        print(f"Erro: {e}")

    # 5. ATUALIZADO: Agora redireciona corretamente para a função 'def usuarios():'
    return redirect(url_for('usuarios'))

# ==============================================================================
# ROTAS DO PAINEL FINANCEIRO E COBRANÇAS
# ==============================================================================

@app.route('/financeiro')
def financeiro():
    # 1. Trava de Segurança
    if 'logado' not in session or not session.get('is_admin'):
        flash('Acesso restrito ao setor financeiro.', 'error')
        return redirect(url_for('home'))

    conexao = sqlite3.connect('financas.db')
    conexao.row_factory = sqlite3.Row
    cursor = conexao.cursor()

    # 2. Dicionário padrão para os cards (evita erros se o banco estiver vazio)
    fin_data = {
        'receita_prevista': 0.0,
        'cobrancas_ativas': 0,
        'recebido_mes': 0.0,
        'taxa_recebimento': 0,
        'valor_atrasado': 0.0,
        'qtd_atrasados': 0
    }
    cobrancas_pendentes = []

    try:
        # 3. Busca faturas pendentes ou atrasadas juntando com o nome do usuário
        cursor.execute('''
            SELECT c.id, u.usuario, u.licenca, c.data_vencimento, c.valor_fatura, c.status_pagamento
            FROM cobrancas c
            JOIN usuarios u ON c.usuario_id = u.id
            WHERE c.status_pagamento != 'Em Dia'
            ORDER BY c.data_vencimento ASC
        ''')
        cobrancas_pendentes = [dict(row) for row in cursor.fetchall()]

        # 4. Calcula os totais para o Resumo Geral
        cursor.execute("SELECT status_pagamento, valor_fatura FROM cobrancas")
        todas_cobrancas = cursor.fetchall()

        for cob in todas_cobrancas:
            valor = float(cob['valor_fatura']) if cob['valor_fatura'] else 0.0
            status = cob['status_pagamento']

            fin_data['receita_prevista'] += valor
            fin_data['cobrancas_ativas'] += 1

            if status == 'Em Dia':
                fin_data['recebido_mes'] += valor
            elif status == 'Atrasado':
                fin_data['valor_atrasado'] += valor
                fin_data['qtd_atrasados'] += 1

        # 5. Calcula a porcentagem da meta de recebimento
        if fin_data['receita_prevista'] > 0:
            fin_data['taxa_recebimento'] = int((fin_data['recebido_mes'] / fin_data['receita_prevista']) * 100)

    except sqlite3.OperationalError:
        # ATENÇÃO: Se a tabela não existir, o sistema cria automaticamente!
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS cobrancas (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                usuario_id INTEGER,
                valor_fatura REAL,
                data_vencimento TEXT,
                status_pagamento TEXT
            )
        ''')
        conexao.commit()

    conexao.close()

    return render_template('financeiro.html', fin_data=fin_data, cobrancas_pendentes=cobrancas_pendentes)

@app.route('/atualizar_cobranca', methods=['POST'])
def atualizar_cobranca():
    # Rota ativada pelo botão "Atualizar Financeiro" na aba Gestão do Sistema
    if not session.get('is_admin'):
        return redirect(url_for('home'))

    id_usuario = request.form.get('id_usuario_cobranca')
    status = request.form.get('status_pagamento')
    vencimento = request.form.get('data_vencimento')
    valor_raw = request.form.get('valor_fatura', '0')

    # Trata o valor (troca vírgula por ponto)
    try:
        valor = float(str(valor_raw).replace(',', '.'))
    except ValueError:
        valor = 0.00

    try:
        conexao = sqlite3.connect('financas.db')
        cursor = conexao.cursor()

        # Verifica se o usuário já tem uma cobrança registrada
        cursor.execute("SELECT id FROM cobrancas WHERE usuario_id = ?", (id_usuario,))
        existe = cursor.fetchone()

        if existe:
            cursor.execute('''
                UPDATE cobrancas
                SET status_pagamento = ?, data_vencimento = ?, valor_fatura = ?
                WHERE usuario_id = ?
            ''', (status, vencimento, valor, id_usuario))
        else:
            cursor.execute('''
                INSERT INTO cobrancas (usuario_id, status_pagamento, data_vencimento, valor_fatura)
                VALUES (?, ?, ?, ?)
            ''', (id_usuario, status, vencimento, valor))

        conexao.commit()
        flash('Financeiro atualizado com sucesso!', 'success')
    except Exception as e:
        flash(f'Erro ao salvar cobrança: {e}', 'error')
    finally:
        conexao.close()

    return redirect(url_for('usuarios'))


@app.route('/marcar_pago/<int:id>', methods=['POST'])
def marcar_pago(id):
    # Rota ativada pelo botão verde de "Check" na tela do Painel Financeiro
    if not session.get('is_admin'):
        return redirect(url_for('home'))

    try:
        conexao = sqlite3.connect('financas.db')
        cursor = conexao.cursor()

        cursor.execute("UPDATE cobrancas SET status_pagamento = 'Em Dia' WHERE id = ?", (id,))
        conexao.commit()

        flash('Fatura marcada como PAGA com sucesso!', 'success')
    except Exception as e:
        flash(f'Erro ao dar baixa na fatura: {e}', 'error')
    finally:
        conexao.close()

    return redirect(url_for('financeiro'))

from datetime import datetime, timedelta

@app.route('/renovar_cobranca', methods=['POST'])
def renovar_cobranca():
    if not session.get('is_admin'):
        return redirect(url_for('home'))

    cobranca_id = request.form.get('cobranca_id')
    periodo = request.form.get('periodo')

    try:
        conexao = sqlite3.connect('financas.db')
        cursor = conexao.cursor()

        if periodo == 'indeterminado':
            novo_vencimento = 'Vitalício'
        else:
            # Calcula a data atual + os dias selecionados
            dias = int(periodo)
            data_futura = datetime.now() + timedelta(days=dias)

            # Formato YYYY-MM-DD para visualização limpa
            novo_vencimento = data_futura.strftime('%Y-%m-%d')

        # Atualiza a data e já marca como "Em Dia"
        cursor.execute('''
            UPDATE cobrancas
            SET data_vencimento = ?, status_pagamento = 'Em Dia'
            WHERE id = ?
        ''', (novo_vencimento, cobranca_id))

        conexao.commit()

        if periodo == 'indeterminado':
            flash('Assinatura renovada para tempo indeterminado (Vitalício)!', 'success')
        else:
            flash(f'Assinatura renovada com sucesso para +{periodo} dias!', 'success')

    except Exception as e:
        flash(f'Erro ao renovar assinatura: {e}', 'error')
    finally:
        conexao.close()

    return redirect(url_for('financeiro'))

# ==============================================================================
# MEU PERFIL
# ==============================================================================

@app.route('/perfil', methods=['GET', 'POST'])
def perfil():
    if 'logado' not in session: return redirect(url_for('login'))

    user_id = session['user_id']
    conexao = sqlite3.connect('financas.db')
    conexao.row_factory = sqlite3.Row # Adicionado para pegarmos os dados pelo nome da coluna
    cursor = conexao.cursor()

    if request.method == 'POST':
        # Aqui no futuro podemos processar a atualização de senha ou nome
        pass

    try:
        # Pede ao banco TODAS as informações novas do usuário
        cursor.execute("SELECT usuario, licenca, valor_licencas, modulos_liberados FROM usuarios WHERE id = ?", (user_id,))
        usuario_data = cursor.fetchone()
    except sqlite3.OperationalError:
        # Plano B: se a coluna de módulos ou valor ainda não existir, puxa só o básico para não dar erro 500
        cursor.execute("SELECT usuario, licenca FROM usuarios WHERE id = ?", (user_id,))
        row = cursor.fetchone()
        if row:
            usuario_data = {'usuario': row['usuario'], 'licenca': row['licenca'], 'valor_licencas': 0.0, 'modulos_liberados': 'Todos'}
        else:
            usuario_data = None

    conexao.close()

    # Distribuindo as informações capturadas nas variáveis que o HTML está esperando
    if usuario_data:
        nome_usuario = usuario_data['usuario']
        licenca_usuario = usuario_data['licenca']
        valor_licenca = usuario_data['valor_licencas']
        modulos_liberados = usuario_data['modulos_liberados']
    else:
        # Valores de segurança caso a sessão fique maluca
        nome_usuario = session.get('usuario', '')
        licenca_usuario = 'Básica'
        valor_licenca = 0.0
        modulos_liberados = 'Todos'

    return render_template('perfil.html',
                           nome_usuario=nome_usuario,
                           licenca_usuario=licenca_usuario,
                           valor_licenca=valor_licenca,
                           modulos_liberados=modulos_liberados)

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
    conn = sqlite3.connect('/home/Hir3solutions/mysite/financas.db')
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

import sqlite3
import json # <- Essencial para a IA funcionar

# ==============================================================================
# MOTOR DE APRENDIZADO DA IA (hir3) - BLINDADO
# ==============================================================================
def registrar_aprendizado_ia(user_id, modulo, acao, dados):
    """
    Registra os padrões de comportamento do usuário para treinamento contínuo da IA.
    Envolvido em try/except para NUNCA travar o sistema se algo der errado.
    """
    try:
        import json # Importação de segurança
        conexao = sqlite3.connect('financas.db')
        cursor = conexao.cursor()

        cursor.execute('''
            CREATE TABLE IF NOT EXISTS ia_comportamento_usuario (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                usuario_id INTEGER,
                modulo TEXT,
                acao TEXT,
                dados_json TEXT,
                data_registro DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        ''')

        cursor.execute('''
            INSERT INTO ia_comportamento_usuario (usuario_id, modulo, acao, dados_json)
            VALUES (?, ?, ?, ?)
        ''', (user_id, modulo, acao, json.dumps(dados)))

        conexao.commit()
    except Exception as e:
        print(f"[AVISO IA] Erro silencioso no motor de aprendizado: {e}")
    finally:
        conexao.close()


# ==============================================================================
# ROTAS DE GASTOS - BLINDADAS CONTRA ERRO 500
# ==============================================================================

@app.route('/novo_gasto', methods=['GET', 'POST'])
def novo_gasto():
    user_id = session.get('user_id')
    if not user_id:
        return redirect(url_for('login'))

    if request.method == 'POST':
        try:
            descricao = request.form.get('descricao', 'Gasto sem nome')
            categoria = request.form.get('categoria', 'Outros')
            data = request.form.get('data_gasto') or request.form.get('data')
            status = request.form.get('status', 'PAGO')

            valor_raw = request.form.get('valor', '0').strip()
            if not valor_raw:
                valor_raw = '0'
            try:
                valor = float(valor_raw.replace(',', '.'))
            except ValueError:
                valor = 0.0

            quinzena_raw = request.form.get('quinzena', '0')
            quinzena = int(quinzena_raw) if str(quinzena_raw).isdigit() else 0

            conexao = sqlite3.connect('financas.db')
            cursor = conexao.cursor()

            # ==========================================
            # AUTO-CORREÇÃO DO BANCO DE DADOS
            # Cria a coluna de quinzena caso ela não exista
            # ==========================================
            try:
                cursor.execute("ALTER TABLE gastos ADD COLUMN quinzena INTEGER DEFAULT 0")
                conexao.commit()
            except sqlite3.OperationalError:
                pass # Se a coluna já existir, ele segue o jogo!

            # Agora insere com a certeza absoluta de que a coluna existe
            cursor.execute('''
                INSERT INTO gastos (usuario_id, descricao, valor, categoria, data, quinzena, status)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            ''', (user_id, descricao, valor, categoria, data, quinzena, status))

            conexao.commit()
            conexao.close()

            # ALIMENTANDO A IA (Silenciosamente)
            try:
                registrar_aprendizado_ia(user_id, 'gastos', 'criar', {
                    'descricao': descricao, 'categoria': categoria, 'valor': valor, 'quinzena': quinzena, 'status': status
                })
            except Exception:
                pass

            return redirect(url_for('home'))

        except Exception as e:
            print(f"ERRO FATAL EM NOVO GASTO: {e}")
            return redirect(url_for('home'))

    return render_template('telas/novo_gasto.html')

@app.route('/editar_gasto/<int:id>', methods=['GET', 'POST'])
def editar_gasto(id):
    if 'user_id' not in session:
        return redirect(url_for('login'))

    user_id = session['user_id']
    conexao = sqlite3.connect('financas.db')
    conexao.row_factory = sqlite3.Row
    cursor = conexao.cursor()

    # ==========================================
    # AUTO-CORREÇÃO DO BANCO DE DADOS
    # ==========================================
    try:
        cursor.execute("ALTER TABLE gastos ADD COLUMN quinzena INTEGER DEFAULT 0")
        conexao.commit()
    except sqlite3.OperationalError:
        pass

    if request.method == 'POST':
        try:
            descricao = request.form.get('descricao', '')
            data = request.form.get('data_gasto', '')
            categoria = request.form.get('categoria', '')
            status = request.form.get('status', 'PAGO')

            valor_raw = request.form.get('valor', '0').strip()
            if not valor_raw:
                valor_raw = '0'
            try:
                valor = float(valor_raw.replace(',', '.'))
            except ValueError:
                valor = 0.0

            quinzena_raw = request.form.get('quinzena', '0')
            quinzena = int(quinzena_raw) if str(quinzena_raw).isdigit() else 0

            # O fallback sumiu porque garantimos que a coluna existe no try acima!
            cursor.execute("""
                UPDATE gastos
                SET descricao=?, data=?, valor=?, categoria=?, quinzena=?, status=?
                WHERE id=? AND usuario_id=?
            """, (descricao, data, valor, categoria, quinzena, status, id, user_id))

            conexao.commit()
            conexao.close()

            try:
                registrar_aprendizado_ia(user_id, 'gastos', 'editar', {
                    'id_gasto': id, 'nova_descricao': descricao, 'nova_categoria': categoria, 'novo_valor': valor, 'nova_quinzena': quinzena
                })
            except Exception:
                pass

            return redirect('/')

        except Exception as e:
            print(f"Erro fatal ao editar gasto: {e}")
            conexao.close()
            return redirect('/')

    # GET: Busca o gasto atual
    cursor.execute("SELECT * FROM gastos WHERE id=? AND usuario_id=?", (id, user_id))
    gasto = cursor.fetchone()
    conexao.close()

    if not gasto:
        return "Gasto não encontrado ou sem permissão", 404

    return render_template('telas/novo_gasto.html', gasto=gasto)

@app.route('/excluir_gasto/<int:id>', methods=['POST'])
def excluir_gasto(id):
    if 'user_id' not in session:
        return redirect(url_for('login'))

    user_id = session['user_id']
    conexao = sqlite3.connect('financas.db')
    cursor = conexao.cursor()

    try:
        cursor.execute("SELECT descricao, categoria, valor FROM gastos WHERE id = ? AND usuario_id = ?", (id, user_id))
        gasto_apagado = cursor.fetchone()

        cursor.execute("DELETE FROM gastos WHERE id = ? AND usuario_id = ?", (id, user_id))
        conexao.commit()

        if gasto_apagado:
            # ALIMENTANDO A IA DE FORMA SEGURA
            try:
                registrar_aprendizado_ia(user_id, 'gastos', 'excluir', {
                    'descricao_excluida': gasto_apagado[0],
                    'categoria': gasto_apagado[1],
                    'valor': gasto_apagado[2]
                })
            except Exception:
                pass

    except Exception as e:
        print(f"Erro ao excluir gasto: {e}")
    finally:
        conexao.close()

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
        # Salvar Meta de Compras
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

        # Adicionar novo item
        elif 'adicionar' in request.form or ('descricao' in request.form and 'id_item_edit' not in request.form):
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

        # Editar item existente (NOVA FUNCIONALIDADE)
        elif 'editar' in request.form:
            id_edit = request.form.get('id_item_edit')
            descricao = request.form.get('descricao', '').strip()
            quantidade = int(request.form.get('quantidade', 1))
            preco = parse_valor(request.form.get('preco'))
            total_item = quantidade * preco

            if descricao and id_edit:
                cursor.execute('''
                    UPDATE lista_compras
                    SET descricao = ?, quantidade = ?, preco = ?, total_item = ?
                    WHERE id = ? AND usuario_id = ?
                ''', (descricao, quantidade, preco, total_item, id_edit, user_id))
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
    output.write('\ufeff') # Garante a leitura correta de acentos no Excel
    writer = csv.writer(output, delimiter=';')

    # Cabeçalho atualizado
    writer.writerow(['Descrição', 'Quantidade', 'Preço Unitário', 'Total do Item'])

    row_num = 2 # Começa na linha 2 porque a linha 1 é o cabeçalho
    for item in itens:
        descricao = item[0]
        quantidade = item[1]
        preco_br = str(item[2]).replace('.', ',')

        # Injeção de Fórmula Dinâmica do Excel: Multiplica Quantidade (B) x Preço (C)
        formula_total = f'=B{row_num}*C{row_num}'

        writer.writerow([descricao, quantidade, preco_br, formula_total])
        row_num += 1

    # Espaçamento e Linha Final de Soma (Totalizador)
    writer.writerow(['', '', '', ''])
    if row_num > 2:
        # Cria um =SOMA(D2:DX) contendo todos os totais acima
        formula_soma_geral = f'=SOMA(D2:D{row_num-1})'
        writer.writerow(['', '', 'TOTAL GERAL:', formula_soma_geral])

    output.seek(0)
    # Atualizei o nome do arquivo para incluir o mês na hora de salvar
    return Response(output.getvalue(), mimetype="text/csv; charset=utf-8",
                    headers={"Content-Disposition": f"attachment;filename=lista_compras_{mes_atual}.csv"})

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

@app.route('/lancar_compras_gastos', methods=['POST'])
def lancar_compras_gastos():
    if 'logado' not in session:
        return redirect(url_for('login'))

    user_id = session.get('user_id')

    try:
        # Caminho absoluto para evitar qualquer erro de localização
        conexao = sqlite3.connect('/home/Hir3solutions/mysite/financas.db')
        conexao.row_factory = sqlite3.Row
        cursor = conexao.cursor()

        # CORREÇÃO CRÍTICA AQUI: A tabela correta é 'lista_compras'
        cursor.execute("SELECT SUM(quantidade * preco) as total FROM lista_compras WHERE usuario_id = ?", (user_id,))
        resultado = cursor.fetchone()
        total = resultado['total'] if resultado and resultado['total'] else 0

        if total > 0:
            hoje = datetime.now().strftime('%Y-%m-%d')
            dia_atual = datetime.now().day
            quinzena = 1 if dia_atual <= 15 else 2

            # Insere na tabela de gastos do mês associado ao usuário
            cursor.execute('''
                INSERT INTO gastos (descricao, valor, data, categoria, status, quinzena, usuario_id)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            ''', ('Supermercado do Mês', total, hoje, 'Alimentação', 'PAGO', quinzena, user_id))

            # CORREÇÃO CRÍTICA AQUI: Limpa a tabela 'lista_compras'
            cursor.execute("DELETE FROM lista_compras WHERE usuario_id = ?", (user_id,))

            # Manda a notificação para o Sininho da Hir3
            cursor.execute('''
                INSERT INTO notificacoes (titulo, mensagem, icone, cor, usuario_id, lida)
                VALUES (?, ?, ?, ?, ?, 0)
            ''', ('Compras Lançadas!', f'O valor de R$ {total:.2f} foi adicionado aos seus gastos de Alimentação.', 'shopping-cart', 'green', user_id))

            conexao.commit()
            flash('Lista de compras finalizada e lançada com sucesso!', 'success')
        else:
            flash('Sua lista de compras está vazia ou o valor total é zero.', 'warning')

        conexao.close()

    except Exception as e:
        print(f"Erro ao lançar compras: {e}")
        flash(f"Erro ao lançar compras: {e}", 'danger')

    # Redireciona diretamente para o painel principal
    return redirect(url_for('home'))

# ==============================================================================
# ROTA DA CALCULADORA
# ==============================================================================

@app.route('/calculadora')
def calculadora():
    if 'logado' not in session:
        return redirect(url_for('login'))
    return render_template('telas/calculadora.html')

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

    # ==========================================
    # BUSCA DE RESERVAS PARA O RELATÓRIO (CORRIGIDO FORA DO LOOP)
    # ==========================================
    cursor.execute("SELECT * FROM reservas WHERE usuario_id = ?", (user_id,))
    lista_reservas_relatorio = cursor.fetchall()

    # Fechamos a conexão após buscar todos os dados necessários
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
# FUNÇÃO PARA BUSCAR A MEMÓRIA DO USUÁRIO
# ==============================================================================
def buscar_memoria_hir3(user_id):
    """
    Busca os últimos comportamentos do usuário para ensinar o Gemini
    a adivinhar categorias e quinzenas com base no histórico real dele.
    """
    try:
        conexao = sqlite3.connect('financas.db')
        cursor = conexao.cursor()

        # Busca as últimas 10 ações (apenas do módulo de gastos)
        cursor.execute('''
            SELECT acao, dados_json FROM ia_comportamento_usuario
            WHERE usuario_id = ? AND modulo = 'gastos'
            ORDER BY data_registro DESC LIMIT 10
        ''', (user_id,))

        historico = cursor.fetchall()
        conexao.close()

        if not historico:
            return "O usuário é novo. Tente deduzir a categoria pela lógica padrão."

        memoria_texto = "Abaixo está o histórico recente de como o usuário categoriza seus gastos. Use isso para aprender o padrão dele e deduzir categorias/quinzenas parecidas:\n"
        for acao, dados_json in historico:
            memoria_texto += f"- Ação Feita: {acao} | Dados: {dados_json}\n"

        return memoria_texto
    except Exception as e:
        print(f"Erro ao buscar memória para a IA: {e}")
        return "Sem acesso à memória no momento."

# ==============================================================================
# CÉREBRO DO HIR3 (INTEGRAÇÃO IA)
# ==============================================================================
def analisar_mensagem_com_hir3(texto_usuario, user_id): # <--- ATENÇÃO: Adicionamos o user_id aqui!

    # 1. Busca a memória específica desse usuário
    memoria_do_usuario = buscar_memoria_hir3(user_id)

    # 2. Injeta a memória no Prompt do Gemini
    prompt = f"""
    Você é o 'hir3', um assistente financeiro carismático de Inteligência Artificial para WhatsApp.
    Você não é um bot engessado, você APRENDE com os hábitos do usuário!

    [MEMÓRIA DE COMPORTAMENTO DO USUÁRIO]
    {memoria_do_usuario}
    [FIM DA MEMÓRIA]

    O usuário vai te enviar uma mensagem e você DEVE extrair as informações e me devolver ÚNICA e EXCLUSIVAMENTE um objeto JSON válido, sem nenhuma formatação Markdown em volta.

    Regras de ação:
    1. Se o usuário relatar um gasto (ex: "comprei um lanche por 20", "gastei 50 no uber"):
       Retorne o JSON: {{"acao": "registrar_gasto", "valor": <float>, "descricao": "<texto resumido>", "categoria": "<Adivinhe a categoria: Alimentação, Transporte, Saúde, Habitação, Lazer ou Outros. PRIORIZE COMO O USUÁRIO FEZ NO PASSADO SEGUNDO A MEMÓRIA>", "quinzena": <1 ou 2, tente deduzir pela memória>, "mensagem_hir3": "<Sua resposta amigável e curta confirmando o registro>"}}

    2. Se o usuário perguntar sobre saldo, resumo, ou quanto falta pra meta:
       Retorne o JSON: {{"acao": "consultar_saldo", "mensagem_hir3": "<Uma frase inteligente e curta avisando que você vai buscar o extrato>"}}

    3. Se for qualquer outra coisa (oi, bom dia, dúvida, meme):
       Retorne o JSON: {{"acao": "conversar", "mensagem_hir3": "<Sua resposta carismática como assistente hir3>"}}

    Mensagem atual do usuário: "{texto_usuario}"
    """

    try:
        # Envia a mensagem com a memória embutida para o Gemini
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
            "mensagem_hir3": "Ops! Meu cérebro de silício deu uma travada rápida com os servidores da Google. Tenta mandar a mensagem de novo?"
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
    versao = "1.5.8"

    # Gera a data automaticamente (ex: "Julho 2026")
    data_formatada = datetime.now().strftime('%B %Y').capitalize()

    return dict(
        versao_atual=versao,
        data_atual=data_formatada
    )

if __name__ == '__main__':
    app.run(debug=True)