import datetime
from decimal import Decimal
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required, user_passes_test
from django.contrib.auth.models import User
from django.contrib import messages

from .models import PerfilFinanceiro, Categoria, Lancamento
from .forms import RegistroUsuarioForm, PerfilSalarialForm, CategoriaForm, LancamentoForm
from .services import inicializar_estrutura_padrao_usuario, gerar_lancamentos_salariais_mes


def _calcular_saldo_anterior(user: User, data_limite: datetime.date) -> Decimal:
    perfil, _ = PerfilFinanceiro.objects.get_or_create(usuario=user)
    saldo = perfil.saldo_inicial
    anteriores = Lancamento.objects.filter(usuario=user, data__lt=data_limite).select_related('categoria')
    for lanc in anteriores:
        saldo += lanc.valor_assinado
    return saldo


def _construir_matriz_fluxo_quinzenal(user: User, ano: int, mes: int):
    """
    Constrói a estrutura completa do Fluxo de Caixa Dinâmico diretamente para o usuário
    (sem módulo de Contas Bancárias):
    - Suporta o Modo Quinzenal (2 Datas: 1º Ciclo Início do Mês + 2º Ciclo Meio do Mês)
    - Suporta o Modo Mensal Tradicional (Data Única)
    """
    perfil, _ = PerfilFinanceiro.objects.get_or_create(usuario=user)
    primeiro_dia = datetime.date(ano, mes, 1)
    if mes == 12:
        proximo_mes = datetime.date(ano + 1, 1, 1)
    else:
        proximo_mes = datetime.date(ano, mes + 1, 1)

    saldo_anterior = _calcular_saldo_anterior(user, primeiro_dia)
    lancamentos_qs = Lancamento.objects.filter(
        usuario=user,
        data__gte=primeiro_dia, data__lt=proximo_mes
    ).select_related('categoria', 'categoria__pai').order_by('data', 'id')

    linhas_matriz = []
    linhas_fechamento_q2 = []
    linhas_adiantamento_q1 = []

    saldo_corrente = saldo_anterior

    # Totais 1º Ciclo (Início do Mês - ex: Dia 05 ou 5º Dia Útil)
    rec_q2 = Decimal('0.00')
    desp_q2 = Decimal('0.00')
    pago_q2 = Decimal('0.00')
    pendente_q2 = Decimal('0.00')

    # Totais 2º Ciclo (Meio do Mês - ex: Dia 20 ou Dia 15)
    rec_q1 = Decimal('0.00')
    desp_q1 = Decimal('0.00')
    pago_q1 = Decimal('0.00')
    pendente_q1 = Decimal('0.00')

    for lanc in lancamentos_qs:
        saldo_corrente += lanc.valor_assinado
        is_q1 = (lanc.ciclo == Lancamento.CICLO_Q1)
        is_q2 = not is_q1

        valor_col_q2 = lanc.valor_assinado if is_q2 else None
        valor_col_q1 = lanc.valor_assinado if is_q1 else None

        if is_q2:
            if lanc.is_receita:
                rec_q2 += lanc.valor
            else:
                desp_q2 += lanc.valor
                if lanc.status == Lancamento.STATUS_PAGO:
                    pago_q2 += lanc.valor
                else:
                    pendente_q2 += lanc.valor
        else:
            if lanc.is_receita:
                rec_q1 += lanc.valor
            else:
                desp_q1 += lanc.valor
                if lanc.status == Lancamento.STATUS_PAGO:
                    pago_q1 += lanc.valor
                else:
                    pendente_q1 += lanc.valor

        item = {
            'obj': lanc,
            'is_q1': is_q1,
            'is_q2': is_q2,
            'valor_col_q2': valor_col_q2,
            'valor_col_q1': valor_col_q1,
            'saldo_acumulado': saldo_corrente,
        }
        linhas_matriz.append(item)
        if is_q2:
            linhas_fechamento_q2.append(item)
        else:
            linhas_adiantamento_q1.append(item)

    liquido_q2 = rec_q2 - desp_q2
    liquido_q1 = rec_q1 - desp_q1
    rec_total = rec_q2 + rec_q1
    desp_total = desp_q2 + desp_q1
    liquido_mes = rec_total - desp_total

    pct_comprometido_q2 = min(int((desp_q2 / rec_q2 * 100)) if rec_q2 > 0 else 0, 100)
    pct_comprometido_q1 = min(int((desp_q1 / rec_q1 * 100)) if rec_q1 > 0 else 0, 100)
    pct_comprometido_total = min(int((desp_total / rec_total * 100)) if rec_total > 0 else 0, 100)

    return {
        'ano': ano,
        'mes': mes,
        'nome_mes': primeiro_dia.strftime('%B/%Y').capitalize(),
        'data_fechamento_5du': perfil.data_fechamento_mes(ano, mes),
        'data_adiantamento_15': perfil.data_adiantamento_mes(ano, mes),
        'saldo_anterior': saldo_anterior,
        'saldo_final_projetado': saldo_corrente,
        'linhas_matriz': linhas_matriz,
        'linhas_fechamento_q2': linhas_fechamento_q2,
        'linhas_adiantamento_q1': linhas_adiantamento_q1,
        'resumo_q2': {
            'receitas': rec_q2,
            'despesas': desp_q2,
            'liquido': liquido_q2,
            'pago': pago_q2,
            'pendente': pendente_q2,
            'pct_comprometido': pct_comprometido_q2,
        },
        'resumo_q1': {
            'receitas': rec_q1,
            'despesas': desp_q1,
            'liquido': liquido_q1,
            'pago': pago_q1,
            'pendente': pendente_q1,
            'pct_comprometido': pct_comprometido_q1,
        },
        'resumo_mensal': {
            'receitas': rec_total,
            'despesas': desp_total,
            'liquido': liquido_mes,
            'pct_comprometido': pct_comprometido_total,
        }
    }


