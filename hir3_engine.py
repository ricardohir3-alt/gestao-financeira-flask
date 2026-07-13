import json
import google.generativeai as genai

# ==========================================
# CONFIGURAÇÃO DO CÉREBRO (API DO GEMINI)
# ==========================================
# Substitua pela sua chave real se ainda não o fez
genai.configure(api_key="COLE_SUA_CHAVE_AQUI")
modelo = genai.GenerativeModel('gemini-1.5-flash')

def analisar_mensagem_com_hir3(texto_usuario):
    """
    Função principal do hir3. 
    Lê o WhatsApp, interpreta a intenção e devolve um JSON puro.
    """
    
    prompt = f"""
    Você é o 'hir3', o assistente virtual de inteligência artificial do sistema financeiro 'Minhas Finanças'.
    Sua missão é interpretar a mensagem do usuário e extrair os dados retornando ÚNICA e EXCLUSIVAMENTE um objeto JSON válido. 
    NÃO adicione formatação Markdown (como ```json) e não escreva nenhum texto antes ou depois do JSON.

    Siga rigorosamente estas 4 regras de intenção:

    1. SE FOR UM GASTO (ex: "paguei 30 de lanche", "comprei pão 10,50" ou se o usuário enviar "1"):
       - Se os dados estiverem claros, retorne: {{"acao": "registrar_gasto", "valor": <float>, "descricao": "<resumo capitalizado>", "categoria": "<Alimentação, Habitação, Lazer Outros Saúde, Transporte, ou>", "mensagem_hir3": "✅ Perfeito! Registrei R$ <valor> referente a <descricao> na categoria <categoria>."}}
       - Se o usuário enviou apenas "1" ou não disse o valor, retorne a ação "conversar" e uma "mensagem_hir3" pedindo o valor e no que ele gastou.

    2. SE FOR RECUPERAÇÃO DE SENHA OU LOGIN (ex: "esqueci minha senha", "não consigo acessar" ou se o usuário enviar "3"):
       Retorne: {{"acao": "recuperar_senha", "mensagem_hir3": ""}}

    3. SE FOR CONSULTA DE SALDO (ex: "como tá meu saldo?", "resumo do mês" ou se o usuário enviar "2"):
       Retorne: {{"acao": "consultar_saldo", "mensagem_hir3": ""}}

    4. SE FOR SAUDAÇÃO, DÚVIDA OU MENSAGEM GENÉRICA (ex: "bom dia", "oi", "olá", "ajuda", "menu"):
       Retorne EXATAMENTE este JSON de menu:
       {{"acao": "conversar", "mensagem_hir3": "Olá! 👋 Eu sou o *hir3*, seu assistente financeiro.\\n\\nComo posso facilitar sua vida hoje? Digite o número da opção:\\n\\n*1️⃣* Registrar um novo gasto\\n*2️⃣* Consultar meu saldo atual\\n*3️⃣* Recuperar senha de acesso"}}

    Mensagem do usuário: "{texto_usuario}"
    """
    
    try:
        # Envia para o Gemini
        resposta = modelo.generate_content(prompt)
        
        # Limpeza para garantir formato JSON
        texto_limpo = resposta.text.replace('```json', '').replace('```', '').strip()
        
        return json.loads(texto_limpo)
        
    except json.JSONDecodeError:
        print(f"Erro de formatação do Gemini. Resposta crua: {resposta.text}")
        return {
            "acao": "conversar",
            "mensagem_hir3": "Ops! Deu um pequeno curto-circuito nos meus cabos. Você pode repetir ou digitar *Menu*?"
        }
    except Exception as e:
        print(f"Falha geral na API do Gemini: {e}")
        return {
            "acao": "conversar",
            "mensagem_hir3": "Meus servidores estão passando por uma instabilidade. Volto em um minuto!"
        }