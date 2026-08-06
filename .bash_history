git status
cd/mysite
git init
git remote add origin https://github.com/ricardohir3-alt/gestao-financeira-flask
git add .
git commit -m "feat(ui): refatoracao do dashboard, novo grafico de score tricolor, modais otimizados e tipografia clean"
git branch -M main
git push -u origin main
git rm --cached mysite
rm -rf mysite/.git
git add mysite
git commit -m "corrige estrutura da pasta mysite"
git push
exit