def login_view(request):
    if request.user.is_authenticated:
        return redirect('dashboard')
    if request.method == 'POST':
        username = request.POST.get('username', '').strip()
        password = request.POST.get('password', '')
        user = authenticate(request, username=username, password=password)
        if user is not None:
            if user.is_active:
                login(request, user)
                return redirect('dashboard')
            else:
                messages.error(request, 'Esta conta de usuário está desativada.')
        else:
            messages.error(request, 'Usuário ou senha inválidos.')
    return render(request, 'core/login.html')


def logout_view(request):
    logout(request)
    return redirect('login')


def registro_view(request):
    if request.method == 'POST':
        form = RegistroUsuarioForm(request.POST)
        if form.is_valid():
            user = form.save(commit=False)
            nome = form.cleaned_data['nome_completo']
            partes = nome.split(' ', 1)
            user.first_name = partes[0]
            user.last_name = partes[1] if len(partes) > 1 else ''
            user.set_password(form.cleaned_data['senha'])
            user.save()

            perfil = inicializar_estrutura_padrao_usuario(
                user=user,
                recebe_duas_datas=form.cleaned_data['recebe_duas_datas'],
                salario=form.cleaned_data['salario_bruto_mensal']
            )
            perfil.cpf = form.cleaned_data.get('cpf', '')
            perfil.celular = form.cleaned_data.get('celular', '')
            perfil.percentual_adiantamento = form.cleaned_data.get('percentual_adiantamento') or Decimal('40.00')
            perfil.save()

            hoje = datetime.date.today()
            gerar_lancamentos_salariais_mes(user, hoje.year, hoje.month)

            login(request, user)
            messages.success(request, f'Bem-vindo(a), {nome}! Sua estrutura financeira foi criada com sucesso.')
            return redirect('dashboard')
    else:
        form = RegistroUsuarioForm()
    return render(request, 'core/registro.html', {'form': form})


@login_required
def alternar_modo_salarial_rapido(request):
    if request.method == 'POST':
        perfil, _ = PerfilFinanceiro.objects.get_or_create(usuario=request.user)
        perfil.recebe_duas_datas = not perfil.recebe_duas_datas
        perfil.save()

        hoje = datetime.date.today()
        ano = int(request.POST.get('ano', hoje.year))
        mes = int(request.POST.get('mes', hoje.month))

        if request.POST.get('recalcular_salario') == '1':
            gerar_lancamentos_salariais_mes(request.user, ano, mes)

        modo_str = (
            f'2 Datas ({perfil.label_curto_fechamento} + {perfil.label_curto_adiantamento})'
            if perfil.recebe_duas_datas else
            f'Salário Único Mensal ({perfil.label_curto_fechamento})'
        )
        messages.success(request, f'Modo dinâmico alterado para: {modo_str}')
    return redirect(request.META.get('HTTP_REFERER', 'fluxo_quinzenal'))


