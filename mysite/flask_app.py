# ==============================================================================
# 1. IMPORTAÇÕES ORGANIZADAS
# ==============================================================================
import os
import shutil
import platform
import secrets
import sqlite3
import csv
import io
import calendar
import json
from datetime import datetime, timedelta, date

import flask
from flask import Flask, render_template, request, redirect, url_for, session, Response, jsonify, flash
import requests
import pdfplumber
import pytesseract
from PIL import Image
from werkzeug.security import generate_password_hash, check_password_hash
import google.generativeai as genai

# ==============================================================================
# 2. CONFIGURAÇÕES INICIAIS DO FLASK E BANCO DE DADOS
# ==============================================================================
from datetime import datetime # Importação necessária para o rastreador de atividade

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'chave_super_secreta_rafael_local')
app.permanent_session_lifetime = timedelta(days=30) # Mantém conectado por mais tempo

# O caminho inteligente para o Banco de Dados (Funciona local e no PythonAnywhere)
DB_PATH = '/home/Hir3solutions/mysite/financas.db' if os.path.exists('/home/Hir3solutions/mysite') else 'financas.db'

def get_db_connection():
    """Conexão blindada e centralizada para todo o sistema."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

# ==============================================================================
# RASTREADOR DE ATIVIDADE E TRAVA DE SEGURANÇA GLOBAIS
# ==============================================================================
@app.before_request
def verificacoes_globais():
    rotas_livres = ['login', 'static', 'recuperar', 'recuperar_senha']

    # Verifica se existe um usuário logado na sessão atual
    if 'logado' in session and 'usuario' in session:

        # 1. TRAVA B2B/SEGURANÇA: Se o usuário logado estiver marcado com senha fraca,
        # impede que ele acesse qualquer outra página além de forcar_troca_senha ou logout.
        if session.get('precisa_trocar_senha') and request.endpoint not in ['forcar_troca_senha', 'logout', 'static']:
            return redirect(url_for('forcar_troca_senha'))

        # 2. RASTREADOR DE ATIVIDADE (Último Acesso / Online)
        usuario_logado = session['usuario']
        agora = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

        try:
            conn = get_db_connection()
            cursor = conn.cursor()
            # Atualiza a coluna ultimo_acesso silenciosamente
            cursor.execute("UPDATE usuarios SET ultimo_acesso = ? WHERE usuario = ?", (agora, usuario_logado))
            conn.commit()
            conn.close()
        except:
            # Se der algum erro (ex: banco trancado temporariamente), ignora para não afetar o uso
            pass

    # 3. VERIFICAÇÃO DE LOGIN: Bloqueia não-logados de acessarem rotas protegidas
    elif request.endpoint not in rotas_livres and 'static' not in request.path:
        return redirect(url_for('login'))

# ==============================================================================
# 3. CONFIGURAÇÃO DA IA (GEMINI - HIR3)
# ==============================================================================
# Use Variáveis de Ambiente em produção!
chave_gemini = os.environ.get('GEMINI_API_KEY', 'SUA_CHAVE_API_AQUI')
genai.configure(api_key=chave_gemini)
modelo_hir3 = genai.GenerativeModel('gemini-1.5-flash')

TOKEN_VERIFICACAO = "minhas_financas_secreto_123"

# ==============================================================================
# 4. INICIALIZAÇÃO DO BANCO DE DADOS (CRIAÇÃO DE TABELAS)
# ==============================================================================
def iniciar_banco():
    conexao = get_db_connection()
    cursor = conexao.cursor()

    cursor.execute('''CREATE TABLE IF NOT EXISTS erros_diagnosticados (
        id INTEGER PRIMARY KEY AUTOINCREMENT, erro_raw TEXT, diagnostico TEXT,
        sugestao_correcao TEXT, data_criacao DATETIME DEFAULT CURRENT_TIMESTAMP)''')

    cursor.execute('''CREATE TABLE IF NOT EXISTS logs_sistema (
        id INTEGER PRIMARY KEY AUTOINCREMENT, erro_raw TEXT, diagnostico TEXT,
        data_criacao DATETIME DEFAULT CURRENT_TIMESTAMP)''')

    cursor.execute('''CREATE TABLE IF NOT EXISTS gastos (
        id INTEGER PRIMARY KEY AUTOINCREMENT, usuario_id INTEGER, descricao TEXT NOT NULL,
        categoria TEXT NOT NULL, valor REAL NOT NULL, quinzena INTEGER NOT NULL,
        status TEXT NOT NULL, data TEXT NOT NULL)''')

    cursor.execute('''CREATE TABLE IF NOT EXISTS reservas (
        id INTEGER PRIMARY KEY AUTOINCREMENT, usuario_id INTEGER, nome TEXT NOT NULL,
        meta REAL NOT NULL, guardado REAL DEFAULT 0)''')

    cursor.execute('''CREATE TABLE IF NOT EXISTS usuarios (
        id INTEGER PRIMARY KEY AUTOINCREMENT, usuario TEXT UNIQUE NOT NULL,
        senha TEXT NOT NULL, telefone TEXT, licenca TEXT, valor_licencas REAL,
        modulos_liberados TEXT, validade_licenca TEXT, ativo INTEGER DEFAULT 1,
        is_admin INTEGER DEFAULT 0, renda REAL, renda_variavel TEXT, ultimo_mes_acesso TEXT)''')

    cursor.execute('''CREATE TABLE IF NOT EXISTS compras (
        id INTEGER PRIMARY KEY AUTOINCREMENT, usuario_id INTEGER, item TEXT NOT NULL,
        comprado INTEGER DEFAULT 0, valor REAL DEFAULT 0.0, mes TEXT DEFAULT '',
        descricao TEXT, quantidade INTEGER DEFAULT 1, preco REAL DEFAULT 0.0)''')

    cursor.execute('''CREATE TABLE IF NOT EXISTS dividas (
        id INTEGER PRIMARY KEY AUTOINCREMENT, usuario_id INTEGER, descricao TEXT,
        valor_total REAL, total_parcelas INTEGER, parcelas_pagas INTEGER DEFAULT 0,
        valor_parcela REAL, status TEXT DEFAULT 'ATIVA', FOREIGN KEY(usuario_id) REFERENCES usuarios(id))''')

    cursor.execute('''CREATE TABLE IF NOT EXISTS meta_compras (
        usuario_id INTEGER, mes TEXT, valor REAL DEFAULT 0.0, PRIMARY KEY (usuario_id, mes))''')

    cursor.execute('''CREATE TABLE IF NOT EXISTS metas (
        id INTEGER PRIMARY KEY AUTOINCREMENT, usuario_id INTEGER NOT NULL, nome_meta TEXT NOT NULL,
        valor_objetivo REAL NOT NULL, valor_atual REAL DEFAULT 0.00, data_prazo TEXT NOT NULL,
        data_criacao TEXT NOT NULL, status TEXT DEFAULT 'ATIVA')''')

    cursor.execute('''CREATE TABLE IF NOT EXISTS ia_comportamento_usuario (
        id INTEGER PRIMARY KEY AUTOINCREMENT, usuario_id INTEGER, modulo TEXT,
        acao TEXT, dados_json TEXT, data_registro DATETIME DEFAULT CURRENT_TIMESTAMP)''')

    cursor.execute('''CREATE TABLE IF NOT EXISTS cobrancas (
        id INTEGER PRIMARY KEY AUTOINCREMENT, usuario_id INTEGER, valor_fatura REAL,
        data_vencimento TEXT, data_pagamento TEXT, status_pagamento TEXT)''')

    cursor.execute('''CREATE TABLE IF NOT EXISTS notificacoes (
        id INTEGER PRIMARY KEY AUTOINCREMENT, usuario_id INTEGER, titulo TEXT,
        mensagem TEXT, icone TEXT, cor TEXT, lida INTEGER DEFAULT 0,
        data_criacao DATETIME DEFAULT CURRENT_TIMESTAMP)''')

    # Criação do Admin Mestre Inicial
    cursor.execute("SELECT * FROM usuarios WHERE usuario = 'admin'")
    if not cursor.fetchone():
        senha_criptografada = generate_password_hash('123')
        cursor.execute("INSERT INTO usuarios (usuario, senha, is_admin, ativo) VALUES ('admin', ?, 1, 1)", (senha_criptografada,))

    conexao.commit()
    conexao.close()

# ==============================================================================
# ROTA DE LOGIN E LOGOUT
# ==============================================================================
import re # Certifique-se de que isso está no topo do seu arquivo, junto com os outros imports!

def is_senha_forte(senha):
    """
    Verifica se a senha contém pelo menos:
    - 1 letra maiúscula
    - 1 letra minúscula
    - 1 número
    """
    if len(senha) < 6: return False # Mínimo de 6 caracteres é recomendado
    if not re.search(r'[A-Z]', senha): return False
    if not re.search(r'[a-z]', senha): return False
    if not re.search(r'\d', senha): return False
    return True

@app.route('/login', methods=['GET', 'POST'])
def login():
    erro = None
    sucesso = request.args.get('sucesso')

    if request.method == 'POST':
        usuario = request.form.get('usuario')
        senha_digitada = request.form.get('senha')
        manter_conectado = request.form.get('lembrar')

        conexao = get_db_connection()
        cursor = conexao.cursor()
        cursor.execute("SELECT * FROM usuarios WHERE LOWER(usuario) = LOWER(?)", (usuario,))
        usuario_banco = cursor.fetchone()
        conexao.close()

        if usuario_banco and check_password_hash(usuario_banco['senha'], senha_digitada):
            dict_usuario = dict(usuario_banco)

            if usuario_banco['id'] != 1:
                # Travas B2B
                if dict_usuario.get('licenca') in ['Bloqueada', 'Inativa', 'Vencida']:
                    return render_template('login.html', erro="Acesso Negado: Sua licença está inativa.", sucesso=sucesso)
                if dict_usuario.get('ativo') == 0:
                    return render_template('login.html', erro="Acesso Negado: Seu usuário foi desativado.", sucesso=sucesso)

                hoje = date.today().strftime('%Y-%m-%d')
                validade = dict_usuario.get('validade_licenca')
                if validade and validade not in ['None', '']:
                    if hoje > validade:
                        return redirect(url_for('assinatura_vencida'))

            # Inicia a Sessão
            session['logado'] = True
            session['user_id'] = usuario_banco['id']
            session['usuario'] = usuario_banco['usuario']
            session['nome'] = usuario_banco['usuario'] # Facilitar no front

            is_admin_db = dict_usuario.get('is_admin', 0)
            session['is_admin'] = (usuario_banco['id'] == 1 or is_admin_db == 1)
            session.permanent = bool(manter_conectado)

            # CHECAGEM DE FORÇA DA SENHA
            if not is_senha_forte(senha_digitada):
                # Se a senha for fraca, ele loga, mas é travado nesta tela
                session['precisa_trocar_senha'] = True
                return redirect(url_for('forcar_troca_senha'))

            # Se a senha for segura, limpa a flag (caso exista) e vai pro Dashboard
            session.pop('precisa_trocar_senha', None)
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
        senha_atual = request.form.get('senha_atual')
        nova_senha = request.form.get('nova_senha')

        conexao = get_db_connection()
        cursor = conexao.cursor()
        cursor.execute('SELECT * FROM usuarios WHERE LOWER(usuario) = LOWER(?)', (usuario,))
        usuario_banco = cursor.fetchone()

        if usuario_banco:
            if check_password_hash(usuario_banco['senha'], senha_atual):
                # Validar se a NOVA senha é forte
                if not is_senha_forte(nova_senha):
                    erro = "Sua nova senha deve ter pelo menos 6 caracteres, contendo letras maiúsculas, minúsculas e números."
                else:
                    nova_senha_hash = generate_password_hash(nova_senha)
                    cursor.execute('UPDATE usuarios SET senha = ? WHERE usuario = ?', (nova_senha_hash, usuario_banco['usuario']))
                    conexao.commit()
                    conexao.close()
                    return redirect(url_for('login', sucesso="Senha atualizada! Sua nova senha já atende aos padrões de segurança."))
            else:
                erro = "A senha atual está incorreta. Operação cancelada!"
        else:
            erro = "Usuário não encontrado no sistema!"
        conexao.close()
    return render_template('telas/recuperar.html', erro=erro)

@app.route('/forcar_troca_senha', methods=['GET', 'POST'])
def forcar_troca_senha():
    # Verifica se a pessoa realmente precisa estar aqui
    if 'logado' not in session or not session.get('precisa_trocar_senha'):
        return redirect(url_for('home'))

    erro = None
    if request.method == 'POST':
        nova_senha = request.form.get('nova_senha')
        confirmar_senha = request.form.get('confirmar_senha')

        if nova_senha != confirmar_senha:
            erro = "As senhas não coincidem. Tente novamente."
        elif not is_senha_forte(nova_senha):
            erro = "Sua senha deve ter no mínimo 6 caracteres, conter pelo menos 1 letra maiúscula, 1 minúscula e 1 número."
        else:
            # Senha forte! Atualiza no banco e libera o acesso.
            conexao = get_db_connection()
            cursor = conexao.cursor()
            nova_senha_hash = generate_password_hash(nova_senha)
            cursor.execute('UPDATE usuarios SET senha = ? WHERE id = ?', (nova_senha_hash, session['user_id']))
            conexao.commit()
            conexao.close()

            # Remove a trava e manda pro Dashboard
            session.pop('precisa_trocar_senha', None)
            return redirect(url_for('home'))

    return render_template('telas/forcar_senha.html', erro=erro)

# ==============================================================================
# PÁGINAS LEGAIS (Termos e Privacidade)
# ==============================================================================
@app.route('/politica_privacidade')
def politica_privacidade():
    # Se o usuário não estiver logado, base.html vai ocultar o menu automaticamente
    return render_template('telas/politica.html')

@app.route('/termos_uso')
def termos_uso():
    return render_template('telas/termos.html')

# ==============================================================================
# CADASTRO DE CLIENTES
# ==============================================================================

@app.route('/cadastro_clientes', methods=['POST'])
def cadastro_clientes():
    # Pega os dados enviados pelo formulário invisível
    usuario = request.form.get('usuario')
    email = request.form.get('email')
    senha = request.form.get('senha')
    senha_confirmacao = request.form.get('senha_confirmacao')

    # Trata o e-mail: se vier vazio, transforma em None (Nulo no banco de dados)
    if email:
        email = email.strip()
        if email == "":
            email = None
    else:
        email = None

    # 1. Validação básica (email retirado da obrigatoriedade)
    if not usuario or not senha:
        return render_template('login.html', erro="Preencha todos os campos obrigatórios do cadastro!")

    if senha != senha_confirmacao:
        return render_template('login.html', erro="As senhas digitadas não coincidem!")

    # 2. Conectar ao banco de dados
    conn = sqlite3.connect('/home/Hir3solutions/mysite/financas.db')
    cursor = conn.cursor()

    # 3. Verificar se o usuário já existe (e o e-mail também, se foi preenchido)
    if email:
        cursor.execute("SELECT id FROM usuarios WHERE usuario = ? OR email = ?", (usuario, email))
        if cursor.fetchone():
            conn.close()
            return render_template('login.html', erro="Usuário ou E-mail já cadastrado!")
    else:
        cursor.execute("SELECT id FROM usuarios WHERE usuario = ?", (usuario,))
        if cursor.fetchone():
            conn.close()
            return render_template('login.html', erro="Esse usuário já existe. Escolha outro nome!")

    # 4. Criptografar a senha
    from werkzeug.security import generate_password_hash
    senha_hash = generate_password_hash(senha)

    # 5. Inserir o novo cliente (passando a variável email, que pode ter texto ou ser nula)
    try:
        cursor.execute("""
            INSERT INTO usuarios (usuario, email, senha, licenca, ativo, modulos_liberados)
            VALUES (?, ?, ?, 'basica', 1, 'dashboard,extrato')
        """, (usuario, email, senha_hash))
        conn.commit()
    except Exception as e:
        conn.close()
        return render_template('login.html', erro=f"Erro interno ao cadastrar: {str(e)}")

    conn.close()

    # 6. Se tudo der certo, recarrega a página de login limpa para ele entrar
    return redirect(url_for('login'))

# ==============================================================================
# DASHBOARD PRINCIPAL
# ==============================================================================
def verificar_virada_de_mes(user_id):
    mes_atual = datetime.now().strftime('%Y-%m')
    conexao = get_db_connection()
    cursor = conexao.cursor()
    cursor.execute("SELECT ultimo_mes_acesso, renda_variavel FROM usuarios WHERE id = ?", (user_id,))
    resultado = cursor.fetchone()

    if resultado:
        ultimo_mes = resultado['ultimo_mes_acesso']
        renda_variavel = resultado['renda_variavel']

        if ultimo_mes != mes_atual:
            if renda_variavel == 'sim':
                cursor.execute("UPDATE usuarios SET renda = 0.00, ultimo_mes_acesso = ? WHERE id = ?", (mes_atual, user_id))
            else:
                cursor.execute("UPDATE usuarios SET ultimo_mes_acesso = ? WHERE id = ?", (mes_atual, user_id))
            conexao.commit()
    conexao.close()

@app.route('/', methods=['GET'])
def home():
    if 'logado' not in session and 'usuario' not in session:
        return redirect(url_for('login'))

    user_id = session.get('user_id')
    if user_id: verificar_virada_de_mes(user_id)

    conexao = get_db_connection()
    cursor = conexao.cursor()

    # Busca configurações base do usuário
    cursor.execute("SELECT renda, renda_variavel FROM usuarios WHERE id = ?", (user_id,))
    resultado_usuario = cursor.fetchone()

    mes_atual_real = datetime.now().strftime('%Y-%m')
    mes_filtro = request.args.get('mes', mes_atual_real)

    # =====================================================================
    # LER A RENDA DA TABELA CORRETA (POR MÊS)
    # =====================================================================
    try:
        cursor.execute("SELECT valor FROM renda WHERE mes = ? AND usuario_id = ?", (mes_filtro, user_id))
        resultado_renda = cursor.fetchone()
    except Exception:
        resultado_renda = None # Se a tabela renda ainda não existir

    if resultado_renda:
        renda_atual = float(resultado_renda['valor'])
    else:
        try:
            if mes_filtro > mes_atual_real and resultado_usuario and resultado_usuario['renda_variavel'] == 'sim':
                renda_atual = 0.00
            elif resultado_usuario and resultado_usuario['renda'] is not None:
                renda_atual = float(resultado_usuario['renda'])
            else:
                renda_atual = 0.00
        except (ValueError, TypeError):
            renda_atual = 0.00
    # =====================================================================

    cursor.execute('SELECT * FROM gastos WHERE data LIKE ? AND usuario_id = ? ORDER BY data DESC', (mes_filtro + '%', user_id))
    lista_gastos = cursor.fetchall()

    total_gastos = sum(float(g['valor']) for g in lista_gastos)

    # =====================================================================
    # COMPARATIVO MENSAL (Cálculo do Mês Passado)
    # =====================================================================
    try:
        ano_filtro = int(mes_filtro[:4])
        mes_num = int(mes_filtro[5:7])

        if mes_num == 1:
            mes_passado_num = 12
            ano_passado = ano_filtro - 1
        else:
            mes_passado_num = mes_num - 1
            ano_passado = ano_filtro

        mes_passado_str = f"{ano_passado}-{mes_passado_num:02d}"

        cursor.execute("SELECT SUM(valor) as total FROM gastos WHERE data LIKE ? AND usuario_id = ?", (mes_passado_str + '%', user_id))
        resultado_passado = cursor.fetchone()
        total_passado = float(resultado_passado['total']) if resultado_passado and resultado_passado['total'] else 0.0
    except Exception:
        total_passado = 0.0
    # =====================================================================

    cursor.execute('''SELECT substr(data, 9, 2) as dia, SUM(valor) as total FROM gastos
                      WHERE data LIKE ? AND usuario_id = ? GROUP BY dia ORDER BY dia''', (mes_filtro + '%', user_id))
    dados_grafico = cursor.fetchall()
    dias_grafico = [row['dia'] for row in dados_grafico]
    valores_grafico = [float(row['total']) for row in dados_grafico]

    cursor.execute("SELECT * FROM notificacoes WHERE usuario_id = ? AND lida = 0 ORDER BY data_criacao DESC LIMIT 10", (user_id,))
    notificacoes = cursor.fetchall()
    total_notificacoes = len(notificacoes)

    cursor.execute("SELECT valor_fatura, data_vencimento FROM cobrancas WHERE usuario_id = ? AND status_pagamento = 'PENDENTE'", (user_id,))
    fatura_pendente = cursor.fetchone()

    conexao.close()

    # Cálculos
    categorias_dict = {}
    for g in lista_gastos:
        cat = g['categoria']
        categorias_dict[cat] = categorias_dict.get(cat, 0) + float(g['valor'])

    total_q1 = sum(float(g['valor']) for g in lista_gastos if str(g['quinzena']) == '1')
    total_q2 = sum(float(g['valor']) for g in lista_gastos if str(g['quinzena']) == '2')
    perc_q1 = round((total_q1 / total_gastos * 100), 1) if total_gastos > 0 else 0
    perc_q2 = round((total_q2 / total_gastos * 100), 1) if total_gastos > 0 else 0

    # =====================================================================
    # CORREÇÃO DO SCORE MATEMÁTICO
    # =====================================================================
    # Usamos .upper() para garantir que não vai quebrar por letras minúsculas no banco
    total_pago = sum(float(g['valor']) for g in lista_gastos if str(g['status']).upper() == 'PAGO')

    # Tudo que não foi pago, obrigatoriamente está pendente (garante que não perca os status VENCIDO/ATRASADO)
    total_pendente = total_gastos - total_pago

    if total_gastos > 0:
        perc_pago = round((total_pago / total_gastos * 100), 1)
        # Força o fechamento matemático cravado em 100%
        perc_pendente = round((100.0 - perc_pago), 1)
    else:
        perc_pago = 0
        perc_pendente = 0
    # =====================================================================

    top3_gastos = sorted(lista_gastos, key=lambda x: float(x['valor']), reverse=True)[:3]
    disponivel_geral = renda_atual - total_gastos

    # Formatações
    def fmt(v): return f"{v:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")

    # Fechamento do Comparativo Mensal
    diferenca_mensal = total_passado - total_gastos
    comparativo = {
        'total_atual': fmt(total_gastos),
        'total_passado': fmt(total_passado),
        'diferenca_absoluta': fmt(abs(diferenca_mensal)),
        'economizou': diferenca_mensal > 0,
        'excedeu': diferenca_mensal < 0
    }

    return render_template('index.html',
                           renda_total=fmt(renda_atual), gastos_totais=fmt(total_gastos),
                           valor_disponivel=fmt(disponivel_geral), gastos=lista_gastos,
                           mes_filtro=mes_filtro, dias_grafico=dias_grafico, valores_grafico=valores_grafico,
                           labels_categorias=list(categorias_dict.keys()), valores_categorias=list(categorias_dict.values()),
                           perc_q1=perc_q1, perc_q2=perc_q2, total_q1=fmt(total_q1), total_q2=fmt(total_q2),
                           perc_pago=perc_pago, perc_pendente=perc_pendente,
                           total_pago=fmt(total_pago), total_pendente=fmt(total_pendente),
                           top3_gastos=top3_gastos, notificacoes=notificacoes,
                           total_notificacoes=total_notificacoes, fatura_pendente=fatura_pendente,
                           comparativo=comparativo,
                           versao_atual="1.6.4")

@app.route('/historico_notificacoes')
def historico_notificacoes():
    if 'logado' not in session: return redirect(url_for('login'))
    conexao = get_db_connection()
    cursor = conexao.cursor()
    cursor.execute('SELECT * FROM notificacoes WHERE usuario_id = ? ORDER BY data_criacao DESC', (session['user_id'],))
    notificacoes_historico = cursor.fetchall()
    conexao.close()
    return render_template('telas/historico_notificacoes.html', notificacoes=notificacoes_historico)

# ==============================================================================
# GAMIFICAÇÃO E JORNADA IA
# ==============================================================================
def calcular_jornada_ia(usuario_id, cursor):
    """Função central para não quebrar a lógica do painel RPG."""
    cursor.execute("SELECT * FROM metas WHERE usuario_id = ? AND status = 'ATIVA' ORDER BY id DESC LIMIT 1", (usuario_id,))
    meta = cursor.fetchone()
    if meta:
        try:
            # Lógica simples para deduzir esforço mensal
            data_prazo = datetime.strptime(meta['data_prazo'], '%Y-%m-%d') if len(meta['data_prazo']) > 7 else datetime.strptime(meta['data_prazo'] + '-01', '%Y-%m-%d')
            hoje = datetime.now()
            meses_restantes = max(1, (data_prazo.year - hoje.year) * 12 + data_prazo.month - hoje.month)
            falta = meta['valor_objetivo'] - meta['valor_atual']
            missao_mensal = falta / meses_restantes
        except:
            missao_mensal = 0.0

        return {
            'nome': meta['nome_meta'],
            'objetivo': meta['valor_objetivo'],
            'valor_atual': meta['valor_atual'],
            'missao_mensal': missao_mensal
        }
    return None

@app.route('/nova_meta', methods=['POST'])
def nova_meta():
    if 'logado' not in session: return redirect(url_for('login'))
    user_id = session['user_id']

    nome_meta = request.form.get('nome_meta')
    valor_objetivo = request.form.get('valor_objetivo')
    data_prazo = request.form.get('data_prazo')
    data_criacao = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

    conexao = get_db_connection()
    cursor = conexao.cursor()
    cursor.execute("UPDATE metas SET status = 'PAUSADA' WHERE usuario_id = ? AND status = 'ATIVA'", (user_id,))
    cursor.execute('''INSERT INTO metas (usuario_id, nome_meta, valor_objetivo, data_prazo, data_criacao)
                      VALUES (?, ?, ?, ?, ?)''', (user_id, nome_meta, valor_objetivo, data_prazo, data_criacao))
    conexao.commit()
    conexao.close()
    return redirect(url_for('home'))

@app.route('/api/jornada_rpg')
def api_jornada_rpg():
    if 'user_id' not in session: return jsonify({'status': 'erro'}), 401

    try:
        id_usuario = session['user_id']
        mes_atual = datetime.now().strftime('%Y-%m')

        conexao = get_db_connection()
        cursor = conexao.cursor()

        cursor.execute("SELECT renda FROM usuarios WHERE id = ?", (id_usuario,))
        row_renda = cursor.fetchone()
        renda = float(row_renda['renda']) if row_renda and row_renda['renda'] else 0.0

        cursor.execute("SELECT SUM(valor) FROM gastos WHERE usuario_id = ? AND data LIKE ?", (id_usuario, f"{mes_atual}%"))
        row_gastos = cursor.fetchone()
        gastos = float(row_gastos[0]) if row_gastos and row_gastos[0] else 0.0

        jornada_ia = calcular_jornada_ia(id_usuario, cursor)
        conexao.close()

        saldo = renda - gastos
        perc_poupado = (saldo / renda * 100) if renda > 0 else 0

        if perc_poupado >= 30: nivel, meta_atual, nome_nivel = 4, renda * 0.40, "Nível 4: Independência"
        elif perc_poupado >= 20: nivel, meta_atual, nome_nivel = 3, renda * 0.30, "Nível 3: Paz de Espírito"
        elif perc_poupado >= 10: nivel, meta_atual, nome_nivel = 2, renda * 0.20, "Nível 2: Escudo Protetor"
        elif perc_poupado > 0: nivel, meta_atual, nome_nivel = 1, renda * 0.10, "Nível 1: O Despertar"
        else: nivel, meta_atual, nome_nivel = 0, renda * 0.10 if renda > 0 else 100, "Nível 0: Sobrevivência"

        progresso = min(100, max(0, (saldo / meta_atual * 100) if meta_atual > 0 else 0))

        prompt = f"Atue como um Mentor Financeiro Gamificado. Renda: {renda:.2f}, Gastos: {gastos:.2f}, Saldo: {saldo:.2f}. Nível: {nome_nivel}."
        if jornada_ia:
            prompt += f" Missão: Juntar {jornada_ia['objetivo']:.2f} para {jornada_ia['nome']}. Guardar {jornada_ia['missao_mensal']:.2f}/mês."
        prompt += " Escreva em 3 linhas com emojis estilo RPG."

        # Usa a variável global configurada no início
        resposta_ia = modelo_hir3.generate_content(prompt)

        return jsonify({
            'status': 'sucesso', 'nivel': nivel, 'saldo': saldo, 'meta_atual': meta_atual,
            'progresso': progresso, 'mensagem': resposta_ia.text.strip(), 'jornada_ia': jornada_ia
        })
    except Exception as e:
        print(f"Erro RPG: {e}")
        return jsonify({'status': 'erro'}), 500

# ==============================================================================
# GESTÃO DE USUÁRIOS E ADMINISTRAÇÃO
# ==============================================================================
from datetime import datetime, timedelta

@app.route('/usuarios', methods=['GET', 'POST'])
def usuarios():
    if 'logado' not in session: return redirect(url_for('login'))
    if not session.get('is_admin'): return render_template('telas/gestao_usuarios.html')

    conexao = get_db_connection()
    cursor = conexao.cursor()

    if request.method == 'POST':
        if 'cadastrar' in request.form:
            novo_user = request.form.get('usuario')
            nova_senha = generate_password_hash(request.form.get('senha'))
            nova_licenca = request.form.get('licenca')
            try:
                cursor.execute("INSERT INTO usuarios (usuario, senha, licenca) VALUES (?, ?, ?)", (novo_user, nova_senha, nova_licenca))
                conexao.commit()
            except sqlite3.IntegrityError: pass

        elif 'editar' in request.form:
            id_edit = request.form.get('id_usuario_edit')
            novo_nome = request.form.get('novo_nome')
            nova_licenca = request.form.get('nova_licenca')
            try: novo_valor = float(str(request.form.get('novo_valor', '0')).replace(',', '.'))
            except ValueError: novo_valor = 0.00
            novos_modulos = request.form.get('novos_modulos', 'Todos')

            try:
                cursor.execute("UPDATE usuarios SET usuario=?, licenca=?, valor_licencas=?, modulos_liberados=? WHERE id=?", (novo_nome, nova_licenca, novo_valor, novos_modulos, id_edit))
                conexao.commit()
            except: pass

        elif 'excluir' in request.form:
            id_del = request.form.get('id_usuario')
            try:
                cursor.execute("UPDATE usuarios SET ativo = 0 WHERE id = ? AND id != 1", (id_del,))
                conexao.commit()
            except: pass

    # Trazendo as novas colunas: validade_licenca, email e ultimo_acesso
    cursor.execute("SELECT id, usuario, licenca, valor_licencas, modulos_liberados, validade_licenca, email, ultimo_acesso FROM usuarios WHERE ativo = 1 OR ativo IS NULL")
    rows = cursor.fetchall()

    agora = datetime.now()
    lista_users = []

    for r in rows:
        # Garantindo leitura independente se o banco retornar Tupla ou Dicionário (sqlite3.Row)
        is_dict = hasattr(r, 'keys')
        uid = r['id'] if is_dict else r[0]
        unome = r['usuario'] if is_dict else r[1]
        ulic = r['licenca'] if is_dict else r[2]
        uval = r['valor_licencas'] if is_dict else r[3]
        umod = r['modulos_liberados'] if is_dict else r[4]
        uvalid = r['validade_licenca'] if is_dict else r[5]
        uemail = r['email'] if is_dict else r[6]
        u_acesso = r['ultimo_acesso'] if is_dict else r[7]

        is_online = False
        if u_acesso:
            try:
                data_acesso = datetime.strptime(u_acesso, '%Y-%m-%d %H:%M:%S')
                # Considera ONLINE se a última atividade foi há menos de 5 minutos
                if (agora - data_acesso) < timedelta(minutes=5):
                    is_online = True
            except: pass

        # O HTML espera exatamente essa ordem (0 ao 7)
        lista_users.append((uid, unome, ulic, uval, umod, uvalid, uemail, is_online))

    try:
        cursor.execute("SELECT * FROM logs_sistema ORDER BY id DESC LIMIT 50")
        logs = [dict(row) for row in cursor.fetchall()]
    except: logs = []

    conexao.close()

    db_size_mb = round(os.path.getsize(DB_PATH) / (1024 * 1024), 2) if os.path.exists(DB_PATH) else 0.0
    try: disk_percent = int((shutil.disk_usage("/")[1] / shutil.disk_usage("/")[0]) * 100)
    except: disk_percent = 0

    sys_info = {
        'db_size': str(db_size_mb).replace('.', ','),
        'disk_percent': disk_percent,
        'python_version': platform.python_version(),
        'flask_version': flask.__version__,
        'app_version': f"v{VERSAO_SISTEMA}" # <--- Agora ele puxa a versão oficial automaticamente!
    }

    return render_template('telas/gestao_usuarios.html', usuarios=lista_users, logs=logs, sys_info=sys_info)

@app.route('/api/inativar_usuario/<int:id_usuario>', methods=['POST'])
def api_inativar_usuario(id_usuario):
    if not session.get('is_admin'): return jsonify({'status': 'erro'}), 403
    try:
        conexao = get_db_connection()
        cursor = conexao.cursor()
        cursor.execute('UPDATE usuarios SET ativo = 0 WHERE id = ? AND id != 1', (id_usuario,))
        conexao.commit()
        conexao.close()
        return jsonify({'status': 'sucesso'})
    except Exception as e: return jsonify({'status': 'erro', 'mensagem': str(e)})

@app.route('/api/editar_usuario/<int:id_usuario>', methods=['POST'])
def api_editar_usuario(id_usuario):
    if not session.get('is_admin'): return jsonify({'status': 'erro'}), 403
    dados = request.json
    try: novo_valor = float(str(dados.get('valor_diario', dados.get('valor', '0'))).replace(',', '.'))
    except ValueError: novo_valor = 0.00
    nova_validade = dados.get('nova_validade', '2099-12-31')

    # Trata o e-mail (para não salvar vazio)
    email = dados.get('email')
    if email:
        email = email.strip()
        if email == "": email = None

    try:
        conexao = get_db_connection()
        cursor = conexao.cursor()
        # Adicionado o e-mail na query de atualização
        cursor.execute("""UPDATE usuarios SET usuario=?, email=?, licenca=?, valor_licencas=?, modulos_liberados=?, validade_licenca=? WHERE id=?""",
                       (dados['nome'], email, dados['licenca'], novo_valor, dados['modulos'], nova_validade, id_usuario))
        conexao.commit()
        conexao.close()
        return jsonify({'status': 'sucesso'})
    except Exception as e: return jsonify({'status': 'erro', 'mensagem': str(e)})

@app.route('/licencas', methods=['GET', 'POST'])
def licencas():
    if 'logado' not in session or session.get('user_id') != 1: return "Acesso negado", 403
    conexao = get_db_connection()
    cursor = conexao.cursor()
    if request.method == 'POST':
        try: novo_valor = float(str(request.form.get('valor_licencas', '0')).replace(',', '.'))
        except: novo_valor = 0.00
        cursor.execute("UPDATE usuarios SET licenca = ?, valor_licencas = ? WHERE id = ?", (request.form.get('nova_licenca'), novo_valor, request.form.get('id_usuario')))
        conexao.commit()
        return redirect(url_for('licencas'))

    cursor.execute("SELECT COUNT(*) as total FROM usuarios WHERE ativo = 1 OR ativo IS NULL")
    total_usuarios = cursor.fetchone()['total']
    cursor.execute("SELECT id, usuario, licenca, valor_licencas FROM usuarios WHERE id != 1 AND (ativo = 1 OR ativo IS NULL)")
    lista_usuarios = cursor.fetchall()
    conexao.close()
    return render_template('telas/licencas.html', total_usuarios=total_usuarios, usuarios=lista_usuarios)

@app.route('/assinatura_vencida')
def assinatura_vencida():
    session.clear()
    return render_template('telas/licencas_vencidas.html')

@app.route('/tornar_admin/<int:id>', methods=['POST'])
def tornar_admin(id):
    if session.get('user_id') != 1: return redirect(url_for('usuarios'))
    try:
        conexao = get_db_connection()
        cursor = conexao.cursor()
        cursor.execute("UPDATE usuarios SET is_admin = 1 WHERE id = ?", (id,))
        conexao.commit()
        conexao.close()
    except: pass
    return redirect(url_for('usuarios'))

# ==============================================================================
# PAINEL FINANCEIRO / EXTARTOS B2B
# ==============================================================================
@app.route('/financeiro')
def financeiro():
    if 'logado' not in session or not session.get('is_admin'): return redirect(url_for('home'))
    id_cliente_extrato = request.args.get('id_usuario')
    conexao = get_db_connection()
    cursor = conexao.cursor()

    fin_data = {'receita_prevista': 0.0, 'cobrancas_ativas': 0, 'recebido_mes': 0.0, 'taxa_recebimento': 0, 'valor_atrasado': 0.0, 'qtd_atrasados': 0, 'modo_extrato': bool(id_cliente_extrato), 'nome_cliente': ''}

    if id_cliente_extrato:
        cursor.execute("SELECT c.*, u.usuario as nome_usuario FROM cobrancas c JOIN usuarios u ON c.usuario_id = u.id WHERE c.usuario_id = ? ORDER BY c.status_pagamento DESC, c.data_vencimento ASC", (id_cliente_extrato,))
        cliente = cursor.execute("SELECT usuario FROM usuarios WHERE id = ?", (id_cliente_extrato,)).fetchone()
        if cliente: fin_data['nome_cliente'] = cliente['usuario']
    else:
        cursor.execute("SELECT c.*, u.usuario as nome_usuario FROM cobrancas c JOIN usuarios u ON c.usuario_id = u.id ORDER BY c.status_pagamento DESC, c.data_vencimento ASC")

    todas_cobrancas = [dict(row) for row in cursor.fetchall()]
    conexao.close()

    for cob in todas_cobrancas:
        valor = float(cob['valor_fatura']) if cob['valor_fatura'] else 0.0
        status = cob['status_pagamento']
        fin_data['receita_prevista'] += valor
        fin_data['cobrancas_ativas'] += 1
        if status == 'Em Dia': fin_data['recebido_mes'] += valor
        elif status in ['Atrasado', 'Pendente']:
            fin_data['valor_atrasado'] += valor
            fin_data['qtd_atrasados'] += 1

    if fin_data['receita_prevista'] > 0: fin_data['taxa_recebimento'] = int((fin_data['recebido_mes'] / fin_data['receita_prevista']) * 100)
    return render_template('telas/financeiro.html', fin_data=fin_data, lista_faturas=todas_cobrancas)

@app.route('/atualizar_cobranca', methods=['POST'])
def atualizar_cobranca():
    if not session.get('is_admin'): return redirect(url_for('home'))
    try: valor = float(str(request.form.get('valor_fatura', '0')).replace(',', '.'))
    except: valor = 0.00
    try:
        conexao = get_db_connection()
        cursor = conexao.cursor()
        cursor.execute("INSERT INTO cobrancas (usuario_id, status_pagamento, data_vencimento, valor_fatura) VALUES (?, ?, ?, ?)", (request.form.get('id_usuario_cobranca'), request.form.get('status_pagamento'), request.form.get('data_vencimento'), valor))
        conexao.commit()
    finally: conexao.close()
    return redirect(url_for('financeiro', id_usuario=request.form.get('id_usuario_cobranca')))

@app.route('/marcar_pago/<int:id>', methods=['POST'])
def marcar_pago(id):
    if not session.get('is_admin'): return redirect(url_for('home'))
    try:
        conexao = get_db_connection()
        cursor = conexao.cursor()
        cursor.execute("UPDATE cobrancas SET status_pagamento = 'Em Dia', data_pagamento = ? WHERE id = ?", (date.today().strftime('%Y-%m-%d'), id))
        conexao.commit()
    finally: conexao.close()
    if request.form.get('id_usuario_retorno'): return redirect(url_for('financeiro', id_usuario=request.form.get('id_usuario_retorno')))
    return redirect(url_for('financeiro'))

@app.route('/renovar_cobranca', methods=['POST'])
def renovar_cobranca():
    if not session.get('is_admin'): return redirect(url_for('home'))
    periodo = request.form.get('periodo')
    novo_vencimento = 'Vitalício' if periodo == 'indeterminado' else (datetime.now() + timedelta(days=int(periodo))).strftime('%Y-%m-%d')
    try:
        conexao = get_db_connection()
        cursor = conexao.cursor()
        cursor.execute("UPDATE cobrancas SET data_vencimento = ?, status_pagamento = 'Em Dia' WHERE id = ?", (novo_vencimento, request.form.get('cobranca_id')))
        conexao.commit()
    finally: conexao.close()
    return redirect(url_for('financeiro'))

# ==============================================================================
# PERFIL E ATUALIZAÇÕES
# ==============================================================================
@app.route('/perfil', methods=['GET', 'POST'])
def perfil():
    if 'logado' not in session: return redirect(url_for('login'))
    conexao = get_db_connection()
    cursor = conexao.cursor()

    if request.method == 'POST':
        novo_nome = request.form.get('nome')
        if novo_nome:
            cursor.execute("UPDATE usuarios SET usuario = ? WHERE id = ?", (novo_nome, session['user_id']))
            conexao.commit()
            session['nome'] = novo_nome

    try:
        cursor.execute("SELECT usuario, licenca, valor_licencas, modulos_liberados FROM usuarios WHERE id = ?", (session['user_id'],))
        usuario_data = cursor.fetchone()
    except sqlite3.OperationalError:
        cursor.execute("SELECT usuario, licenca FROM usuarios WHERE id = ?", (session['user_id'],))
        row = cursor.fetchone()
        if row:
            usuario_data = {'usuario': row['usuario'], 'licenca': row['licenca'], 'valor_licencas': 0.0, 'modulos_liberados': 'Todos'}
        else:
            usuario_data = None

    conexao.close()

    return render_template('perfil.html',
        nome_usuario=usuario_data['usuario'] if usuario_data else session.get('usuario'),
        licenca_usuario=usuario_data['licenca'] if usuario_data else 'Básica',
        valor_licenca=usuario_data['valor_licencas'] if usuario_data else 0.0,
        modulos_liberados=usuario_data['modulos_liberados'] if usuario_data else 'Todos')

@app.route('/atualizacoes')
def atualizacoes():
    if 'logado' not in session: return redirect(url_for('login'))
    return render_template('telas/atualizacoes.html')

# ==============================================================================
# ATUALIZAR RENDA DO MÊS
# ==============================================================================
@app.route('/renda', methods=['POST'])
def atualizar_renda():
    if 'logado' not in session: return redirect(url_for('login'))

    try:
        # 1. Pega o valor (agora aceita 'renda_base' do antigo ou 'renda' do Modal)
        renda_form = request.form.get('renda_base') or request.form.get('renda')

        # 2. Pega o mês. Se vier do Modal, ele chega vazio. Vamos puxar da URL (referrer) ou usar o atual!
        mes_filtro = request.form.get('mes_filtro')
        if not mes_filtro:
            if request.referrer and 'mes=' in request.referrer:
                mes_filtro = request.referrer.split('mes=')[1].split('&')[0]
            else:
                from datetime import datetime
                mes_filtro = datetime.now().strftime('%Y-%m')

        usuario_id = session.get('user_id', 1)

        if renda_form and mes_filtro:
            # Limpa formatação
            try:
                renda_float = float(renda_form)
            except ValueError:
                renda_float = float(renda_form.replace('.', '').replace(',', '.'))

            conexao = get_db_connection()
            cursor = conexao.cursor()

            # Cria tabela caso não exista (Segurança)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS renda (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    valor REAL NOT NULL,
                    mes TEXT NOT NULL,
                    usuario_id INTEGER DEFAULT 1
                )
            """)

            # Busca e atualiza/insere
            cursor.execute("SELECT id FROM renda WHERE mes = ? AND usuario_id = ?", (mes_filtro, usuario_id))
            row = cursor.fetchone()

            if row:
                id_renda = row[0] if isinstance(row, tuple) else row['id']
                cursor.execute("UPDATE renda SET valor = ? WHERE id = ?", (renda_float, id_renda))
            else:
                cursor.execute("INSERT INTO renda (valor, mes, usuario_id) VALUES (?, ?, ?)", (renda_float, mes_filtro, usuario_id))

            # Caso queira usar a opção de renda variável no front-end, deixamos salvo na sessão
            renda_variavel = request.form.get('renda_variavel')
            if renda_variavel:
                session['renda_variavel'] = renda_variavel

            conexao.commit()
            conexao.close()

    except Exception as e:
        print(f"Erro ao salvar renda: {e}")

    # 3. O PULO DO GATO: Volta exatamente para a página e filtro que você estava!
    return redirect(request.referrer or url_for('home'))

