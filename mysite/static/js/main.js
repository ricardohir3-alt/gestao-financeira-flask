// ==========================================
// SISTEMA DE INTERNACIONALIZAÇÃO (i18n)
// ==========================================
const traducoes = {
    'PT-BR': {
        'nav_dashboard': 'Dashboard Inicial', 'nav_gasto': 'Registrar Gasto', 'nav_compras': 'Lista de Compras', 'nav_metas': 'Planejamento Financeiro', 'nav_usuarios': 'Gestão de Usuários', 'nav_relatorios': 'Relatório Premium', 'nav_novidades': 'Novidades', 'menu_perfil': 'Meu Perfil', 'menu_sair': 'Sair', 'mob_inicio': 'Início', 'mob_compras': 'Compras', 'mob_lancar': 'Lançar', 'mob_metas': 'Metas', 'mob_mais': 'Mais', 'nav_titulo': 'Navegação', 'sup_whatsapp': 'Suporte WhatsApp',
        'resumo_gerencial': 'Resumo Gerencial', 'mes': 'Mês:', 'entradas': 'Entradas', 'saidas': 'Saídas', 'saldo_atual': 'Saldo Atual', 'fluxo_mes': 'Fluxo do Mês', 'fluxo_sub': 'O quanto da sua renda já foi consumido', 'ver_projecao': 'Ver projeção', 'metricas': 'Métricas Detalhadas', 'consumo_q': 'Consumo Quinzena', 'status': 'Status', 'top_despesas': 'Top Despesas', 'categorias': 'Categorias', 'jornada_ia': 'Jornada IA', 'ver_tendencia': 'Ver Tendência de Gastos', 'extrato': 'Extrato do Mês', 'transacoes': 'Transações', 'todos': 'Todos', 'pagos': 'Pagos', 'pendentes': 'Pendentes', 'sem_despesas': 'Sem dados registrados',
        'xp_lvl1': 'Limpando a selva financeira. Continue farmando XP!', 'xp_lvl2': 'Excelente rotação! Suas metas estão na mira.', 'xp_lvl3': 'Lenda Mítica das finanças! O controle é seu.', 'xp_motivo_login': 'Login Diário!', 'xp_motivo_tendencia': 'Análise de Tendência vista!', 'xp_motivo_extrato': 'Extrato Visualizado!', 'xp_motivo_pago': 'Conta Paga!', 'xp_motivo_ia': 'Consultoria IA concluída!'
    },
    'EN-US': {
        'menu_titulo': 'MENU', 'nav_dashboard': 'Dashboard', 'nav_gasto': 'Add Expense', 'nav_compras': 'Shopping List', 'nav_metas': 'Financial Planning', 'nav_usuarios': 'User Management', 'nav_relatorios': 'Premium Report', 'nav_novidades': 'Updates', 'menu_perfil': 'My Profile', 'menu_sair': 'Logout', 'mob_inicio': 'Home', 'mob_compras': 'Shop', 'mob_lancar': 'Add', 'mob_metas': 'Goals', 'mob_mais': 'More', 'nav_titulo': 'Navigation', 'sup_whatsapp': 'WhatsApp Support',
        'resumo_gerencial': 'Management Summary', 'mes': 'Month:', 'entradas': 'Incomes', 'saidas': 'Expenses', 'saldo_atual': 'Current Balance', 'fluxo_mes': 'Monthly Flow', 'fluxo_sub': 'How much of your income has been consumed', 'ver_projecao': 'View projection', 'metricas': 'Detailed Metrics', 'consumo_q': 'Fortnight Consumption', 'status': 'Status', 'top_despesas': 'Top Expenses', 'categorias': 'Categories', 'jornada_ia': 'AI Journey', 'ver_tendencia': 'View Spending Trends', 'extrato': 'Monthly Statement', 'transacoes': 'Transactions', 'todos': 'All', 'pagos': 'Paid', 'pendentes': 'Pending', 'sem_despesas': 'No expenses recorded',
        'xp_lvl1': 'Clearing the financial jungle. Keep farming XP!', 'xp_lvl2': 'Excellent rotation! Your goals are in sight.', 'xp_lvl3': 'Mythic Legend of finances! You are in control.', 'xp_motivo_login': 'Daily Login!', 'xp_motivo_tendencia': 'Trend Analysis viewed!', 'xp_motivo_extrato': 'Statement Viewed!', 'xp_motivo_pago': 'Bill Paid!', 'xp_motivo_ia': 'AI Consulting completed!'
    },
    'ZH-CN': {
        'menu_titulo': '菜单', 'nav_dashboard': '仪表板', 'nav_gasto': '记录支出', 'nav_compras': '购物清单', 'nav_metas': '财务规划', 'nav_usuarios': '用户管理', 'nav_relatorios': '高级报告', 'nav_novidades': '更新', 'menu_perfil': '我的主页', 'menu_sair': '退出', 'mob_inicio': '主页', 'mob_compras': '购物', 'mob_lancar': '添加', 'mob_metas': '目标', 'mob_mais': '更多', 'nav_titulo': '导航', 'sup_whatsapp': 'WhatsApp 支持',
        'resumo_gerencial': '管理摘要', 'mes': '月:', 'entradas': '收入', 'saidas': '支出', 'saldo_atual': '当前余额', 'fluxo_mes': '月度流量', 'fluxo_sub': '您的收入消耗了多少', 'ver_projecao': '查看预测', 'metricas': '详细指标', 'consumo_q': '半月消耗', 'status': '状态', 'top_despesas': '最高支出', 'categorias': '类别', 'jornada_ia': 'AI 之旅', 'ver_tendencia': '查看支出趋势', 'extrato': '月度对账单', 'transacoes': '交易', 'todos': '全部', 'pagos': '已付', 'pendentes': '待付', 'sem_despesas': '没有记录的费用',
        'xp_lvl1': '清理财务丛林。继续获取经验值！', 'xp_lvl2': '出色的轮换！你的目标在望。', 'xp_lvl3': '财务神话传说！一切尽在掌控。', 'xp_motivo_login': '每日登录！', 'xp_motivo_tendencia': '已查看趋势分析！', 'xp_motivo_extrato': '已查看对账单！', 'xp_motivo_pago': '账单已付！', 'xp_motivo_ia': 'AI 咨询完成！'
    }
};