@login_required
def dashboard_view(request):
    inicializar_estrutura_padrao_usuario(request.user)
    hoje = datetime.date.today()
    ano = int(request.GET.get('ano', hoje.year))
    mes = int(request.GET.get('mes', hoje.month))

    matriz = _construir_matriz_fluxo_quinzenal(request.user, ano, mes)
    lancamentos_ate_hoje = Lancamento.objects.filter(
        usuario=request.user, data__lte=hoje
    ).select_related('categoria').order_by('-data', '-id')[:8]
    lancamentos_futuros = Lancamento.objects.filter(
        usuario=request.user, data__gt=hoje
    ).select_related('categoria').order_by('data', 'id')[:8]

    context = {
        'matriz': matriz,
        'hoje': hoje,
        'lancamentos_ate_hoje': lancamentos_ate_hoje,
        'lancamentos_futuros': lancamentos_futuros,
        'form_perfil': PerfilSalarialForm(instance=request.user.perfil),
    }
    return render(request, 'core/dashboard.html', context)


@login_required
def fluxo_quinzenal_view(request):
    inicializar_estrutura_padrao_usuario(request.user)
    hoje = datetime.date.today()
    ano = int(request.GET.get('ano', hoje.year))
    mes = int(request.GET.get('mes', hoje.month))
    aba_ativa = request.GET.get('aba', 'visao_geral')

    if request.method == 'POST':
        acao = request.POST.get('acao')
        if acao == 'novo_lancamento':
            form = LancamentoForm(request.POST, user=request.user)
            if form.is_valid():
                lanc = form.save(commit=False)
                lanc.usuario = request.user
                lanc.save()
                messages.success(request, f'Lançamento "{lanc.descricao}" registrado com sucesso!')
                return redirect(f"{request.path}?ano={lanc.data.year}&mes={lanc.data.month}&aba={aba_ativa}")
        elif acao == 'editar_lancamento':
            lanc_edit = get_object_or_404(Lancamento, pk=request.POST.get('lancamento_id'), usuario=request.user)
            form_edit = LancamentoForm(request.POST, instance=lanc_edit, user=request.user)
            if form_edit.is_valid():
                atualizado = form_edit.save()
                from .templatetags.moeda import moeda
                messages.success(request, f'Lançamento/Salário "{atualizado.descricao}" atualizado manualmente para {moeda(atualizado.valor)}!')
                return redirect(f"{request.path}?ano={atualizado.data.year}&mes={atualizado.data.month}&aba={aba_ativa}")
            else:
                messages.error(request, 'Verifique os dados informados na edição do lançamento.')
        elif acao == 'configurar_salario':
            form_perfil = PerfilSalarialForm(request.POST, instance=request.user.perfil)
            if form_perfil.is_valid():
                form_perfil.save()
                if request.POST.get('gerar_no_mes') == '1':
                    gerar_lancamentos_salariais_mes(request.user, ano, mes)
                    messages.success(request, 'Configuração salarial atualizada e parcelas de salário geradas no mês!')
                else:
                    messages.success(request, 'Configuração salarial dinâmica salva com sucesso!')
                return redirect(f"{request.path}?ano={ano}&mes={mes}&aba={aba_ativa}")
        elif acao == 'gerar_salarios_mes':
            gerar_lancamentos_salariais_mes(request.user, ano, mes)
            messages.success(request, 'Parcelas salariais do mês geradas automaticamente!')
            return redirect(f"{request.path}?ano={ano}&mes={mes}&aba={aba_ativa}")

    matriz = _construir_matriz_fluxo_quinzenal(request.user, ano, mes)

    ciclo_inicial = (
        Lancamento.CICLO_Q1
        if (request.user.perfil.recebe_duas_datas and hoje.day >= request.user.perfil.dia_adiantamento)
        else Lancamento.CICLO_Q2
    )
    form_lancamento = LancamentoForm(
        user=request.user,
        initial={'data': hoje, 'ciclo': ciclo_inicial, 'status': Lancamento.STATUS_PAGO}
    )
    form_perfil = PerfilSalarialForm(instance=request.user.perfil)

    meses_lista = [
        (1, 'Janeiro'), (2, 'Fevereiro'), (3, 'Março'), (4, 'Abril'),
        (5, 'Maio'), (6, 'Junho'), (7, 'Julho'), (8, 'Agosto'),
        (9, 'Setembro'), (10, 'Outubro'), (11, 'Novembro'), (12, 'Dezembro')
    ]

    context = {
        'matriz': matriz,
        'aba_ativa': aba_ativa,
        'form_lancamento': form_lancamento,
        'form_perfil': form_perfil,
        'meses_lista': meses_lista,
        'anos_lista': [hoje.year - 1, hoje.year, hoje.year + 1],
    }
    return render(request, 'core/fluxo_quinzenal.html', context)