# ==============================================================================
# GASTOS E LAÇAMENTOS
# ==============================================================================
def registrar_aprendizado_ia(user_id, modulo, acao, dados):
    try:
        conexao = get_db_connection()
        cursor = conexao.cursor()
        cursor.execute("INSERT INTO ia_comportamento_usuario (usuario_id, modulo, acao, dados_json) VALUES (?, ?, ?, ?)", (user_id, modulo, acao, json.dumps(dados)))
        conexao.commit()
    except Exception as e: print(f"[IA] Erro: {e}")
    finally: conexao.close()

@app.route('/novo_gasto', methods=['GET', 'POST'])
def novo_gasto():
    if 'user_id' not in session: return redirect(url_for('login'))
    if request.method == 'POST':
        try:
            try: valor = float(str(request.form.get('valor', '0')).replace(',', '.'))
            except ValueError: valor = 0.0

            conexao = get_db_connection()
            cursor = conexao.cursor()
            cursor.execute("INSERT INTO gastos (usuario_id, descricao, valor, categoria, data, quinzena, status) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (session['user_id'], request.form.get('descricao', 'Gasto sem nome'), valor, request.form.get('categoria', 'Outros'), request.form.get('data_gasto') or request.form.get('data'), int(request.form.get('quinzena', '0')), request.form.get('status', 'PAGO')))
            conexao.commit()
            conexao.close()
            registrar_aprendizado_ia(session['user_id'], 'gastos', 'criar', {'descricao': request.form.get('descricao'), 'categoria': request.form.get('categoria'), 'valor': valor})
            return redirect(url_for('home'))
        except Exception as e: print(f"Erro: {e}"); return redirect(url_for('home'))
    return render_template('telas/novo_gasto.html')

@app.route('/editar_gasto/<int:id>', methods=['POST'])
def editar_gasto(id):
    if 'user_id' not in session: return redirect(url_for('login'))
    try: valor = float(str(request.form.get('valor', '0')).replace(',', '.'))
    except: valor = 0.0
    conexao = get_db_connection()
    cursor = conexao.cursor()
    cursor.execute("UPDATE gastos SET descricao=?, data=?, valor=?, categoria=?, quinzena=?, status=? WHERE id=? AND usuario_id=?",
        (request.form.get('descricao'), request.form.get('data'), valor, request.form.get('categoria'), int(request.form.get('quinzena', '0')), request.form.get('status', 'PENDENTE'), id, session['user_id']))
    conexao.commit()
    conexao.close()

    mes_filtro = request.form.get('mes_filtro')
    return redirect(url_for('home', mes=mes_filtro) if mes_filtro else url_for('home'))

@app.route('/excluir_gasto/<int:id>', methods=['POST'])
def excluir_gasto(id):
    if 'user_id' not in session: return redirect(url_for('login'))
    conexao = get_db_connection()
    cursor = conexao.cursor()
    cursor.execute("DELETE FROM gastos WHERE id = ? AND usuario_id = ?", (id, session['user_id']))
    conexao.commit()
    conexao.close()
    mes_filtro = request.form.get('mes_filtro')
    return redirect(url_for('home', mes=mes_filtro) if mes_filtro else url_for('home'))

@app.route('/api/gastos_mes', methods=['GET'])
def api_gastos_mes():
    if 'user_id' not in session: return jsonify([]), 401
    mes = request.args.get('mes')
    if not mes: return jsonify([])
    conexao = get_db_connection()
    cursor = conexao.cursor()
    cursor.execute('SELECT id, descricao, valor, categoria FROM gastos WHERE data LIKE ? AND usuario_id = ? ORDER BY data ASC', (mes + '%', session['user_id']))
    gastos = [{'id': g['id'], 'descricao': g['descricao'], 'valor': float(g['valor']), 'categoria': g['categoria']} for g in cursor.fetchall()]
    conexao.close()
    return jsonify(gastos)

@app.route('/duplicar_gastos_lote', methods=['POST'])
def duplicar_gastos_lote():
    if 'user_id' not in session: return redirect(url_for('login'))
    mes_destino, contas = request.form.get('mes_destino'), request.form.getlist('contas_selecionadas')
    if not mes_destino or not contas: return redirect(url_for('novo_gasto'))

    ano_dest, mes_dest = map(int, mes_destino.split('-'))
    ultimo_dia = calendar.monthrange(ano_dest, mes_dest)[1]

    conexao = get_db_connection()
    cursor = conexao.cursor()
    cursor.execute(f"SELECT * FROM gastos WHERE id IN ({','.join('?'*len(contas))}) AND usuario_id = ?", contas + [session['user_id']])

    for g in cursor.fetchall():
        try: dia_origem = int(g['data'][8:10])
        except: dia_origem = 1
        nova_data = f"{ano_dest:04d}-{mes_dest:02d}-{min(dia_origem, ultimo_dia):02d}"
        cursor.execute("INSERT INTO gastos (descricao, categoria, valor, quinzena, status, data, usuario_id) VALUES (?, ?, ?, ?, 'PENDENTE', ?, ?)",
                       (g['descricao'], g['categoria'], g['valor'], g['quinzena'], nova_data, session['user_id']))
    conexao.commit()
    conexao.close()
    return redirect(url_for('home', mes=mes_destino))

@app.route('/atualizar_status/<int:id_gasto>', methods=['POST'])
def atualizar_status(id_gasto):
    if 'logado' not in session and 'user_id' not in session: return redirect(url_for('login'))
    conexao = get_db_connection()
    cursor = conexao.cursor()

    # Busca o status e o id do contrato (se ele existir)
    gasto = cursor.execute('SELECT status, divida_id FROM gastos WHERE id = ? AND usuario_id = ?', (id_gasto, session['user_id'])).fetchone()

    if gasto:
        status_atual = gasto['status']
        novo_status = 'PAGO' if status_atual == 'PENDENTE' else 'PENDENTE'

        # 1. Atualiza o status do gasto na tabela
        cursor.execute('UPDATE gastos SET status = ? WHERE id = ?', (novo_status, id_gasto))

        # =========================================================
        # MOTOR INTELIGENTE: SINCRONIZAÇÃO DE CONTRATOS A LONGO PRAZO
        # =========================================================
        try:
            divida_id = gasto['divida_id']
            if divida_id:
                if novo_status == 'PAGO':
                    # Avança o progresso da dívida
                    cursor.execute("UPDATE dividas SET parcelas_pagas = parcelas_pagas + 1 WHERE id = ?", (divida_id,))
                elif novo_status == 'PENDENTE':
                    # Recua o progresso se o usuário desmarcar
                    cursor.execute("UPDATE dividas SET parcelas_pagas = parcelas_pagas - 1 WHERE id = ?", (divida_id,))
        except Exception as e:
            print(f"[SYNC DIVIDA] Erro: {e}")
        # =========================================================

        conexao.commit()
    conexao.close()
    mes_filtro = request.args.get('mes')
    return redirect(url_for('home', mes=mes_filtro) if mes_filtro else url_for('home'))

# ==============================================================================
# DÍVIDAS E PLANEJAMENTO
# ==============================================================================
@app.route('/dividas', methods=['GET'])
def dividas():
    if not session.get('user_id'): return redirect(url_for('login'))
    conexao = get_db_connection()
    cursor = conexao.cursor()
    dividas = cursor.execute("SELECT * FROM dividas WHERE usuario_id = ? ORDER BY id DESC", (session['user_id'],)).fetchall()
    conexao.close()
    return render_template('telas/dividas_planejamento.html', dividas=dividas)

@app.route('/nova_divida', methods=['POST'])
def nova_divida():
    if not session.get('user_id'): return redirect(url_for('login'))
    try: valor_total = float(str(request.form.get('valor_total_divida', '0')).replace(',', '.'))
    except: valor_total = 0.0
    try: valor_parcela = float(str(request.form.get('valor', '0')).replace(',', '.'))
    except: valor_parcela = 0.0
    conexao = get_db_connection()
    cursor = conexao.cursor()
    cursor.execute("INSERT INTO dividas (usuario_id, descricao, valor_total, total_parcelas, parcelas_pagas, valor_parcela, status) VALUES (?, ?, ?, ?, 0, ?, 'ATIVA')",
                   (session['user_id'], request.form.get('descricao'), valor_total, int(request.form.get('total_parcelas', '1')), valor_parcela))
    conexao.commit()
    conexao.close()
    return redirect('/dividas')

@app.route('/editar_divida/<int:id>', methods=['POST'])
def editar_divida(id):
    if not session.get('user_id'): return redirect(url_for('login'))
    try: valor_total = float(str(request.form.get('valor_total', '0')).replace(',', '.'))
    except: valor_total = 0.0
    try: valor_parcela = float(str(request.form.get('valor_parcela', '0')).replace(',', '.'))
    except: valor_parcela = 0.0
    conexao = get_db_connection()
    cursor = conexao.cursor()
    cursor.execute("UPDATE dividas SET descricao=?, valor_total=?, total_parcelas=?, valor_parcela=?, parcelas_pagas=? WHERE id=? AND usuario_id=?",
                   (request.form.get('descricao'), valor_total, int(request.form.get('total_parcelas', '1')), valor_parcela, int(request.form.get('parcelas_pagas', '0')), id, session['user_id']))
    conexao.commit()
    conexao.close()
    return redirect('/dividas')

@app.route('/pagar_parcela/<int:id>', methods=['POST'])
def pagar_parcela(id):
    conexao = get_db_connection()
    cursor = conexao.cursor()
    d = cursor.execute("SELECT parcelas_pagas, total_parcelas FROM dividas WHERE id = ? AND usuario_id = ?", (id, session['user_id'])).fetchone()
    if d and d['parcelas_pagas'] < d['total_parcelas']:
        cursor.execute("UPDATE dividas SET parcelas_pagas = ?, status = ? WHERE id = ?", (d['parcelas_pagas'] + 1, 'CONCLUIDA' if d['parcelas_pagas'] + 1 == d['total_parcelas'] else 'ATIVA', id))
        conexao.commit()
    conexao.close()
    return redirect('/dividas')

@app.route('/quitar_divida/<int:id>', methods=['POST'])
def quitar_divida(id):
    conexao = get_db_connection()
    cursor = conexao.cursor()
    cursor.execute("UPDATE dividas SET parcelas_pagas = total_parcelas, status = 'CONCLUIDA' WHERE id = ? AND usuario_id = ?", (id, session['user_id']))
    conexao.commit()
    conexao.close()
    return redirect('/dividas')

@app.route('/excluir_divida/<int:id>', methods=['POST'])
def excluir_divida(id):
    conexao = get_db_connection()
    cursor = conexao.cursor()
    cursor.execute("DELETE FROM dividas WHERE id = ? AND usuario_id = ?", (id, session['user_id']))
    conexao.commit()
    conexao.close()
    return redirect('/dividas')


# ==============================================================================
# RESERVAS (CAIXINHAS)
# ==============================================================================
@app.route('/reservas', methods=['GET', 'POST'])
def reservas():
    if 'logado' not in session: return redirect(url_for('login'))
    conexao = get_db_connection()
    cursor = conexao.cursor()

    if request.method == 'POST':
        if 'novo_objetivo' in request.form:
            try: meta = float(str(request.form.get('meta', '0')).replace(',', '.'))
            except: meta = 0.0
            cursor.execute('INSERT INTO reservas (nome, meta, guardado, usuario_id) VALUES (?, ?, 0, ?)', (request.form.get('nome'), meta, session['user_id']))
        elif 'adicionar_saldo' in request.form:
            try: v = float(str(request.form.get('valor_adicionar', '0')).replace(',', '.'))
            except: v = 0.0
            cursor.execute('UPDATE reservas SET guardado = guardado + ? WHERE id = ? AND usuario_id = ?', (v, request.form.get('id_reserva'), session['user_id']))
        conexao.commit()
        return redirect(url_for('reservas'))

    reservas = cursor.execute('SELECT * FROM reservas WHERE usuario_id = ? ORDER BY id DESC', (session['user_id'],)).fetchall()
    conexao.close()
    return render_template('telas/dividas_planejamento.html', reservas=reservas)

@app.route('/editar_reserva/<int:id>', methods=['POST'])
def editar_reserva(id):
    if 'logado' not in session: return redirect(url_for('login'))
    try: meta = float(str(request.form.get('meta', '0')).replace(',', '.'))
    except: meta = 0.0
    conexao = get_db_connection()
    cursor = conexao.cursor()
    cursor.execute('UPDATE reservas SET nome = ?, meta = ? WHERE id = ? AND usuario_id = ?', (request.form.get('nome'), meta, id, session['user_id']))
    conexao.commit()
    conexao.close()
    return redirect('/reservas')

@app.route('/excluir_reserva/<int:id>', methods=['POST'])
def excluir_reserva(id):
    if 'logado' not in session: return redirect(url_for('login'))
    conexao = get_db_connection()
    cursor = conexao.cursor()
    cursor.execute("DELETE FROM reservas WHERE id = ? AND usuario_id = ?", (id, session['user_id']))
    conexao.commit()
    conexao.close()
    return redirect('/reservas')

from datetime import datetime
from flask import jsonify

@app.route('/lancar_parcela/<int:id_divida>', methods=['POST'])
def lancar_parcela(id_divida):
    if 'logado' not in session and 'usuario' not in session:
        return jsonify({'status': 'erro', 'mensagem': 'Sessão expirada'}), 401

    user_id = session.get('user_id')
    conexao = get_db_connection()
    cursor = conexao.cursor()

    # 1. Puxa os dados do contrato
    cursor.execute("SELECT descricao, valor_parcela FROM dividas WHERE id = ? AND usuario_id = ?", (id_divida, user_id))
    divida = cursor.fetchone()

    if not divida:
        conexao.close()
        return jsonify({'status': 'erro', 'mensagem': 'Contrato não encontrado'}), 404

    # 2. Prepara os dados automáticos
    descricao_gasto = f"Parcela: {divida['descricao']}"
    valor = divida['valor_parcela']
    data_atual = datetime.now().strftime('%Y-%m-%d')
    quinzena = 1 if datetime.now().day <= 15 else 2

    # 3. Injera no fluxo de caixa (amarrado ao divida_id)
    cursor.execute('''
        INSERT INTO gastos (descricao, categoria, valor, quinzena, status, data, usuario_id, divida_id)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    ''', (descricao_gasto, 'Contratos/Dívidas', valor, quinzena, 'PENDENTE', data_atual, user_id, id_divida))

    conexao.commit()
    conexao.close()

    return jsonify({'status': 'sucesso', 'mensagem': 'Parcela adicionada aos gastos do mês!'})

# ==============================================================================
# COMPRAS (LISTA)
# ==============================================================================
def parse_valor(texto, padrao=0.0):
    if not texto: return padrao
    try: return float(str(texto).strip().replace('.', '').replace(',', '.'))
    except: return padrao

@app.route('/compras', methods=['GET', 'POST'])
def compras():
    if not session.get('user_id'): return redirect(url_for('login'))
    mes_atual = datetime.now().strftime('%Y-%m')
    conexao = get_db_connection()
    cursor = conexao.cursor()

    if request.method == 'POST':
        if 'valor_meta' in request.form:
            cursor.execute('INSERT INTO meta_compras (usuario_id, mes, valor) VALUES (?, ?, ?) ON CONFLICT(usuario_id, mes) DO UPDATE SET valor = excluded.valor', (session['user_id'], mes_atual, parse_valor(request.form.get('valor_meta'))))
        elif 'editar' in request.form:
            cursor.execute('UPDATE lista_compras SET descricao=?, quantidade=?, preco=?, total_item=? WHERE id=? AND usuario_id=?',
                           (request.form.get('descricao'), int(request.form.get('quantidade', 1)), parse_valor(request.form.get('preco')), int(request.form.get('quantidade', 1))*parse_valor(request.form.get('preco')), request.form.get('id_item_edit'), session['user_id']))
        else:
            q, p = int(request.form.get('quantidade', 1)), parse_valor(request.form.get('preco'))
            cursor.execute('INSERT INTO lista_compras (usuario_id, descricao, quantidade, preco, total_item, mes) VALUES (?, ?, ?, ?, ?, ?)', (session['user_id'], request.form.get('descricao'), q, p, q*p, mes_atual))
        conexao.commit()
        return redirect('/compras')

    itens_bd = cursor.execute("SELECT * FROM lista_compras WHERE usuario_id = ? AND mes = ?", (session['user_id'], mes_atual)).fetchall()
    itens, total_lista = [], 0.0
    for r in itens_bd:
        d = dict(r)
        d['total_item'] = d.get('total_item') if d.get('total_item') is not None else ((d.get('quantidade') or 1) * (d.get('preco') or 0.0))
        total_lista += d['total_item']
        itens.append(d)

    m = cursor.execute("SELECT valor FROM meta_compras WHERE usuario_id = ? AND mes = ?", (session['user_id'], mes_atual)).fetchone()
    meta = m['valor'] if m else 0.0
    conexao.close()

    return render_template('telas/compras.html', itens=itens, total_lista=total_lista, meta_valor=meta, saldo_meta=meta - total_lista, porcentagem_meta=round((total_lista/meta*100),1) if meta>0 else 0)

@app.route('/excluir_compra/<int:id>', methods=['POST'])
def excluir_compra(id):
    conexao = get_db_connection()
    cursor = conexao.cursor()
    cursor.execute("DELETE FROM lista_compras WHERE id = ? AND usuario_id = ?", (id, session.get('user_id')))
    conexao.commit()
    conexao.close()
    return redirect('/compras')

@app.route('/lancar_compras_gastos', methods=['POST'])
def lancar_compras_gastos():
    try: valor = float(request.form.get('total_compra', 0))
    except: valor = 0.0
    if valor > 0:
        conexao = get_db_connection()
        cursor = conexao.cursor()
        cursor.execute("INSERT INTO gastos (usuario_id, descricao, valor, categoria, data, quinzena, status) VALUES (?, ?, ?, ?, ?, 0, 'PAGO')", (session.get('user_id'), 'Supermercado (Lista de Compras)', valor, 'Alimentação', datetime.now().strftime('%Y-%m-%d')))
        conexao.commit()
        conexao.close()
    return redirect(url_for('home'))

@app.route('/exportar_compras_csv')
def exportar_compras_csv():
    if not session.get('user_id'): return redirect(url_for('login'))
    mes = datetime.now().strftime('%Y-%m')
    conexao = get_db_connection()
    itens = conexao.cursor().execute("SELECT descricao, quantidade, preco FROM lista_compras WHERE usuario_id = ? AND mes = ?", (session['user_id'], mes)).fetchall()
    conexao.close()

    output = io.StringIO()
    output.write('\ufeff')
    writer = csv.writer(output, delimiter=';')
    writer.writerow(['Descrição', 'Quantidade', 'Preço Unitário', 'Total do Item'])
    for i, item in enumerate(itens, 2): writer.writerow([item[0], item[1], str(item[2]).replace('.', ','), f'=B{i}*C{i}'])
    if len(itens) > 0: writer.writerow(['', '', 'TOTAL GERAL:', f'=SOMA(D2:D{len(itens)+1})'])
    return Response(output.getvalue(), mimetype="text/csv; charset=utf-8", headers={"Content-Disposition": f"attachment;filename=lista_{mes}.csv"})

# ==============================================================================
# CHAT BOT - IA HIR3
# ==============================================================================

@app.route('/api/chat_hir3', methods=['POST'])
def chat_hir3():
    if 'user_id' not in session:
        return jsonify({'resposta': 'Sua sessão expirou. Faça login novamente!'}), 401

    dados = request.get_json()
    mensagem_usuario = dados.get('mensagem', '').lower()

    conexao = get_db_connection()
    cursor = conexao.cursor()

    # Prepara o Contexto Financeiro do Mês (AGORA INCLUINDO O STATUS)
    mes_atual = datetime.now().strftime('%Y-%m')
    cursor.execute("SELECT descricao, valor, categoria, status FROM gastos WHERE usuario_id = ? AND data LIKE ?", (session['user_id'], f"{mes_atual}%"))
    gastos_mes = cursor.fetchall()
    conexao.close()

    # Matemática Dinâmica do Mês
    total_gastos = sum(g['valor'] for g in gastos_mes)
    maior_gasto = max(gastos_mes, key=lambda x: x['valor']) if gastos_mes else None

    # Matemática Exclusiva para Pendências
    gastos_pendentes = [g for g in gastos_mes if g['status'] == 'PENDENTE']
    total_pendente = sum(g['valor'] for g in gastos_pendentes)
    qtd_pendentes = len(gastos_pendentes)

    # =======================================================
    # LÓGICA DE INTERPRETAÇÃO (Motor do Chatbot Hir3)
    # =======================================================
    resposta = ""

    if "maior gasto" in mensagem_usuario or "mais gastei" in mensagem_usuario:
        if maior_gasto:
            resposta = f"Seu maior gasto neste mês foi com **{maior_gasto['descricao']}** na categoria <i>{maior_gasto['categoria']}</i>, totalizando **R$ {maior_gasto['valor']:.2f}**. O total do seu mês já está em R$ {total_gastos:.2f}."
        else:
            resposta = "Você ainda não registrou nenhum gasto neste mês. Quer que eu te ensine como fazer um lançamento?"

    # NOVA REGRA: IDENTIFICAÇÃO DE CONTAS PENDENTES
    elif "pendente" in mensagem_usuario or "pendentes" in mensagem_usuario or "falta pagar" in mensagem_usuario or "a pagar" in mensagem_usuario:
        if qtd_pendentes > 0:
            resposta = f"Você tem **{qtd_pendentes} conta(s) pendente(s)** neste mês, totalizando **R$ {total_pendente:.2f}**. Fique de olho no vencimento para evitar multas!"
        else:
            resposta = "Ótima notícia! Você não tem nenhuma conta pendente registrada para este mês. Tudo no azul! 🚀"

    elif "como" in mensagem_usuario and ("meta" in mensagem_usuario or "caixinha" in mensagem_usuario):
        resposta = "Para criar uma meta, vá no menu lateral em <b>Planejamento Financeiro</b> e escolha a aba <b>Caixinhas</b>. Lá você pode dar um nome, definir o valor e eu te ajudo a acompanhar o progresso!"

    elif "suporte" in mensagem_usuario or "ajuda" in mensagem_usuario or "feedback" in mensagem_usuario or "falo com" in mensagem_usuario:
        resposta = "Para falar com suporte humano, você pode usar o botão flutuante verde (WhatsApp) no canto inferior esquerdo da tela, ou enviar um email para a equipe da HIR3 SOLUTIONS. Adoramos receber feedbacks!"

    elif "total" in mensagem_usuario or "resumo" in mensagem_usuario:
        resposta = f"Neste mês, você tem um total de <b>R$ {total_gastos:.2f}</b> em saídas registradas (entre pagas e pendentes). Fique de olho no seu gráfico de fechamento!"

    elif "olá" in mensagem_usuario or "oi" in mensagem_usuario or "tudo bem" in mensagem_usuario:
        resposta = "Olá! Tudo ótimo por aqui. Sou o Hir3, sua IA financeira. Como posso facilitar sua vida hoje?"

    else:
        # Resposta de fallback atualizada com a nova sugestão
        resposta = "Interessante! Como sou uma IA mentora em evolução, ainda estou processando esse tipo de solicitação. Tente me perguntar: <i>'Qual meu maior gasto esse mês?'</i>, <i>'Quanto tenho de contas pendentes?'</i> ou <i>'Como falo com o suporte?'</i>"

    return jsonify({'resposta': resposta})

# ==============================================================================
# RELATÓRIOS E WEBHOOK WHATSAPP
# ==============================================================================
@app.route('/relatorios_avancados')
def relatorios_avancados():
    if 'logado' not in session: return redirect(url_for('login'))
    mes_filtro = request.args.get('mes', datetime.now().strftime('%Y-%m'))

    conexao = get_db_connection()
    cursor = conexao.cursor()
    u = cursor.execute("SELECT licenca FROM usuarios WHERE id = ?", (session['user_id'],)).fetchone()
    if u and u['licenca'] != 'Premium' and session['user_id'] != 1:
        conexao.close()
        return render_template('telas/bloqueado.html')

    gastos = cursor.execute('SELECT * FROM gastos WHERE data LIKE ? AND usuario_id = ? ORDER BY data DESC', (mes_filtro + '%', session['user_id'])).fetchall()
    grafico = cursor.execute('SELECT substr(data, 9, 2) as dia, SUM(valor) as total FROM gastos WHERE data LIKE ? AND usuario_id = ? GROUP BY dia ORDER BY dia', (mes_filtro + '%', session['user_id'])).fetchall()
    dividas = cursor.execute("SELECT * FROM dividas WHERE usuario_id = ?", (session['user_id'],)).fetchall()
    reservas = cursor.execute("SELECT * FROM reservas WHERE usuario_id = ?", (session['user_id'],)).fetchall()
    conexao.close()

    cat_dict = {}
    total_g = 0
    for g in gastos:
        cat_dict[g['categoria']] = cat_dict.get(g['categoria'], 0) + float(g['valor'])
        total_g += float(g['valor'])

    lista_div = []
    for d in dividas:
        div = dict(d)
        div['perc_paga'] = round((d['parcelas_pagas'] / d['total_parcelas']) * 100, 1) if d['total_parcelas'] > 0 else 0
        div['saldo_restante'] = (d['total_parcelas'] - d['parcelas_pagas']) * d['valor_parcela']
        lista_div.append(div)

    return render_template('telas/relatorios_avancados.html', mes_filtro=mes_filtro, dias_grafico=[r['dia'] for r in grafico], valores_grafico=[r['total'] for r in grafico],
        labels_categorias=list(cat_dict.keys()), valores_categorias=list(cat_dict.values()), top3_gastos=sorted(gastos, key=lambda x: float(x['valor']), reverse=True)[:3],
        dividas=lista_div, reservas=reservas, total_q1=0, total_q2=0, perc_pago=0, perc_pendente=0) # Resumido para foco do relatório

def buscar_memoria_hir3(user_id):
    try:
        conexao = get_db_connection()
        h = conexao.cursor().execute("SELECT acao, dados_json FROM ia_comportamento_usuario WHERE usuario_id = ? AND modulo = 'gastos' ORDER BY data_registro DESC LIMIT 10", (user_id,)).fetchall()
        conexao.close()
        if not h: return "Novo."
        return "\n".join([f"- Ação: {a} | Dados: {d}" for a, d in h])
    except: return "Erro."

def analisar_mensagem_com_hir3(texto_usuario, user_id):
    memoria = buscar_memoria_hir3(user_id)
    prompt = f"""Você é 'hir3', assistente financeiro de IA. Memória do usuário:\n{memoria}\nDevolva um JSON.
    1. Registrar gasto: {{"acao": "registrar_gasto", "valor": <float>, "descricao": "", "categoria": "", "quinzena": <int>, "mensagem_hir3": ""}}
    2. Outros: {{"acao": "conversar", "mensagem_hir3": ""}}
    Mensagem: "{texto_usuario}" """
    try:
        r = modelo_hir3.generate_content(prompt)
        return json.loads(r.text.replace('```json', '').replace('```', '').strip())
    except: return {"acao": "conversar", "mensagem_hir3": "Ops, falha no meu servidor!"}

@app.route('/whatsapp-webhook', methods=['GET', 'POST'])
def webhook_whatsapp():
    if request.method == 'GET':
        if request.args.get('hub.mode') == 'subscribe' and request.args.get('hub.verify_token') == TOKEN_VERIFICACAO:
            return request.args.get('hub.challenge'), 200
        return 'Página Ativa', 200

    if request.method == 'POST':
        try:
            msgs = request.json.get('entry', [])[0].get('changes', [])[0].get('value', {}).get('messages', [])
            if msgs:
                tel = msgs[0].get('from')
                txt = msgs[0].get('text', {}).get('body', '').strip()
                conexao = get_db_connection()
                u = conexao.cursor().execute("SELECT id, usuario FROM usuarios WHERE telefone = ?", (tel,)).fetchone()
                if u:
                    decisao = analisar_mensagem_com_hir3(txt, u['id'])
                    if decisao.get('acao') == 'registrar_gasto':
                        conexao.cursor().execute("INSERT INTO gastos (usuario_id, descricao, valor, categoria, status) VALUES (?, ?, ?, ?, 'PAGO')", (u['id'], decisao['descricao'], float(decisao['valor']), decisao['categoria']))
                        conexao.commit()
                conexao.close()
                # Chamada fictícia para enviar_whatsapp(tel, resposta)
        except: pass
        return jsonify({"status": "recebido"}), 200

# ==============================================================================
# CONTEXTOS GLOBAIS E INICIALIZAÇÃO
# ==============================================================================
VERSAO_SISTEMA = "1.6.4" # <--- No futuro, você altera a versão APENAS nesta linha!

@app.context_processor
def inject_global_vars():
    return dict(versao_atual=VERSAO_SISTEMA, data_atual=datetime.now().strftime('%B %Y').capitalize())

# Garante que o banco seja criado e configurado logo antes do app rodar
iniciar_banco()

if __name__ == '__main__':
    app.run(debug=True)