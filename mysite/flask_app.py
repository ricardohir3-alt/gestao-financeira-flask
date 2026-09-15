# ==============================================================================
# 1. IMPORTAÇÕES ORGANIZADAS E SEGURANÇA
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
import traceback
import re
from io import StringIO
from datetime import datetime, timedelta, date
from functools import wraps

import flask
from flask import Flask, render_template, request, redirect, url_for, session, Response, jsonify, flash
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.exceptions import HTTPException

import requests
import pdfplumber
import pytesseract
from PIL import Image
import google.generativeai as genai

# ==============================================================================
# 2. CONFIGURAÇÕES INICIAIS DO FLASK E BANCO DE DADOS
# ==============================================================================

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
# DECORADOR DE SEGURANÇA PARA ROTAS E APIs (O "SEGURANÇA DA PORTA")
# ==============================================================================
def login_obrigatorio(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'logado' not in session:
            # Se for uma requisição de API invisível, devolve erro JSON elegante
            if request.path.startswith('/api/') or request.is_json:
                return jsonify({'status': 'erro', 'mensagem': 'Acesso negado. Faça login.'}), 401
            # Se for tentar acessar a página normal, manda para o login
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

# ==============================================================================
# RASTREADOR DE ATIVIDADE E TRAVA DE SEGURANÇA GLOBAIS
# ==============================================================================
@app.before_request
def verificacoes_globais():
    rotas_livres = ['login', 'static', 'recuperar', 'recuperar_senha', 'cadastro_clientes', 'politica_privacidade', 'termos_uso']

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
chave_gemini = os.environ.get('GEMINI_API_KEY', 'SUA_CHAVE_API_AQUI')
genai.configure(api_key=chave_gemini)
modelo_hir3 = genai.GenerativeModel('gemini-1.5-flash')

TOKEN_VERIFICACAO = "minhas_financas_secreto_123"

# ==============================================================================
# 4. INICIALIZAÇÃO DO BANCO DE DADOS E TABELAS
# ==============================================================================
def iniciar_banco():
    conexao = get_db_connection()
    cursor = conexao.cursor()

    cursor.execute('''CREATE TABLE IF NOT EXISTS erros_diagnosticados (
        id INTEGER PRIMARY KEY AUTOINCREMENT, erro_raw TEXT, diagnostico TEXT,
        sugestao_correcao TEXT, data_criacao DATETIME DEFAULT CURRENT_TIMESTAMP)''')

    # Unificado logs_sistema para ter data_hora e erro_raw corretos
    cursor.execute('''CREATE TABLE IF NOT EXISTS logs_sistema (
        id INTEGER PRIMARY KEY AUTOINCREMENT, data_hora TEXT, erro_raw TEXT,
        diagnostico TEXT, data_criacao DATETIME DEFAULT CURRENT_TIMESTAMP)''')

    cursor.execute('''CREATE TABLE IF NOT EXISTS gastos (
        id INTEGER PRIMARY KEY AUTOINCREMENT, usuario_id INTEGER, descricao TEXT NOT NULL,
        categoria TEXT NOT NULL, valor REAL NOT NULL, quinzena INTEGER NOT NULL,
        status TEXT NOT NULL, data TEXT NOT NULL, divida_id INTEGER DEFAULT NULL)''')

    cursor.execute('''CREATE TABLE IF NOT EXISTS reservas (
        id INTEGER PRIMARY KEY AUTOINCREMENT, usuario_id INTEGER, nome TEXT NOT NULL,
        meta REAL NOT NULL, guardado REAL DEFAULT 0)''')

    # Tabela de Usuários atualizada com sistema de bloqueio de Força Bruta
    cursor.execute('''CREATE TABLE IF NOT EXISTS usuarios (
        id INTEGER PRIMARY KEY AUTOINCREMENT, usuario TEXT UNIQUE NOT NULL,
        senha TEXT NOT NULL, email TEXT, telefone TEXT, licenca TEXT, valor_licencas REAL,
        modulos_liberados TEXT, validade_licenca TEXT, ativo INTEGER DEFAULT 1,
        is_admin INTEGER DEFAULT 0, renda REAL, renda_variavel TEXT, ultimo_mes_acesso TEXT,
        ultimo_acesso TEXT, tentativas_login INTEGER DEFAULT 0, bloqueado_ate DATETIME)''')

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

    # Atualização de segurança: Adiciona controle de Força Bruta nas tabelas antigas (Migration)
    try:
        cursor.execute("ALTER TABLE usuarios ADD COLUMN tentativas_login INTEGER DEFAULT 0")
        cursor.execute("ALTER TABLE usuarios ADD COLUMN bloqueado_ate DATETIME")
    except:
        pass # Ignora silenciosamente se as colunas já existirem no banco

    # Criação do Admin Mestre Inicial
    cursor.execute("SELECT * FROM usuarios WHERE usuario = 'admin'")
    if not cursor.fetchone():
        senha_criptografada = generate_password_hash('123')
        cursor.execute("INSERT INTO usuarios (usuario, senha, is_admin, ativo) VALUES ('admin', ?, 1, 1)", (senha_criptografada,))

    conexao.commit()
    conexao.close()

# ==============================================================================
# LOGS E CORREÇÃO DE ERROS (A TELA DE MANUTENÇÃO ELEGANTE)
# ==============================================================================
@app.errorhandler(Exception)
def handle_exception(e):
    # Se for um erro padrão de rota (ex: 404), mostra a tela sem gravar log
    if isinstance(e, HTTPException):
        return render_template('erro.html', codigo=e.code), e.code

    # Se for erro fatal no banco ou código, capta a "Caixa Preta"
    erro_raw = traceback.format_exc()
    print(f"ERRO INTERNO DETECTADO: {e}")

    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        agora = datetime.now().strftime('%d/%m/%Y %H:%M:%S')

        # Salva silenciosamente no banco
        cursor.execute('INSERT INTO logs_sistema (data_hora, erro_raw) VALUES (?, ?)', (agora, erro_raw))
        conn.commit()
        conn.close()
    except:
        pass # Ignora se o próprio DB estiver com erro

    # Mostra a tela amigável (erro.html) em vez da tela de código feio do Flask
    return render_template('erro.html', codigo=500), 500


# ==============================================================================
# ROTA DE LOGIN, LOGOUT E RECUPERAÇÃO DE SENHAS
# ==============================================================================
def is_senha_forte(senha):
    if len(senha) < 6: return False
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
                if dict_usuario.get('licenca') in ['Bloqueada', 'Inativa', 'Vencida']:
                    return render_template('login.html', erro="Acesso Negado: Sua licença está inativa.", sucesso=sucesso)
                if dict_usuario.get('ativo') == 0:
                    return render_template('login.html', erro="Acesso Negado: Seu usuário foi desativado.", sucesso=sucesso)

                hoje = date.today().strftime('%Y-%m-%d')
                validade = dict_usuario.get('validade_licenca')
                if validade and validade not in ['None', '']:
                    if hoje > validade:
                        return redirect(url_for('assinatura_vencida'))

            # Inicializa sessão do usuário
            session['logado'] = True
            session['user_id'] = usuario_banco['id']
            session['usuario'] = usuario_banco['usuario']
            session['nome'] = usuario_banco['usuario']

            is_admin_db = dict_usuario.get('is_admin', 0)
            session['is_admin'] = (usuario_banco['id'] == 1 or is_admin_db == 1)
            session.permanent = bool(manter_conectado)

            if not is_senha_forte(senha_digitada):
                session['precisa_trocar_senha'] = True
                return redirect(url_for('forcar_troca_senha'))

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
                if not is_senha_forte(nova_senha):
                    erro = "A nova senha deve ter no mínimo 6 caracteres, letras maiúsculas, minúsculas e números."
                else:
                    nova_senha_hash = generate_password_hash(nova_senha)
                    cursor.execute('UPDATE usuarios SET senha = ? WHERE usuario = ?', (nova_senha_hash, usuario_banco['usuario']))
                    conexao.commit()
                    conexao.close()
                    return redirect(url_for('login', sucesso="Senha atualizada com segurança! Faça login novamente."))
            else:
                erro = "A senha atual está incorreta. Operação cancelada!"
        else:
            erro = "Usuário não encontrado no sistema!"
        conexao.close()
    return render_template('telas/recuperar.html', erro=erro)

@app.route('/forcar_troca_senha', methods=['GET', 'POST'])
def forcar_troca_senha():
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
            conexao = get_db_connection()
            cursor = conexao.cursor()
            nova_senha_hash = generate_password_hash(nova_senha)
            cursor.execute('UPDATE usuarios SET senha = ? WHERE id = ?', (nova_senha_hash, session['user_id']))
            conexao.commit()
            conexao.close()

            session.pop('precisa_trocar_senha', None)
            return redirect(url_for('home'))

    return render_template('telas/forcar_senha.html', erro=erro)

# ==============================================================================
# PÁGINAS LEGAIS E CADASTRO
# ==============================================================================
@app.route('/politica_privacidade')
def politica_privacidade():
    return render_template('telas/politica.html')

@app.route('/termos_uso')
def termos_uso():
    return render_template('telas/termos.html')

@app.route('/cadastro_clientes', methods=['POST'])
def cadastro_clientes():
    usuario = request.form.get('usuario')
    email = request.form.get('email')
    senha = request.form.get('senha')
    senha_confirmacao = request.form.get('senha_confirmacao')

    if email:
        email = email.strip()
        if email == "": email = None
    else:
        email = None

    if not usuario or not senha:
        return render_template('login.html', erro="Preencha todos os campos obrigatórios do cadastro!")

    if senha != senha_confirmacao:
        return render_template('login.html', erro="As senhas digitadas não coincidem!")

    conn = get_db_connection()
    cursor = conn.cursor()

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

    senha_hash = generate_password_hash(senha)

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
    return redirect(url_for('login'))

# ==============================================================================
# DASHBOARD PRINCIPAL E SISTEMA DE NOTIFICAÇÕES
# ==============================================================================
def carregar_notificacoes_usuario(usuario_id):
    try:
        conexao = get_db_connection()
        cursor = conexao.cursor()

        cursor.execute("""
            SELECT id, titulo, mensagem, lida, data_criacao, icone, cor
            FROM notificacoes
            WHERE usuario_id = ?
            ORDER BY id DESC LIMIT 10
        """, (usuario_id,))

        rows = cursor.fetchall()
        notificacoes_list = []
        total_nao_lidas = 0

        for r in rows:
            is_dict = hasattr(r, 'keys')
            notif = {
                'id': r['id'] if is_dict else r[0],
                'titulo': r['titulo'] if is_dict else r[1],
                'mensagem': r['mensagem'] if is_dict else r[2],
                'lida': r['lida'] if is_dict else r[3],
                'data_criacao': r['data_criacao'] if is_dict else r[4],
                'icone': r['icone'] if is_dict else (r[5] if len(r) > 5 and r[5] else 'bell'),
                'cor': r['cor'] if is_dict else (r[6] if len(r) > 6 and r[6] else 'indigo')
            }
            notificacoes_list.append(notif)
            if notif['lida'] == 0: total_nao_lidas += 1

        conexao.close()
        return notificacoes_list, total_nao_lidas
    except Exception as e:
        print(f"Erro ao carregar notificações: {e}")
        return [], 0

@app.context_processor
def injetar_notificacoes_globais():
    if 'logado' in session and session.get('user_id'):
        notificacoes_list, total_nao_lidas = carregar_notificacoes_usuario(session.get('user_id'))
        return dict(notificacoes=notificacoes_list, total_notificacoes=total_nao_lidas)
    return dict(notificacoes=[], total_notificacoes=0)

def verificar_virada_de_mes(user_id):
    mes_atual = datetime.now().strftime('%Y-%m')
    conexao = get_db_connection()
    cursor = conexao.cursor()
    cursor.execute("SELECT ultimo_mes_acesso, renda_variavel FROM usuarios WHERE id = ?", (user_id,))
    resultado = cursor.fetchone()

    if resultado:
        is_dict = hasattr(resultado, 'keys')
        ultimo_mes = resultado['ultimo_mes_acesso'] if is_dict else resultado[0]
        renda_variavel = resultado['renda_variavel'] if is_dict else resultado[1]

        if ultimo_mes != mes_atual:
            if renda_variavel == 'sim':
                cursor.execute("UPDATE usuarios SET renda = 0.00, ultimo_mes_acesso = ? WHERE id = ?", (mes_atual, user_id))
            else:
                cursor.execute("UPDATE usuarios SET ultimo_mes_acesso = ? WHERE id = ?", (mes_atual, user_id))
            conexao.commit()
    conexao.close()

@app.route('/', methods=['GET'])
@login_obrigatorio
def home():
    user_id = session.get('user_id')
    verificar_virada_de_mes(user_id)

    conexao = get_db_connection()
    cursor = conexao.cursor()

    cursor.execute("SELECT renda, renda_variavel FROM usuarios WHERE id = ?", (user_id,))
    resultado_usuario = cursor.fetchone()

    mes_atual_real = datetime.now().strftime('%Y-%m')
    mes_filtro = request.args.get('mes', mes_atual_real)

    # 1. PEGA A RENDA FIXA BASE
    try:
        cursor.execute("SELECT valor FROM renda WHERE mes = ? AND usuario_id = ?", (mes_filtro, user_id))
        resultado_renda = cursor.fetchone()
    except Exception:
        resultado_renda = None

    renda_base = 0.00
    if resultado_renda:
        is_dict = hasattr(resultado_renda, 'keys')
        renda_base = float(resultado_renda['valor'] if is_dict else resultado_renda[0])
    else:
        try:
            is_dict_usr = hasattr(resultado_usuario, 'keys') if resultado_usuario else False
            usr_renda_var = resultado_usuario['renda_variavel'] if is_dict_usr else (resultado_usuario[1] if resultado_usuario else None)
            usr_renda_fixa = resultado_usuario['renda'] if is_dict_usr else (resultado_usuario[0] if resultado_usuario else None)

            if mes_filtro > mes_atual_real and resultado_usuario and usr_renda_var == 'sim':
                renda_base = 0.00
            elif resultado_usuario and usr_renda_fixa is not None:
                renda_base = float(usr_renda_fixa)
        except (ValueError, TypeError):
            renda_base = 0.00

    # 2. BUSCA TODAS AS MOVIMENTAÇÕES (RECEITAS E DESPESAS)
    # Usa IFNULL para garantir compatibilidade caso a coluna 'tipo' ainda não esteja em todos os registros
    cursor.execute('''SELECT id, descricao, categoria, valor, quinzena, status, data, divida_id, IFNULL(tipo, "despesa") as tipo
                      FROM gastos WHERE data LIKE ? AND usuario_id = ? ORDER BY data DESC''', (mes_filtro + '%', user_id))
    lista_movimentos_raw = cursor.fetchall()

    lista_movimentos = []
    if lista_movimentos_raw and hasattr(lista_movimentos_raw[0], 'keys'):
        lista_movimentos = [dict(row) for row in lista_movimentos_raw]
    else:
        lista_movimentos = [{'id': g[0], 'descricao': g[1], 'categoria': g[2], 'valor': g[3], 'quinzena': g[4], 'status': g[5], 'data': g[6], 'divida_id': g[7], 'tipo': g[8]} for g in lista_movimentos_raw] if lista_movimentos_raw else []

    # 3. SEPARAÇÃO E SOMA INTELIGENTE DE VALORES
    total_gastos = sum(float(g.get('valor', 0)) for g in lista_movimentos if g.get('tipo', 'despesa') == 'despesa')
    total_receitas_extras = sum(float(g.get('valor', 0)) for g in lista_movimentos if g.get('tipo') == 'receita')

    # A renda real do mês é a Fixa + As extras
    renda_atual = renda_base + total_receitas_extras

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

        # Compara apenas DESPESAS do mês passado
        cursor.execute("SELECT SUM(valor) as total FROM gastos WHERE data LIKE ? AND usuario_id = ? AND (tipo = 'despesa' OR tipo IS NULL)", (mes_passado_str + '%', user_id))
        resultado_passado = cursor.fetchone()

        is_dict = hasattr(resultado_passado, 'keys') if resultado_passado else False
        val_passado = resultado_passado['total'] if is_dict else (resultado_passado[0] if resultado_passado else None)

        total_passado = float(val_passado) if val_passado else 0.0
    except Exception:
        total_passado = 0.0

    # Gráfico só exibe as despesas
    cursor.execute('''SELECT substr(data, 9, 2) as dia, SUM(valor) as total FROM gastos
                      WHERE data LIKE ? AND usuario_id = ? AND (tipo = 'despesa' OR tipo IS NULL) GROUP BY dia ORDER BY dia''', (mes_filtro + '%', user_id))
    dados_grafico = cursor.fetchall()

    dias_grafico = []
    valores_grafico = []
    for row in dados_grafico:
        is_dict = hasattr(row, 'keys')
        dias_grafico.append(row['dia'] if is_dict else row[0])
        valores_grafico.append(float(row['total'] if is_dict else row[1]))

    cursor.execute("SELECT valor_fatura, data_vencimento FROM cobrancas WHERE usuario_id = ? AND status_pagamento = 'PENDENTE'", (user_id,))
    fatura_pendente = cursor.fetchone()

    conexao.close()

    # Filtra apenas os gastos puros para os cálculos de Donut, Top 3 e Quinzenas
    gastos_puros = [g for g in lista_movimentos if g.get('tipo', 'despesa') == 'despesa']

    categorias_dict = {}
    for g in gastos_puros:
        cat = g.get('categoria', 'Outros')
        categorias_dict[cat] = categorias_dict.get(cat, 0) + float(g.get('valor', 0))

    total_q1 = sum(float(g.get('valor', 0)) for g in gastos_puros if str(g.get('quinzena', '')) == '1')
    total_q2 = sum(float(g.get('valor', 0)) for g in gastos_puros if str(g.get('quinzena', '')) == '2')
    perc_q1 = round((total_q1 / total_gastos * 100), 1) if total_gastos > 0 else 0
    perc_q2 = round((total_q2 / total_gastos * 100), 1) if total_gastos > 0 else 0

    total_pago = sum(float(g.get('valor', 0)) for g in gastos_puros if str(g.get('status', '')).upper() == 'PAGO')
    total_pendente = total_gastos - total_pago

    if total_gastos > 0:
        perc_pago = round((total_pago / total_gastos * 100), 1)
        perc_pendente = round((100.0 - perc_pago), 1)
    else:
        perc_pago = 0
        perc_pendente = 0

    top3_gastos = sorted(gastos_puros, key=lambda x: float(x.get('valor', 0)), reverse=True)[:3]
    disponivel_geral = renda_atual - total_gastos

    def fmt(v): return f"{v:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")

    diferenca_mensal = total_passado - total_gastos

    if total_passado > 0:
        percentual = round((abs(diferenca_mensal) / total_passado) * 100, 1)
    elif total_gastos > 0:
        percentual = 100.0
    else:
        percentual = 0.0

    comparativo = {
        'total_atual': fmt(total_gastos),
        'total_passado': fmt(total_passado),
        'diferenca_absoluta': fmt(abs(diferenca_mensal)),
        'economizou': diferenca_mensal > 0,
        'excedeu': diferenca_mensal < 0,
        'percentual': f"{percentual}".replace('.', ',')
    }

    return render_template('index.html',
                           renda_total=fmt(renda_atual), gastos_totais=fmt(total_gastos),
                           valor_disponivel=fmt(disponivel_geral), gastos=lista_movimentos,
                           mes_filtro=mes_filtro, dias_grafico=dias_grafico, valores_grafico=valores_grafico,
                           labels_categorias=list(categorias_dict.keys()), valores_categorias=list(categorias_dict.values()),
                           perc_q1=perc_q1, perc_q2=perc_q2, total_q1=fmt(total_q1), total_q2=fmt(total_q2),
                           perc_pago=perc_pago, perc_pendente=perc_pendente,
                           total_pago=fmt(total_pago), total_pendente=fmt(total_pendente),
                           top3_gastos=top3_gastos, fatura_pendente=fatura_pendente,
                           comparativo=comparativo,
                           versao_atual="1.6.6")