const idiomasSuportados = ['PT-BR', 'EN-US', 'ZH-CN'];

window.cicloIdioma = function() {
    let idiomaAtualSalvo = localStorage.getItem('idioma_sistema') || 'PT-BR';
    let idiomaAtualIndex = idiomasSuportados.indexOf(idiomaAtualSalvo);
    if (idiomaAtualIndex === -1) idiomaAtualIndex = 0;

    idiomaAtualIndex = (idiomaAtualIndex + 1) % idiomasSuportados.length;
    const novoIdioma = idiomasSuportados[idiomaAtualIndex];
    
    localStorage.setItem('idioma_sistema', novoIdioma);
    
    const textoIdiomaEl = document.getElementById('texto-idioma');
    if(textoIdiomaEl) textoIdiomaEl.innerText = novoIdioma;

    window.aplicarTraducao(novoIdioma);
    
    if(typeof Swal !== 'undefined') {
        Swal.fire({
            toast: true,
            position: 'top-end',
            icon: 'success',
            title: `Idioma: ${novoIdioma}`,
            showConfirmButton: false,
            timer: 1500,
            background: document.documentElement.classList.contains('dark') ? '#1a1b26' : '#ffffff',
            color: document.documentElement.classList.contains('dark') ? '#ffffff' : '#1f2937'
        });
    }
};

window.aplicarTraducao = function(lang) {
    const dicionario = traducoes[lang] || traducoes['PT-BR'];
    document.querySelectorAll('[data-i18n]').forEach(el => {
        const chave = el.getAttribute('data-i18n');
        if (dicionario[chave]) el.innerText = dicionario[chave];
    });
    if(typeof atualizarTextosXP === 'function') window.atualizarTextosXP(lang);
};

// ==========================================
// INTERFACE E MENUS
// ==========================================
window.togglePerfil = function() { const m = document.getElementById('menu-perfil'); if(m) m.classList.toggle('hidden'); };
window.toggleIdioma = function() { const m = document.getElementById('menu-idioma'); if(m) m.classList.toggle('hidden'); };
window.toggleNotificacoes = function() {
    const p = document.getElementById('painel-notificacoes');
    if(!p) return;
    if (p.classList.contains('opacity-0')) {
        p.classList.remove('opacity-0', 'pointer-events-none', 'scale-95');
        p.classList.add('opacity-100', 'scale-100');
    } else {
        p.classList.add('opacity-0', 'pointer-events-none', 'scale-95');
        p.classList.remove('opacity-100', 'scale-100');
    }
};

