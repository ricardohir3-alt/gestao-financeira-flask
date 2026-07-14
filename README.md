# 📊 Sistema Híbrido de Gestão Financeira e Comercial

![Python](https://img.shields.io/badge/Python-3.13-blue?style=for-the-badge&logo=python&logoColor=white)
![Flask](https://img.shields.io/badge/Flask-Web_Framework-black?style=for-the-badge&logo=flask&logoColor=white)
![SQLite](https://img.shields.io/badge/SQLite-Database-003B57?style=for-the-badge&logo=sqlite&logoColor=white)
![TailwindCSS](https://img.shields.io/badge/Tailwind_CSS-38B2AC?style=for-the-badge&logo=tailwind-css&logoColor=white)
![Gemini AI](https://img.shields.io/badge/Google_Gemini-AI-8E75B2?style=for-the-badge&logo=google&logoColor=white)

Um sistema completo (ERP-like) desenvolvido em Python para gestão financeira pessoal e comercial. Focado em automação, observabilidade e experiência do usuário, o projeto transforma tarefas manuais de planilhas em uma plataforma web moderna, rápida e responsiva.

---

## 🚀 Principais Funcionalidades

- **🧮 Gestão de Orçamentos e Metas:** Definição de limites de gastos (tetos), cálculo dinâmico de saldo disponível e barras de progresso visuais.
- **🔄 Sincronização de Dados (Módulo Xerox):** Importação e exportação de dados via arquivos CSV, permitindo o trabalho offline e integração com o Excel.
- **🤖 Diagnóstico de Logs com Inteligência Artificial:** Central de observabilidade (Logs & Erros) integrada à API do **Google Gemini**. O sistema captura exceções do back-end, envia para a IA e retorna o diagnóstico e a solução diretamente na interface.
- **📸 Fricção Zero (OCR):** Importação de comprovantes (Pix/Boletos) através de leitura de imagens.
- **👥 Gestão de Usuários e Acessos:** Sistema seguro de autenticação com senhas criptografadas, controle de permissões (Admin Master) e gestão de licenças (Básica/Premium).
- **📱 PWA (Progressive Web App):** Interface otimizada (mobile-first) e responsiva com Tailwind CSS, proporcionando uma experiência de aplicativo nativo no navegador.

---

## 🛠️ Tecnologias Utilizadas

* **Back-End:** Python 3, Flask
* **Banco de Dados:** SQLite3
* **Front-End:** HTML5, Jinja2, Tailwind CSS (via CDN)
* **Ícones:** Lucide Icons
* **Integrações:** Google Generative AI (Gemini 1.5 Flash)
* **Deploy:** PythonAnywhere

---

## ⚙️ Como executar o projeto localmente

Siga as instruções abaixo para rodar o projeto na sua máquina:

### 1. Clone este repositório
```bash
git clone [https://github.com/ricardohir3-alt/gestao-financeira-flask.git](https://github.com/ricardohir3-alt/gestao-financeira-flask.git)
cd gestao-financeira-flask

###2. Crie e ative um ambiente virtual
Bash
python -m venv venv
# No Windows:
venv\Scripts\activate
# No Linux/Mac:
source venv/bin/activate

###3. Instale as dependências
Bash
pip install Flask google-generativeai werkzeug

###4. Execute a aplicação
Bash
python flask_app.py