@app.route('/historico_notificacoes')
@login_obrigatorio
def historico_notificacoes():
    conexao = get_db_connection()
    cursor = conexao.cursor()
    cursor.execute('SELECT * FROM notificacoes WHERE usuario_id = ? ORDER BY data_criacao DESC', (session['user_id'],))

    # Tratamento para dict
    notificacoes_historico = [dict(row) for row in cursor.fetchall()] if cursor.description else []

    conexao.close()
    return render_template('telas/historico_notificacoes.html', notificacoes=notificacoes_historico)

# ==============================================================================
# GESTÃO DE USUÁRIOS E ADMINISTRAÇÃO
# ==============================================================================

@app.route('/usuarios', methods=['GET', 'POST'])
@login_obrigatorio
def usuarios():
    if not session.get('is_admin'):
        return redirect(url_for('home'))

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
            except sqlite3.IntegrityError:
                pass

        elif 'editar' in request.form:
            id_edit = request.form.get('id_usuario_edit')
            novo_nome = request.form.get('novo_nome')
            nova_licenca = request.form.get('nova_licenca')
            try:
                novo_valor = float(str(request.form.get('novo_valor', '0')).replace(',', '.'))
            except ValueError:
                novo_valor = 0.00
            novos_modulos = request.form.get('novos_modulos', 'Todos')

            try:
                cursor.execute("UPDATE usuarios SET usuario=?, licenca=?, valor_licencas=?, modulos_liberados=? WHERE id=?", (novo_nome, nova_licenca, novo_valor, novos_modulos, id_edit))
                conexao.commit()
            except:
                pass

        elif 'excluir' in request.form:
            id_del = request.form.get('id_usuario')
            try:
                cursor.execute("UPDATE usuarios SET ativo = 0 WHERE id = ? AND id != 1", (id_del,))
                conexao.commit()
            except:
                pass

    cursor.execute("SELECT id, usuario, licenca, valor_licencas, modulos_liberados, validade_licenca, email, ultimo_acesso FROM usuarios WHERE ativo = 1 OR ativo IS NULL")
    rows = cursor.fetchall()

    agora = datetime.now()
    lista_users = []

    for r in rows:
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
                if (agora - data_acesso) < timedelta(minutes=5):
                    is_online = True
            except:
                pass

        lista_users.append((uid, unome, ulic, uval, umod, uvalid, uemail, is_online))

    try:
        cursor.execute("SELECT * FROM logs_sistema ORDER BY id DESC LIMIT 50")
        logs = [dict(zip([column[0] for column in cursor.description], row)) for row in cursor.fetchall()]
    except Exception as e:
        print(f"Error fetching logs: {e}")
        logs = []

    conexao.close()

    db_size_mb = round(os.path.getsize(DB_PATH) / (1024 * 1024), 2) if os.path.exists(DB_PATH) else 0.0
    try:
        disk_percent = int((shutil.disk_usage("/")[1] / shutil.disk_usage("/")[0]) * 100)
    except:
        disk_percent = 0

    sys_info = {
        'db_size': str(db_size_mb).replace('.', ','),
        'uploads_size': "0,00",
        'disk_percent': disk_percent,
        'python_version': platform.python_version(),
        'flask_version': flask.__version__,
        'app_version': "v1.6.6"
    }

    # TRAVA DO AJAX APLICADA AQUI
    is_ajax = request.args.get('modal') == 'true'
    return render_template('telas/gestao_usuarios.html', usuarios=lista_users, logs=logs, sys_info=sys_info, ajax_request=is_ajax)