let menuAberto = false;
window.toggleMenu = function() {
    const menuLateral = document.getElementById('menu-lateral');
    const overlay = document.getElementById('overlay');
    if (!menuLateral) return;
    menuAberto = !menuAberto;
    if (menuAberto) {
        menuLateral.classList.remove('w-14'); menuLateral.classList.add('w-64');
        if(overlay) overlay.classList.remove('hidden');
        document.querySelectorAll('.menu-texto').forEach(t => t.classList.remove('hidden'));
    } else {
        menuLateral.classList.remove('w-64'); menuLateral.classList.add('w-14');
        if(overlay) overlay.classList.add('hidden');
        document.querySelectorAll('.menu-texto').forEach(t => t.classList.add('hidden'));
    }
};

let mobileMenuAberto = false;
window.toggleMobileMenu = function() {
    const menuMais = document.getElementById('mobile-menu-mais');
    const overlayMais = document.getElementById('mobile-menu-overlay');
    if (!menuMais || !overlayMais) return;
    mobileMenuAberto = !mobileMenuAberto;
    if (mobileMenuAberto) {
        overlayMais.classList.remove('hidden');
        setTimeout(() => { overlayMais.classList.remove('opacity-0'); menuMais.classList.remove('translate-y-full'); }, 10);
    } else {
        overlayMais.classList.add('opacity-0'); menuMais.classList.add('translate-y-full');
        setTimeout(() => { overlayMais.classList.add('hidden'); }, 300);
    }
};

window.confirmarAcao = function(event, formulario, titulo, mensagem, textoBotaoConfirma = 'Sim, continuar') {
    event.preventDefault();
    const isDark = document.documentElement.classList.contains('dark');
    Swal.fire({
        title: titulo, text: mensagem, icon: 'warning', showCancelButton: true, confirmButtonColor: '#3b82f6', cancelButtonColor: '#ef4444',
        confirmButtonText: `<i data-lucide="check" class="w-4 h-4 inline-block mr-1 align-middle"></i> ${textoBotaoConfirma}`,
        cancelButtonText: 'Cancelar', background: isDark ? '#1f2937' : '#ffffff', color: isDark ? '#f3f4f6' : '#111827',
        customClass: { popup: 'rounded-2xl shadow-xl border border-gray-200 dark:border-gray-700' },
        didOpen: () => { if (typeof lucide !== 'undefined') lucide.createIcons(); }
    }).then((result) => { if (result.isConfirmed) formulario.submit(); });
};

// ==========================================
// MODAIS GLOBAIS
// ==========================================
window.abrirModalMeta = function() {
    const m = document.getElementById('modal-nova-meta'), c = document.getElementById('card-nova-meta');
    m.classList.remove('hidden'); m.classList.add('flex');
    setTimeout(() => { m.classList.remove('opacity-0', 'pointer-events-none'); c.classList.remove('scale-95'); }, 10);
};
window.fecharModalMeta = function() {
    const m = document.getElementById('modal-nova-meta'), c = document.getElementById('card-nova-meta');
    m.classList.add('opacity-0', 'pointer-events-none'); c.classList.add('scale-95');
    setTimeout(() => { m.classList.add('hidden'); m.classList.remove('flex'); }, 300);
};

window.abrirModalEditarGasto = function(id, desc, valor, data, cat, quinz) {
    if(window.isDraggingAlert) return;
    document.getElementById('edit-gasto-desc').value = desc;
    document.getElementById('edit-gasto-valor').value = parseFloat(valor).toFixed(2);
    document.getElementById('edit-gasto-data').value = data;
    document.getElementById('edit-gasto-categoria').value = cat;
    document.getElementById('edit-gasto-quinzena').value = quinz;
    document.getElementById('form-editar-gasto').action = '/editar_gasto/' + id + '?origem=index';
    const m = document.getElementById('modal-editar-gasto'), c = document.getElementById('card-editar-gasto');
    m.classList.remove('hidden'); m.classList.add('flex');
    setTimeout(() => { m.classList.remove('opacity-0', 'pointer-events-none'); c.classList.remove('scale-95'); }, 10);
};
window.fecharModalEditarGasto = function() {
    const m = document.getElementById('modal-editar-gasto'), c = document.getElementById('card-editar-gasto');
    m.classList.add('opacity-0', 'pointer-events-none'); c.classList.add('scale-95');
    setTimeout(() => { m.classList.add('hidden'); m.classList.remove('flex'); }, 300);
};

