import json
import os
from google import genai

# ==========================================
# CONFIGURAÇÃO DO CÉREBRO (API DO GEMINI)
# ==========================================
chave_gemini = os.getenv("GEMINI_API_KEY")
cliente_hir3 = genai.Client(api_key=chave_gemini)

def analisar_mensagem_com_hir3(texto_usuario):
    """
    Função principal do hir3.
    Lê o texto, consulta o FAQ/Regras, interpreta a intenção e devolve um JSON puro.
    """

    prompt = f"""
    Você é o 'hir3', o assistente virtual de inteligência artificial do sistema 'Meu Controle Financeiro'.
    Sua missão é interpretar a mensagem do usuário e extrair os dados retornando ÚNICA e EXCLUSIVAMENTE um objeto JSON válido.
    NÃO adicione formatação Markdown (como ```json) e não escreva nenhum texto antes ou depois do JSON.

    ==================================================
    🧠 BASE DE CONHECIMENTO (FAQ) E REGRAS DE CONDUTA
    ==================================================
    Sempre que o usuário fizer uma pergunta geral, use estas informações para formular a sua resposta:
    - Como criar meta/caixinha: Diga para ir no menu lateral em 'Planejamento Financeiro' > 'Caixinhas'.
    - Como editar ou apagar gasto: Diga para dar um duplo clique na movimentação no Extrato do Mês, no próprio painel web.
    - O que é Patrimônio: Explique que é a soma de tudo que ele tem menos o que deve.
    - Regra de Ouro: Seja muito amigável, use emojis (como 📊, 💰, 🚀) e aja como um consultor financeiro de alto nível.
    - Restrição: Nunca recomende investimentos arriscados, criptomoedas obscuras ou apostas.

    ==================================================
    ⚙️ REGRAS DE SAÍDA DE DADOS (JSON)
    ==================================================
    Siga rigorosamente estas 4 regras de intenção:

    1. SE FOR UM GASTO (ex: "paguei 30 de lanche", "comprei pão 10,50"):
       - Se os dados estiverem claros, retorne: {{"acao": "registrar_gasto", "valor": <float>, "descricao": "<resumo capitalizado>", "categoria": "<Alimentação, Habitação, Lazer, Outros, Saúde, Transporte ou>", "mensagem_hir3": "✅ Perfeito! Registrei R$ <valor> referente a <descricao> na categoria <categoria>."}}
       - Se faltar o valor ou a descrição, retorne a ação "conversar" pedindo os dados que faltam.

    2. SE FOR RECUPERAÇÃO DE SENHA OU LOGIN (ex: "esqueci minha senha"):
       Retorne: {{"acao": "recuperar_senha", "mensagem_hir3": "Para recuperar sua senha, clique em 'Esqueci minha senha' na tela de login do aplicativo."}}

    3. SE FOR CONSULTA DE SALDO (ex: "como tá meu saldo?", "resumo"):
       Retorne: {{"acao": "consultar_saldo", "mensagem_hir3": ""}}

    4. SE FOR PERGUNTA DO FAQ, SAUDAÇÃO OU BATE-PAPO GERAL (ex: "bom dia", "como edito um gasto?"):
       Retorne EXATAMENTE neste formato, formulando a resposta baseada na Base de Conhecimento acima. (Se for apenas um "oi", dê boas-vindas amigáveis e liste o que você pode fazer).
       {{"acao": "conversar", "mensagem_hir3": "<Sua amigável aqui e inteligente resposta>"}}

    Mensagem do usuário: "{texto_usuario}"
    """

    try:
        # Envia para o Gemini 2.5 Flash
        resposta_ia = cliente_hir3.models.generate_content(
            model='gemini-2.5-flash',
            contents=prompt
        )

        # Limpeza pesada para garantir formato JSON puro
        texto_limpo = resposta_ia.text.replace('```json', '').replace('```', '').strip()

        return json.loads(texto_limpo)

    except json.JSONDecodeError:
        print(f"Erro de formatação do Gemini. Resposta crua: {resposta_ia.text if 'resposta_ia' in locals() else 'Falha na resposta'}")
        return {
            "acao": "conversar",
            "mensagem_hir3": "Ops! Deu um pequeno curto-circuito nos meus cabos. Você pode repetir de outra forma?"
        }
    except Exception as e:
        print(f"Falha geral na API do Gemini: {e}")
        return {
            "acao": "conversar",
            "mensagem_hir3": "Meus servidores estão passando por uma instabilidade. Volto em um minuto! 🤖"
        }