@app.route('/api/inativar_usuario/<int:id_usuario>', methods=['POST'])
@login_obrigatorio
def api_inativar_usuario(id_usuario):
    if not session.get('is_admin'): return jsonify({'status': 'erro', 'mensagem': 'Acesso restrito.'}), 403
    try:
        conexao = get_db_connection()
        cursor = conexao.cursor()
        cursor.execute('UPDATE usuarios SET ativo = 0 WHERE id = ? AND id != 1', (id_usuario,))
        conexao.commit()
        conexao.close()
        return jsonify({'status': 'sucesso', 'mensagem': 'Usuário inativado com sucesso!'})
    except Exception as e: return jsonify({'status': 'erro', 'mensagem': str(e)})

@app.route('/api/editar_usuario/<int:id_usuario>', methods=['POST'])
@login_obrigatorio
def api_editar_usuario(id_usuario):
    if not session.get('is_admin'): return jsonify({'status': 'erro', 'mensagem': 'Acesso restrito.'}), 403
    dados = request.json
    try: novo_valor = float(str(dados.get('valor_diario', dados.get('valor', '0'))).replace(',', '.'))
    except ValueError: novo_valor = 0.00
    nova_validade = dados.get('nova_validade', '2099-12-31')

    email = dados.get('email')
    if email:
        email = email.strip()
        if email == "": email = None

    try:
        conexao = get_db_connection()
        cursor = conexao.cursor()
        cursor.execute("""UPDATE usuarios SET usuario=?, email=?, licenca=?, valor_licencas=?, modulos_liberados=?, validade_licenca=? WHERE id=?""",
                       (dados['nome'], email, dados['licenca'], novo_valor, dados['modulos'], nova_validade, id_usuario))
        conexao.commit()
        conexao.close()
        return jsonify({'status': 'sucesso', 'mensagem': 'Dados atualizados com sucesso!'})
    except Exception as e: return jsonify({'status': 'erro', 'mensagem': str(e)})