window.abrirModalProjecao = function() {
    window.ganharXP(2, 'Projeção Analisada!');
    const m = document.getElementById('modal-projecao');
    m.classList.remove('hidden');
    setTimeout(() => { m.classList.remove('opacity-0'); m.querySelector('div').classList.remove('scale-95'); }, 10);
};
window.fecharModalProjecao = function() {
    const m = document.getElementById('modal-projecao');
    m.classList.add('opacity-0'); m.querySelector('div').classList.add('scale-95');
    setTimeout(() => { m.classList.add('hidden'); }, 300);
};

window.abrirModalGraficoLinha = function() {
    const m = document.getElementById('modal-grafico-linha');
    m.classList.remove('hidden');
    setTimeout(() => {
        m.classList.remove('opacity-0'); m.querySelector('div').classList.remove('scale-95');
        window.dispatchEvent(new Event('resize'));
        window.ganharXP(5, 'xp_motivo_tendencia');
    }, 10);
};
window.fecharModalGraficoLinha = function() {
    const m = document.getElementById('modal-grafico-linha');
    m.classList.add('opacity-0'); m.querySelector('div').classList.add('scale-95');
    setTimeout(() => { m.classList.add('hidden'); }, 300);
};

window.scrollAlertas = function(direcao) {
    const c = document.getElementById('alertas-vencimento');
    if(c) c.scrollBy({ left: direcao * 240, behavior: 'smooth' });
};

let valoresOcultos = localStorage.getItem('valoresOcultos') === 'true';
window.atualizarVisibilidade = function() {
    const elementos = document.querySelectorAll('.valor-sensivel');
    const icone = document.getElementById('icone-olho');
    if (valoresOcultos) {
        elementos.forEach(el => el.textContent = 'R$ •••••');
        if (icone) icone.setAttribute('data-lucide', 'eye-off');
    } else {
        elementos.forEach(el => el.textContent = el.getAttribute('data-valor'));
        if (icone) icone.setAttribute('data-lucide', 'eye');
    }
    if (typeof lucide !== 'undefined') lucide.createIcons();
};
window.toggleValores = function() {
    valoresOcultos = !valoresOcultos;
    localStorage.setItem('valoresOcultos', valoresOcultos);
    window.atualizarVisibilidade();
};

// ==========================================
// GAMIFICAÇÃO & XP
// ==========================================
const XP_POR_NIVEL = 500;
window.carregarSistemaXP = function() {
    let xpAtual = parseInt(localStorage.getItem('user_xp')) || 0;
    let ultimoLogin = localStorage.getItem('user_last_login');
    let dataHoje = new Date().toLocaleDateString();

    if(ultimoLogin !== dataHoje) {
        xpAtual += 50; 
        localStorage.setItem('user_last_login', dataHoje);
        localStorage.setItem('user_xp', xpAtual);
        setTimeout(() => window.mostrarToastXP(50, 'xp_motivo_login'), 1000);
    }
    window.atualizarInterfaceXP(xpAtual);
};

window.ganharXP = function(quantidade, chaveMotivo) {
    let xpAtual = parseInt(localStorage.getItem('user_xp')) || 0;
    xpAtual += quantidade;
    localStorage.setItem('user_xp', xpAtual);
    window.atualizarInterfaceXP(xpAtual);
    window.mostrarToastXP(quantidade, chaveMotivo);
};

window.atualizarInterfaceXP = function(xpTotal) {
    let nivel = Math.floor(xpTotal / XP_POR_NIVEL) + 1;
    let xpAtualNivel = xpTotal % XP_POR_NIVEL;
    let progressoPerc = (xpAtualNivel / XP_POR_NIVEL) * 100;

    const b = document.getElementById('user-level-badge'); if(b) b.innerText = 'Lvl ' + nivel;
    const t = document.getElementById('xp-text'); if(t) t.innerText = `${xpAtualNivel} / ${XP_POR_NIVEL} XP`;
    const bar = document.getElementById('xp-bar'); if(bar) bar.style.width = `${progressoPerc}%`;
    window.atualizarTextosXP(localStorage.getItem('idioma_sistema') || 'PT-BR', nivel);
};

window.atualizarTextosXP = function(lang, nivelOverride = null) {
    let xpTotal = parseInt(localStorage.getItem('user_xp')) || 0;
    let nivel = nivelOverride || Math.floor(xpTotal / XP_POR_NIVEL) + 1;
    let txt = document.getElementById('xp-motivational-text');
    if(txt) {
        const d = traducoes[lang] || traducoes['PT-BR'];
        if(nivel < 5) txt.innerText = d['xp_lvl1'];
        else if(nivel < 15) txt.innerText = d['xp_lvl2'];
        else txt.innerText = d['xp_lvl3'];
    }
};