@login_required
def alternar_status_lancamento(request, pk):
    lanc = get_object_or_404(Lancamento, pk=pk, usuario=request.user)
    ordem = [Lancamento.STATUS_PAGO, Lancamento.STATUS_PENDENTE, Lancamento.STATUS_AGENDADO]
    idx = ordem.index(lanc.status) if lanc.status in ordem else 0
    lanc.status = ordem[(idx + 1) % len(ordem)]
    lanc.save()
    messages.info(request, f'Status de "{lanc.descricao}" alterado para {lanc.get_status_display()}.')
    return redirect(request.META.get('HTTP_REFERER', 'fluxo_quinzenal'))


@login_required
def alternar_ciclo_lancamento(request, pk):
    lanc = get_object_or_404(Lancamento, pk=pk, usuario=request.user)
    if lanc.ciclo == Lancamento.CICLO_Q1:
        lanc.ciclo = Lancamento.CICLO_Q2
    else:
        lanc.ciclo = Lancamento.CICLO_Q1
    lanc.save()
    messages.info(request, f'Ciclo de "{lanc.descricao}" movido para {lanc.get_ciclo_display()}.')
    return redirect(request.META.get('HTTP_REFERER', 'fluxo_quinzenal'))


@login_required
def excluir_lancamento(request, pk):
    lanc = get_object_or_404(Lancamento, pk=pk, usuario=request.user)
    if request.method == 'POST':
        desc = lanc.descricao
        lanc.delete()
        messages.warning(request, f'Lançamento "{desc}" excluído.')
    return redirect(request.META.get('HTTP_REFERER', 'fluxo_quinzenal'))


@login_required
def categorias_view(request):
    raizes = Categoria.objects.filter(usuario=request.user, pai__isnull=True).prefetch_related('filhos')
    if request.method == 'POST':
        acao = request.POST.get('acao')
        if acao == 'excluir':
            cat = get_object_or_404(Categoria, pk=request.POST.get('categoria_id'), usuario=request.user)
            if cat.pai is None:
                messages.error(request, 'Categorias raiz (DESPESAS / RECEITAS) não podem ser removidas.')
            elif cat.lancamentos.exists():
                messages.error(request, 'Não é possível excluir uma categoria que possui lançamentos vinculados.')
            else:
                cat.delete()
                messages.warning(request, 'Categoria excluída.')
            return redirect('categorias')
        else:
            form = CategoriaForm(request.POST, user=request.user)
            if form.is_valid():
                nova = form.save(commit=False)
                nova.usuario = request.user
                nova.fator = nova.pai.fator
                nova.save()
                messages.success(request, f'Subcategoria "{nova.descricao}" criada em {nova.pai.descricao}!')
                return redirect('categorias')
    else:
        form = CategoriaForm(user=request.user)

    return render(request, 'core/categorias.html', {'raizes': raizes, 'form': form})


@login_required
@user_passes_test(lambda u: u.is_staff or u.is_superuser)
def usuarios_admin_view(request):
    usuarios = User.objects.all().select_related('perfil').order_by('id')
    if request.method == 'POST':
        u = get_object_or_404(User, pk=request.POST.get('user_id'))
        acao = request.POST.get('acao')
        if acao == 'toggle_ativo' and u != request.user:
            u.is_active = not u.is_active
            u.save()
            messages.info(request, f'Status de {u.username} atualizado.')
        elif acao == 'toggle_admin' and u != request.user:
            u.is_staff = not u.is_staff
            u.save()
            messages.info(request, f'Permissão administrativa de {u.username} atualizada.')
        elif acao == 'toggle_quinzenal':
            perfil, _ = PerfilFinanceiro.objects.get_or_create(usuario=u)
            perfil.recebe_duas_datas = not perfil.recebe_duas_datas
            perfil.save()
            messages.info(request, f'Modo salarial de {u.username} alterado.')
        return redirect('usuarios_admin')

    return render(request, 'core/usuarios_admin.html', {'usuarios': usuarios})