@app.route('/analisar_erro/<int:log_id>', methods=['POST'])
@login_obrigatorio
def analisar_erro(log_id):
    if not session.get('is_admin'):
        return redirect(url_for('home'))

    try:
        conexao = get_db_connection()
        cursor = conexao.cursor()
        cursor.execute('SELECT erro_raw FROM logs_sistema WHERE id = ?', (log_id,))
        erro_banco = cursor.fetchone()

        if erro_banco:
            erro_raw = erro_banco[0] if isinstance(erro_banco, tuple) else erro_banco['erro_raw']
            prompt = f"Você é o Hir3, o engenheiro de IA do Meu Controle Financeiro. Analise o seguinte erro do Python/Flask e explique em português MUITO simples, em até 2 frases, qual é o problema e como o desenvolvedor Ricardo deve resolver. Não use jargões difíceis. Erro: {erro_raw}"
            resposta_ia = modelo_hir3.generate_content(prompt).text
            cursor.execute('UPDATE logs_sistema SET diagnostico = ? WHERE id = ?', (resposta_ia, log_id))
            conexao.commit()

        conexao.close()
    except Exception as e:
        print(f"Falha na IA: {e}")

    return redirect(url_for('usuarios'))

@app.route('/licencas', methods=['GET', 'POST'])
@login_obrigatorio
def licencas():
    if session.get('user_id') != 1: return "Acesso negado", 403

    conexao = get_db_connection()
    cursor = conexao.cursor()
    if request.method == 'POST':
        try: novo_valor = float(str(request.form.get('valor_licencas', '0')).replace(',', '.'))
        except: novo_valor = 0.00
        cursor.execute("UPDATE usuarios SET licenca = ?, valor_licencas = ? WHERE id = ?", (request.form.get('nova_licenca'), novo_valor, request.form.get('id_usuario')))
        conexao.commit()
        return redirect(url_for('licencas'))

    cursor.execute("SELECT COUNT(*) as total FROM usuarios WHERE ativo = 1 OR ativo IS NULL")
    total_result = cursor.fetchone()
    total_usuarios = total_result['total'] if hasattr(total_result, 'keys') else total_result[0]

    cursor.execute("SELECT id, usuario, licenca, valor_licencas FROM usuarios WHERE id != 1 AND (ativo = 1 OR ativo IS NULL)")
    lista_usuarios = cursor.fetchall()
    conexao.close()
    return render_template('telas/licencas.html', total_usuarios=total_usuarios, usuarios=lista_usuarios)

@app.route('/assinatura_vencida')
def assinatura_vencida():
    session.clear()
    return render_template('telas/licencas_vencidas.html')

@app.route('/tornar_admin/<int:id>', methods=['POST'])
@login_obrigatorio
def tornar_admin(id):
    if session.get('user_id') != 1: return redirect(url_for('usuarios'))
    try:
        conexao = get_db_connection()
        cursor = conexao.cursor()
        cursor.execute("UPDATE usuarios SET is_admin = 1 WHERE id = ?", (id,))
        conexao.commit()
        conexao.close()
    except:
        pass
    return redirect(url_for('usuarios'))

# ==============================================================================
# PAINEL FINANCEIRO / EXTRATOS B2B
# ==============================================================================
@app.route('/financeiro')
@login_obrigatorio
def financeiro():
    if not session.get('is_admin'): return redirect(url_for('home'))
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
@login_obrigatorio
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

@app.route('/renovar_cobranca', methods=['POST'])
@login_obrigatorio
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
# ROTA 1: SALVAR FATURA PIX GERADA (NOVA)
# ==============================================================================
@app.route('/api/salvar_fatura', methods=['POST'])
@login_obrigatorio
def salvar_fatura():
    if not session.get('is_admin'):
        return jsonify({'sucesso': False, 'erro': 'Não autorizado'}), 403

    dados = request.get_json()
    usuario_id = dados.get('usuario_id')
    valor = dados.get('valor')

    if not usuario_id or not valor:
        return jsonify({'sucesso': False, 'erro': 'Dados incompletos'}), 400

    try:
        conn = sqlite3.connect('database.db')
        cursor = conn.cursor()
        hoje = datetime.now().strftime('%Y-%m-%d')

        # Cria a fatura como "Pendente" hoje mesmo
        cursor.execute('''
            INSERT INTO cobrancas (usuario_id, valor_fatura, data_vencimento, status_pagamento)
            VALUES (?, ?, ?, 'Pendente')
        ''', (usuario_id, valor, hoje))

        conn.commit()
        conn.close()
        return jsonify({'sucesso': True})
    except Exception as e:
        return jsonify({'sucesso': False, 'erro': str(e)}), 500

# ==============================================================================
# ROTA 2: MARCAR COMO PAGO E RENOVAR 30 DIAS (ATUALIZADA)
# ==============================================================================
@app.route('/marcar_pago/<int:cob_id>', methods=['POST'])
@login_obrigatorio
def marcar_pago(cob_id):
    if not session.get('is_admin'):
        flash('Acesso restrito.', 'erro')
        return redirect(url_for('home'))

    id_usuario_retorno = request.form.get('id_usuario_retorno')

    try:
        conn = sqlite3.connect('database.db')
        cursor = conn.cursor()
        hoje = datetime.now().strftime('%Y-%m-%d')

        # 1. Descobrir de quem é essa cobrança
        cursor.execute('SELECT usuario_id FROM cobrancas WHERE id = ?', (cob_id,))
        resultado = cursor.fetchone()

        if resultado:
            usuario_id = resultado[0]

            # 2. Atualiza a fatura para "Em Dia" (Paga)
            cursor.execute('''
                UPDATE cobrancas
                SET status_pagamento = 'Em Dia', data_pagamento = ?
                WHERE id = ?
            ''', (hoje, cob_id))

            # 3. MÁGICA: Puxar a licença atual do cliente e somar +30 dias
            cursor.execute('SELECT vencimento_licenca FROM usuarios WHERE id = ?', (usuario_id,))
            user_data = cursor.fetchone()

            if user_data and user_data[0]:
                try:
                    venc_atual = datetime.strptime(user_data[0], '%Y-%m-%d')
                except ValueError:
                    venc_atual = datetime.now()
            else:
                venc_atual = datetime.now()

            # Se a licença dele já tinha vencido no passado, damos 30 dias limpos a partir de HOJE.
            # Se ainda não venceu, somamos +30 dias no que ele já tem.
            if venc_atual < datetime.now():
                novo_vencimento = datetime.now() + timedelta(days=30)
            else:
                novo_vencimento = venc_atual + timedelta(days=30)

            cursor.execute('UPDATE usuarios SET vencimento_licenca = ? WHERE id = ?', (novo_vencimento.strftime('%Y-%m-%d'), usuario_id))

        conn.commit()
        conn.close()
        flash('Pagamento confirmado! A fatura foi para o histórico e a Licença estendida em +30 dias.', 'sucesso')
    except Exception as e:
        flash(f'Erro ao processar pagamento: {e}', 'erro')

    # Retorna para a tela de onde o admin clicou
    if id_usuario_retorno:
        return redirect(url_for('financeiro', id_usuario=id_usuario_retorno))
    return redirect(url_for('financeiro'))