window.mostrarToastXP = function(quantidade, chaveMotivo) {
    const lang = localStorage.getItem('idioma_sistema') || 'PT-BR';
    const motivoText = traducoes[lang] ? (traducoes[lang][chaveMotivo] || chaveMotivo) : chaveMotivo;
    const toast = document.createElement('div');
    toast.className = `toast-xp fixed bottom-24 right-4 md:bottom-10 md:right-10 flex items-center gap-2 bg-gradient-to-r from-blue-600 to-indigo-600 text-white px-4 py-3 rounded-2xl shadow-xl border border-blue-400/30`;
    toast.innerHTML = `<div class="bg-white/20 p-1.5 rounded-full"><i data-lucide="zap" class="w-4 h-4 text-yellow-300"></i></div>
                       <div><p class="text-xs font-black">+${quantidade} XP</p><p class="text-[9px] font-medium opacity-90">${motivoText}</p></div>`;
    document.body.appendChild(toast);
    if(typeof lucide !== 'undefined') lucide.createIcons();
    setTimeout(() => toast.remove(), 3000);
};

// ==========================================
// INICIALIZAÇÃO GLOBAL DOM
// ==========================================
document.addEventListener("DOMContentLoaded", function() {
    window.aplicarTraducao(localStorage.getItem('idioma_sistema') || 'PT-BR');
    if (typeof lucide !== 'undefined') lucide.createIcons();

    const htmlElement = document.documentElement;
    if (localStorage.getItem('tema') === 'dark') htmlElement.classList.add('dark');
    
    const iconeTema = document.getElementById('icone-tema');
    if (iconeTema) {
        iconeTema.setAttribute('data-lucide', htmlElement.classList.contains('dark') ? 'sun' : 'moon');
        lucide.createIcons();
    }

    const btnTema = document.getElementById('btn-tema');
    if (btnTema) {
        btnTema.addEventListener('click', (event) => {
            const isDark = htmlElement.classList.contains('dark');
            const executeToggle = () => {
                htmlElement.classList.toggle('dark');
                localStorage.setItem('tema', htmlElement.classList.contains('dark') ? 'dark' : 'light');
                if(iconeTema) iconeTema.setAttribute('data-lucide', htmlElement.classList.contains('dark') ? 'sun' : 'moon');
                lucide.createIcons();
                window.dispatchEvent(new Event('themeChanged')); 
            };
            if (!document.startViewTransition) { executeToggle(); return; }
            const x = event?.clientX ?? window.innerWidth / 2;
            const y = event?.clientY ?? window.innerHeight / 2;
            const endRadius = Math.hypot(Math.max(x, innerWidth - x), Math.max(y, innerHeight - y));
            const transition = document.startViewTransition(() => { executeToggle(); });
            transition.ready.then(() => {
                const clipPath = [ `circle(0px at ${x}px ${y}px)`, `circle(${endRadius}px at ${x}px ${y}px)` ];
                htmlElement.animate({ clipPath: isDark ? [...clipPath].reverse() : clipPath }, { duration: 500, easing: "ease-out", pseudoElement: isDark ? "::view-transition-old(root)" : "::view-transition-new(root)" });
            });
        });
    }

    document.addEventListener('click', function(e) {
        ['perfil', 'idioma', 'notificacoes'].forEach(id => {
            const btn = document.getElementById('btn-' + id) || document.querySelector(`[onclick="toggleNotificacoes()"]`);
            const menu = document.getElementById(id === 'notificacoes' ? 'painel-notificacoes' : 'menu-' + id);
            if (btn && menu && !btn.contains(e.target) && !menu.contains(e.target)) {
                if(id === 'notificacoes') {
                    menu.classList.add('opacity-0', 'pointer-events-none', 'scale-95');
                    menu.classList.remove('opacity-100', 'scale-100');
                } else {
                    menu.classList.add('hidden');
                }
            }
        });
        if (e.target === document.getElementById('modal-projecao')) window.fecharModalProjecao();
        if (e.target === document.getElementById('modal-grafico-linha')) window.fecharModalGraficoLinha();
        if (e.target === document.getElementById('modal-editar-gasto') && !document.getElementById('card-editar-gasto').contains(e.target)) window.fecharModalEditarGasto();
        if (e.target === document.getElementById('modal-nova-meta') && !document.getElementById('card-nova-meta').contains(e.target)) window.fecharModalMeta();
    });
});