# ==============================================================================
# API: EXPORTAR CLIENTES (MASTER DASHBOARD)
# ==============================================================================
@app.route('/api/exportar_clientes')
@login_obrigatorio
def api_exportar_clientes():
    if not session.get('is_admin'):
        return "Acesso negado", 403

    try:
        conexao = get_db_connection()
        cursor = conexao.cursor()
        # Puxa todo mundo menos o admin master (id=1)
        cursor.execute("SELECT id, usuario, email, licenca, valor_licencas, validade_licenca FROM usuarios WHERE id != 1 AND (ativo = 1 OR ativo IS NULL)")
        rows = cursor.fetchall()
        conexao.close()

        # Cria o arquivo em memória
        si = StringIO()
        # Usamos ponto e vírgula pois o Excel no Brasil usa isso para separar as colunas
        cw = csv.writer(si, delimiter=';')

        # Escreve o Cabeçalho
        cw.writerow(['ID', 'Cliente', 'Email', 'Licenca', 'Valor Mensal (R$)', 'Vencimento'])

        # Escreve os Dados
        for r in rows:
            is_dict = hasattr(r, 'keys')
            uid = r['id'] if is_dict else r[0]
            unome = r['usuario'] if is_dict else r[1]
            uemail = r['email'] if is_dict else r[2]
            ulic = r['licenca'] if is_dict else r[3]
            uval = r['valor_licencas'] if is_dict else r[4]
            uvalid = r['validade_licenca'] if is_dict else r[5]

            valor_formatado = f"{float(uval):.2f}".replace('.', ',') if uval else "0,00"

            cw.writerow([uid, unome, uemail or 'Sem email', ulic, valor_formatado, uvalid or 'Indeterminado'])

        # O \ufeff (BOM do UTF-8) força o Excel a ler os acentos corretamente
        output = '\ufeff' + si.getvalue()

        return Response(
            output,
            mimetype="text/csv",
            headers={"Content-Disposition": "attachment;filename=carteira_de_clientes.csv"}
        )
    except Exception as e:
        return f"Erro ao exportar: {str(e)}", 500

# ==============================================================================
# API: TRAVAR INADIMPLENTES EM LOTE (MASTER DASHBOARD)
# ==============================================================================
@app.route('/api/travar_inadimplentes', methods=['POST'])
@login_obrigatorio
def api_travar_inadimplentes():
    if not session.get('is_admin'):
        return jsonify({'status': 'erro', 'mensagem': 'Acesso negado'}), 403

    try:
        conexao = get_db_connection()
        cursor = conexao.cursor()
        hoje = datetime.now().strftime('%Y-%m-%d')

        # A Mágica: Procura todo mundo que está com a validade menor que hoje (e não é o Admin 1)
        # E zera os módulos deles, além de mudar o status da licença para "Vencida"
        cursor.execute("""
            UPDATE usuarios
            SET licenca = 'Vencida', modulos_liberados = 'Bloqueado'
            WHERE validade_licenca < ? AND validade_licenca != '' AND id != 1 AND (ativo = 1 OR ativo IS NULL)
        """, (hoje,))

        linhas_afetadas = cursor.rowcount
        conexao.commit()
        conexao.close()

        return jsonify({
            'status': 'sucesso',
            'mensagem': f'{linhas_afetadas} clientes inadimplentes foram bloqueados com sucesso!'
        })
    except Exception as e:
        return jsonify({'status': 'erro', 'mensagem': str(e)}), 500

# ==============================================================================
# API E SISTEMA DE ALERTA GERAL (BROADCAST)
# ==============================================================================

# 1. Cria a tabela de alertas caso não exista automaticamente
try:
    _conn = get_db_connection()
    _conn.execute('''CREATE TABLE IF NOT EXISTS alerta_geral (id INTEGER PRIMARY KEY CHECK(id=1), mensagem TEXT, ativo INTEGER DEFAULT 0)''')
    _conn.execute('INSERT OR IGNORE INTO alerta_geral (id, mensagem, ativo) VALUES (1, "", 0)')
    _conn.commit()
    _conn.close()
except: pass

# 2. Injeta o Alerta no HTML de TODOS os usuários
@app.context_processor
def injetar_alerta_global():
    try:
        conexao = get_db_connection()
        cursor = conexao.cursor()
        cursor.execute('SELECT mensagem, ativo FROM alerta_geral WHERE id = 1')
        alerta = cursor.fetchone()
        conexao.close()

        # Lê independente se é dict ou tupla
        ativo = alerta['ativo'] if hasattr(alerta, 'keys') else alerta[1]
        mensagem = alerta['mensagem'] if hasattr(alerta, 'keys') else alerta[0]

        if ativo == 1:
            return {'alerta_global': mensagem}
    except: pass
    return {'alerta_global': None}

# 3. Rota para Salvar e Disparar
@app.route('/api/salvar_alerta', methods=['POST'])
@login_obrigatorio
def api_salvar_alerta():
    if not session.get('is_admin'): return jsonify({'status': 'erro', 'mensagem': 'Acesso negado'}), 403
    mensagem = request.json.get('mensagem', '').strip()

    if not mensagem: return jsonify({'status': 'erro', 'mensagem': 'A mensagem não pode ser vazia.'})

    try:
        conexao = get_db_connection()
        cursor = conexao.cursor()
        cursor.execute("UPDATE alerta_geral SET mensagem = ?, ativo = 1 WHERE id = 1", (mensagem,))
        conexao.commit()
        conexao.close()
        return jsonify({'status': 'sucesso'})
    except Exception as e: return jsonify({'status': 'erro', 'mensagem': str(e)})

# 4. Rota para Desligar (Limpar)
@app.route('/api/limpar_alerta', methods=['POST'])
@login_obrigatorio
def api_limpar_alerta():
    if not session.get('is_admin'): return jsonify({'status': 'erro', 'mensagem': 'Acesso negado'}), 403
    try:
        conexao = get_db_connection()
        cursor = conexao.cursor()
        cursor.execute("UPDATE alerta_geral SET ativo = 0 WHERE id = 1")
        conexao.commit()
        conexao.close()
        return jsonify({'status': 'sucesso'})
    except Exception as e: return jsonify({'status': 'erro', 'mensagem': str(e)})

# ==============================================================================
# PERFIL E ATUALIZAÇÕES
# ==============================================================================
@app.route('/perfil', methods=['GET', 'POST'])
@login_obrigatorio
def perfil():
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

# ==============================================================================
# NOVIDADES E ATUALIZAÇÕES
# ==============================================================================
@app.route('/atualizacoes')
@login_obrigatorio
def atualizacoes():
    is_ajax = request.args.get('modal') == 'true'
    return render_template('telas/atualizacoes.html', ajax_request=is_ajax)

# ==============================================================================
# ATUALIZAR RENDA DO MÊS
# ==============================================================================
@app.route('/renda', methods=['POST'])
@login_obrigatorio
def atualizar_renda():
    try:
        # 1. Pega o valor (agora aceita 'renda_base' do antigo ou 'renda' do Modal)
        renda_form = request.form.get('renda_base') or request.form.get('renda')

        # 2. Pega o mês. Se vier do Modal, ele chega vazio. Vamos puxar da URL (referrer) ou usar o atual!
        mes_filtro = request.form.get('mes_filtro')
        if not mes_filtro:
            if request.referrer and 'mes=' in request.referrer:
                mes_filtro = request.referrer.split('mes=')[1].split('&')[0]
            else:
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
# GASTOS E LANÇAMENTOS
# ==============================================================================
def registrar_aprendizado_ia(user_id, modulo, acao, dados):
    try:
        conexao = get_db_connection()
        cursor = conexao.cursor()
        cursor.execute("INSERT INTO ia_comportamento_usuario (usuario_id, modulo, acao, dados_json) VALUES (?, ?, ?, ?)", (user_id, modulo, acao, json.dumps(dados)))
        conexao.commit()
    except Exception as e: print(f"[IA] Erro: {e}")
    finally: conexao.close()

# ==========================================
# ROTA ATUALIZADA: MOVIMENTAÇÕES (Receitas e Despesas)
# ==========================================
@app.route('/movimentacoes', methods=['GET', 'POST'])
@login_obrigatorio
def movimentacoes():
    if request.method == 'POST':
        try:
            try:
                valor = float(str(request.form.get('valor', '0')).replace(',', '.'))
            except ValueError:
                valor = 0.0

            tipo = request.form.get('tipo_movimento', 'despesa')
            is_parcelado = (request.form.get('is_parcelado') == 'on' and tipo == 'despesa')

            try:
                qtd_parcelas = int(request.form.get('qtd_parcelas', '1'))
            except ValueError:
                qtd_parcelas = 1

            if not is_parcelado or qtd_parcelas < 1:
                qtd_parcelas = 1

            descricao_base = request.form.get('descricao', 'Sem descrição')
            categoria = request.form.get('categoria', 'Outros')
            data_str = request.form.get('data_gasto') or request.form.get('data')

            quinzena = int(request.form.get('quinzena', '0')) if tipo == 'despesa' else 0
            status_base = request.form.get('status', 'PAGO')
            data_inicial = datetime.strptime(data_str, '%Y-%m-%d')

            conexao = get_db_connection()
            try:
                cursor = conexao.cursor()
                try:
                    cursor.execute("ALTER TABLE gastos ADD COLUMN tipo TEXT DEFAULT 'despesa'")
                except Exception:
                    pass

                for i in range(qtd_parcelas):
                    mes_atual = data_inicial.month - 1 + i
                    ano_atual = data_inicial.year + (mes_atual // 12)
                    mes_atual = (mes_atual % 12) + 1

                    ultimo_dia_mes = calendar.monthrange(ano_atual, mes_atual)[1]
                    dia_atual = min(data_inicial.day, ultimo_dia_mes)
                    data_parcela = f"{ano_atual:04d}-{mes_atual:02d}-{dia_atual:02d}"

                    descricao_final = f"{descricao_base} ({i+1}/{qtd_parcelas})" if is_parcelado else descricao_base
                    status_final = status_base if i == 0 else 'PENDENTE'

                    cursor.execute(
                        "INSERT INTO gastos (usuario_id, descricao, valor, categoria, data, quinzena, status, tipo) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                        (session['user_id'], descricao_final, valor, categoria, data_parcela, quinzena, status_final, tipo)
                    )
                conexao.commit()
            finally:
                conexao.close()

            # Evitar quebra se a função registrar_aprendizado_ia não estiver definida
            try:
                registrar_aprendizado_ia(session['user_id'], 'gastos', 'criar', {'descricao': descricao_base, 'categoria': categoria, 'valor': valor, 'tipo': tipo, 'parcelas': qtd_parcelas})
            except Exception:
                pass

            return redirect(url_for('home'))

        except Exception as e:
            print(f"Erro ao inserir movimentacao: {e}")
            return redirect(url_for('home'))

    is_ajax = request.args.get('modal') == 'true'
    return render_template('telas/movimentacoes.html', ajax_request=is_ajax, gasto=None)

@app.route('/editar_movimentacao/<int:id>', methods=['POST'])
@login_obrigatorio
def editar_movimentacao(id):
    try:
        valor = float(str(request.form.get('valor', '0')).replace(',', '.'))
    except ValueError:
        valor = 0.0

    tipo = request.form.get('tipo_movimento', 'despesa')
    quinzena = int(request.form.get('quinzena', '0')) if tipo == 'despesa' else 0

    conexao = get_db_connection()
    try:
        cursor = conexao.cursor()
        cursor.execute(
            "UPDATE gastos SET descricao=?, data=?, valor=?, categoria=?, quinzena=?, status=?, tipo=? WHERE id=? AND usuario_id=?",
            (request.form.get('descricao'), request.form.get('data'), valor, request.form.get('categoria'), quinzena, request.form.get('status', 'PENDENTE'), tipo, id, session['user_id'])
        )
        conexao.commit()
    finally:
        conexao.close()

    mes_filtro = request.form.get('mes_filtro')
    return redirect(url_for('home', mes=mes_filtro) if mes_filtro else url_for('home'))

@app.route('/api/movimentacoes_mes', methods=['GET'])
@login_obrigatorio
def api_movimentacoes_mes():
    mes = request.args.get('mes')
    if not mes:
        return jsonify([])

    conexao = get_db_connection()
    try:
        cursor = conexao.cursor()
        cursor.execute('SELECT id, descricao, valor, categoria, IFNULL(tipo, "despesa") as tipo FROM gastos WHERE data LIKE ? AND usuario_id = ? ORDER BY data ASC', (mes + '%', session['user_id']))
        movimentacoes = [{'id': m['id'], 'descricao': m['descricao'], 'valor': float(m['valor']), 'categoria': m['categoria'], 'tipo': m['tipo']} for m in cursor.fetchall()]
    finally:
        conexao.close()

    return jsonify(movimentacoes)


@app.route('/duplicar_movimentacoes_lote', methods=['POST'])
@login_obrigatorio
def duplicar_movimentacoes_lote():
    mes_destino = request.form.get('mes_destino')
    contas = request.form.getlist('contas_selecionadas')

    if not mes_destino or not contas:
        return redirect(url_for('movimentacoes'))

    ano_dest, mes_dest = map(int, mes_destino.split('-'))
    ultimo_dia = calendar.monthrange(ano_dest, mes_dest)[1]

    conexao = get_db_connection()
    try:
        cursor = conexao.cursor()
        placeholders = ','.join('?' * len(contas))
        query = f"SELECT * FROM gastos WHERE id IN ({placeholders}) AND usuario_id = ?"
        cursor.execute(query, contas + [session['user_id']])

        for m in cursor.fetchall():
            try:
                dia_origem = int(m['data'][8:10])
            except ValueError:
                dia_origem = 1

            nova_data = f"{ano_dest:04d}-{mes_dest:02d}-{min(dia_origem, ultimo_dia):02d}"
            tipo_conta = m['tipo'] if 'tipo' in m.keys() and m['tipo'] else 'despesa'

            cursor.execute(
                "INSERT INTO gastos (descricao, categoria, valor, quinzena, status, data, tipo, usuario_id) VALUES (?, ?, ?, ?, 'PENDENTE', ?, ?, ?)",
                (m['descricao'], m['categoria'], m['valor'], m['quinzena'], nova_data, tipo_conta, session['user_id'])
            )
        conexao.commit()
    finally:
        conexao.close()

    return redirect(url_for('home', mes=mes_destino))

# ==============================================================================
# ROTA: ATUALIZAR STATUS DO GASTO (Com Motor Inteligente de Contratos)
# ==============================================================================
@app.route('/atualizar_status/<int:id>', methods=['POST'])
@login_obrigatorio
def atualizar_status(id):
    user_id = session['user_id']
    conexao = get_db_connection()
    cursor = conexao.cursor()

    # Pega o gasto atual
    cursor.execute('SELECT status, divida_id FROM gastos WHERE id = ? AND usuario_id = ?', (id, user_id))
    gasto = cursor.fetchone()

    if gasto:
        is_dict = hasattr(gasto, 'keys')
        status_atual = str(gasto['status'] if is_dict else gasto[0]).upper().strip()
        divida_id = gasto['divida_id'] if is_dict else gasto[1]

        novo_status = 'PENDENTE' if status_atual == 'PAGO' else 'PAGO'

        # Atualiza o status do gasto
        cursor.execute('UPDATE gastos SET status = ? WHERE id = ? AND usuario_id = ?', (novo_status, id, user_id))

        # ================================================================
        # MOTOR INTELIGENTE: SINCRONIZAR COM O CONTRATO/META
        # ================================================================
        if divida_id:
            cursor.execute('SELECT parcelas_pagas, total_parcelas FROM dividas WHERE id = ? AND usuario_id = ?', (divida_id, user_id))
            divida = cursor.fetchone()

            if divida:
                is_dict_div = hasattr(divida, 'keys')
                pagas = int(divida['parcelas_pagas'] if is_dict_div else divida[0] or 0)
                total = int(divida['total_parcelas'] if is_dict_div else divida[1] or 1)

                # Se marcou como pago, soma 1. Se desmarcou, subtrai 1.
                if novo_status == 'PAGO' and status_atual != 'PAGO':
                    pagas += 1
                elif novo_status != 'PAGO' and status_atual == 'PAGO':
                    pagas -= 1

                # Travas de segurança matematicas
                if pagas < 0: pagas = 0
                if pagas > total: pagas = total

                cursor.execute('UPDATE dividas SET parcelas_pagas = ? WHERE id = ? AND usuario_id = ?', (pagas, divida_id, user_id))

        conexao.commit()
    conexao.close()

    mes_filtro = request.args.get('mes', datetime.now().strftime('%Y-%m'))
    return redirect(url_for('home', mes=mes_filtro))

# ==============================================================================
# ROTA: EXCLUIR MOVIMENTAÇÃO (Com Reversão Inteligente de Contratos)
# ==============================================================================
@app.route('/excluir_movimentacao/<int:id>', methods=['POST'])
@login_obrigatorio
def excluir_movimentacao(id):
    user_id = session.get('user_id')
    conexao = get_db_connection()
    cursor = conexao.cursor()

    # Antes de excluir, verifica se era uma parcela de contrato
    cursor.execute("SELECT divida_id, status FROM gastos WHERE id = ? AND usuario_id = ?", (id, user_id))
    gasto = cursor.fetchone()

    if gasto:
        is_dict = hasattr(gasto, 'keys')
        divida_id = gasto['divida_id'] if is_dict else gasto[0]
        status_atual = str(gasto['status'] if is_dict else gasto[1]).upper().strip()

        # Exclui a movimentação da tabela
        cursor.execute("DELETE FROM gastos WHERE id = ? AND usuario_id = ?", (id, user_id))

        # Se excluiu uma parcela que já estava PAGA, remove do progresso do contrato para não corromper
        if divida_id and status_atual == 'PAGO':
            cursor.execute('SELECT parcelas_pagas FROM dividas WHERE id = ? AND usuario_id = ?', (divida_id, user_id))
            divida = cursor.fetchone()
            if divida:
                val_pagas = divida['parcelas_pagas'] if hasattr(divida, 'keys') else divida[0]
                pagas = max(0, int(val_pagas or 0) - 1)
                cursor.execute('UPDATE dividas SET parcelas_pagas = ? WHERE id = ? AND usuario_id = ?', (pagas, divida_id, user_id))

    conexao.commit()
    conexao.close()

    mes = request.form.get('mes_filtro', datetime.now().strftime('%Y-%m'))
    return redirect(url_for('home', mes=mes))

# ==============================================================================
# DÍVIDAS E PLANEJAMENTO
# ==============================================================================
@app.route('/dividas', methods=['GET'])
@login_obrigatorio
def dividas():
    conexao = get_db_connection()
    cursor = conexao.cursor()
    dividas = cursor.execute("SELECT * FROM dividas WHERE usuario_id = ? ORDER BY id DESC", (session['user_id'],)).fetchall()
    conexao.close()
    return render_template('telas/dividas_planejamento.html', dividas=dividas)

@app.route('/nova_divida', methods=['POST'])
@login_obrigatorio
def nova_divida():
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
@login_obrigatorio
def editar_divida(id):
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
@login_obrigatorio
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
@login_obrigatorio
def quitar_divida(id):
    conexao = get_db_connection()
    cursor = conexao.cursor()
    cursor.execute("UPDATE dividas SET parcelas_pagas = total_parcelas, status = 'CONCLUIDA' WHERE id = ? AND usuario_id = ?", (id, session['user_id']))
    conexao.commit()
    conexao.close()
    return redirect('/dividas')

@app.route('/excluir_divida/<int:id>', methods=['POST'])
@login_obrigatorio
def excluir_divida(id):
    conexao = get_db_connection()
    cursor = conexao.cursor()
    cursor.execute("DELETE FROM dividas WHERE id = ? AND usuario_id = ?", (id, session['user_id']))
    conexao.commit()
    conexao.close()
    return redirect('/dividas')


# ==============================================================================
# METAS (CAIXINHAS / RESERVAS)
# ==============================================================================
@app.route('/metas', methods=['GET', 'POST'])
@login_obrigatorio
def metas():
    try:
        conexao = get_db_connection()
        cursor = conexao.cursor()

        if request.method == 'POST':
            if 'novo_objetivo' in request.form:
                try:
                    meta_valor = float(str(request.form.get('meta', '0')).replace(',', '.'))
                except ValueError:
                    meta_valor = 0.0

                cursor.execute(
                    'INSERT INTO reservas (nome, meta, guardado, usuario_id) VALUES (?, ?, 0, ?)',
                    (request.form.get('nome'), meta_valor, session['user_id'])
                )
            elif 'adicionar_saldo' in request.form:
                try:
                    v = float(str(request.form.get('valor_adicionar', '0')).replace(',', '.'))
                except ValueError:
                    v = 0.0

                cursor.execute(
                    'UPDATE reservas SET guardado = guardado + ? WHERE id = ? AND usuario_id = ?',
                    (v, request.form.get('id_reserva'), session['user_id'])
                )
            conexao.commit()
            return redirect(url_for('metas'))

        reservas = cursor.execute('SELECT * FROM reservas WHERE usuario_id = ? ORDER BY id DESC', (session['user_id'],)).fetchall()
    finally:
        conexao.close()

    is_ajax = request.args.get('modal') == 'true'
    return render_template('telas/metas.html', reservas=reservas, ajax_request=is_ajax)


@app.route('/editar_reserva/<int:id>', methods=['POST'])
@login_obrigatorio
def editar_reserva(id):
    try:
        meta_valor = float(str(request.form.get('meta', '0')).replace(',', '.'))
    except ValueError:
        meta_valor = 0.0

    try:
        conexao = get_db_connection()
        cursor = conexao.cursor()
        cursor.execute(
            'UPDATE reservas SET nome = ?, meta = ? WHERE id = ? AND usuario_id = ?',
            (request.form.get('nome'), meta_valor, id, session['user_id'])
        )
        conexao.commit()
    finally:
        conexao.close()

    return redirect('/metas')


@app.route('/excluir_reserva/<int:id>', methods=['POST'])
@login_obrigatorio
def excluir_reserva(id):
    try:
        conexao = get_db_connection()
        cursor = conexao.cursor()
        cursor.execute("DELETE FROM reservas WHERE id = ? AND usuario_id = ?", (id, session['user_id']))
        conexao.commit()
    finally:
        conexao.close()

    return redirect('/metas')


# --------------------------------------------------------------------------------
@app.route('/lancar_parcela/<int:id_divida>', methods=['POST'])
@login_obrigatorio
def lancar_parcela(id_divida):
    user_id = session.get('user_id')

    try:
        conexao = get_db_connection()
        cursor = conexao.cursor()

        cursor.execute("SELECT descricao, valor_parcela FROM dividas WHERE id = ? AND usuario_id = ?", (id_divida, user_id))
        divida = cursor.fetchone()

        if not divida:
            return jsonify({'status': 'erro', 'mensagem': 'Contrato não encontrado'}), 404

        valor_raw = str(divida['valor_parcela'] if hasattr(divida, 'keys') else divida[1]).strip()
        valor_raw = valor_raw.replace('R$', '').replace(' ', '')

        if '.' in valor_raw and ',' in valor_raw:
            valor_raw = valor_raw.replace('.', '').replace(',', '.')
        elif ',' in valor_raw:
            valor_raw = valor_raw.replace(',', '.')

        try:
            valor_limpo = float(valor_raw)
        except ValueError:
            valor_limpo = 0.00

        desc_nome = divida['descricao'] if hasattr(divida, 'keys') else divida[0]
        descricao_gasto = f"Parcela: {desc_nome}"
        data_atual = datetime.now().strftime('%Y-%m-%d')
        quinzena = 1 if datetime.now().day <= 15 else 2

        cursor.execute('''
            INSERT INTO gastos (descricao, categoria, valor, quinzena, status, data, usuario_id, divida_id)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ''', (descricao_gasto, 'Contratos/Dívidas', valor_limpo, quinzena, 'PENDENTE', data_atual, user_id, id_divida))

        conexao.commit()
        return jsonify({'status': 'sucesso', 'mensagem': 'Parcela adicionada aos gastos do mês!'})
    finally:
        conexao.close()

# ==============================================================================
# COMPRAS (LISTA)
# ==============================================================================
def parse_valor(texto, padrao=0.0):
    if not texto: return padrao
    try: return float(str(texto).strip().replace('.', '').replace(',', '.'))
    except: return padrao

@app.route('/compras', methods=['GET', 'POST'])
@login_obrigatorio
def compras():
    mes_atual = datetime.now().strftime('%Y-%m')
    try:
        conexao = get_db_connection()
        cursor = conexao.cursor()

        if request.method == 'POST':
            if 'valor_meta' in request.form:
                cursor.execute('INSERT INTO meta_compras (usuario_id, mes, valor) VALUES (?, ?, ?) ON CONFLICT(usuario_id, mes) DO UPDATE SET valor = excluded.valor',
                               (session['user_id'], mes_atual, parse_valor(request.form.get('valor_meta'))))
            elif 'editar' in request.form:
                cursor.execute('UPDATE lista_compras SET descricao=?, quantidade=?, preco=?, total_item=? WHERE id=? AND usuario_id=?',
                               (request.form.get('descricao'), int(request.form.get('quantidade', 1)), parse_valor(request.form.get('preco')), int(request.form.get('quantidade', 1))*parse_valor(request.form.get('preco')), request.form.get('id_item_edit'), session['user_id']))
            else:
                q, p = int(request.form.get('quantidade', 1)), parse_valor(request.form.get('preco'))
                cursor.execute('INSERT INTO lista_compras (usuario_id, descricao, quantidade, preco, total_item, mes) VALUES (?, ?, ?, ?, ?, ?)',
                               (session['user_id'], request.form.get('descricao'), q, p, q*p, mes_atual))
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
    finally:
        conexao.close()

    # A MÁGICA DO AJAX: Se a requisição veio do JavaScript Modal Ajax, enviamos só o 'miolo'.
    is_ajax = request.args.get('modal') == 'true'

    return render_template('telas/compras.html',
                           itens=itens,
                           total_lista=total_lista,
                           meta_valor=meta,
                           saldo_meta=meta - total_lista,
                           porcentagem_meta=round((total_lista/meta*100),1) if meta>0 else 0,
                           ajax_request=is_ajax)

@app.route('/excluir_compra/<int:id>', methods=['POST'])
@login_obrigatorio
def excluir_compra(id):
    try:
        conexao = get_db_connection()
        cursor = conexao.cursor()
        cursor.execute("DELETE FROM lista_compras WHERE id = ? AND usuario_id = ?", (id, session.get('user_id')))
        conexao.commit()
    finally:
        conexao.close()
    return redirect('/compras')

@app.route('/lancar_compras_gastos', methods=['POST'])
@login_obrigatorio
def lancar_compras_gastos():
    try: valor = float(request.form.get('total_compra', 0))
    except: valor = 0.0

    if valor > 0:
        try:
            conexao = get_db_connection()
            cursor = conexao.cursor()
            cursor.execute("INSERT INTO gastos (usuario_id, descricao, valor, categoria, data, quinzena, status) VALUES (?, ?, ?, ?, ?, 0, 'PAGO')",
                           (session.get('user_id'), 'Supermercado (Lista de Compras)', valor, 'Alimentação', datetime.now().strftime('%Y-%m-%d')))
            conexao.commit()
        finally:
            conexao.close()

    return redirect(url_for('home'))

@app.route('/exportar_compras_csv')
@login_obrigatorio
def exportar_compras_csv():
    mes = datetime.now().strftime('%Y-%m')
    try:
        conexao = get_db_connection()
        itens = conexao.cursor().execute("SELECT descricao, quantidade, preco FROM lista_compras WHERE usuario_id = ? AND mes = ?", (session['user_id'], mes)).fetchall()
    finally:
        conexao.close()

    output = io.StringIO()
    output.write('\ufeff')
    writer = csv.writer(output, delimiter=';')
    writer.writerow(['Descrição', 'Quantidade', 'Preço Unitário', 'Total do Item'])
    for i, item in enumerate(itens, 2):
        # Acesso seguro via índice, independente se for dicionário ou tupla
        desc = item['descricao'] if hasattr(item, 'keys') else item[0]
        qtd = item['quantidade'] if hasattr(item, 'keys') else item[1]
        preco = item['preco'] if hasattr(item, 'keys') else item[2]

        writer.writerow([desc, qtd, str(preco).replace('.', ','), f'=B{i}*C{i}'])

    if len(itens) > 0: writer.writerow(['', '', 'TOTAL GERAL:', f'=SOMA(D2:D{len(itens)+1})'])
    return Response(output.getvalue(), mimetype="text/csv; charset=utf-8", headers={"Content-Disposition": f"attachment;filename=lista_{mes}.csv"})
# ==============================================================================
# CHAT BOT - IA HIR3
# ==============================================================================

@app.route('/api/chat_hir3', methods=['POST'])
@login_obrigatorio
def chat_hir3():
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
@login_obrigatorio
def relatorios_avancados():
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

    # TRAVA AJAX
    is_ajax = request.args.get('modal') == 'true'

    return render_template('telas/relatorios_avancados.html',
                           mes_filtro=mes_filtro,
                           dias_grafico=[r['dia'] for r in grafico],
                           valores_grafico=[r['total'] for r in grafico],
                           labels_categorias=list(cat_dict.keys()),
                           valores_categorias=list(cat_dict.values()),
                           top3_gastos=sorted(gastos, key=lambda x: float(x['valor']), reverse=True)[:3],
                           dividas=lista_div,
                           reservas=reservas,
                           total_q1=0, total_q2=0, perc_pago=0, perc_pendente=0,
                           ajax_request=is_ajax)

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
        except: pass
        return jsonify({"status": "recebido"}), 200

# ==============================================================================
# CONTEXTOS GLOBAIS E INICIALIZAÇÃO
# ==============================================================================
VERSAO_SISTEMA = "1.6.6" # <--- No futuro, você altera a versão APENAS nesta linha!

@app.context_processor
def inject_global_vars():
    return dict(versao_atual=VERSAO_SISTEMA, data_atual=datetime.now().strftime('%B %Y').capitalize())

# Garante que o banco seja criado e configurado logo antes do app rodar
iniciar_banco()

if __name__ == '__main__':
    app.run(debug=True)