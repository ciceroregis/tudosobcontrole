import os
import datetime
from decimal import Decimal
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from django.contrib.auth.models import User
from core.models import Categoria, Lancamento
from core.services import inicializar_estrutura_padrao_usuario, gerar_lancamentos_salariais_mes


def popular_dados():
    hoje = datetime.date.today()
    ano, mes = hoje.year, hoje.month

    # 1. Usuário Admin (Modo 2 Datas: Dia 05 e Dia 20)
    admin_user, _ = User.objects.get_or_create(
        username='admin',
        defaults={
            'first_name': 'Carlos',
            'last_name': 'Administrador (Quinzenal)',
            'email': 'admin@financeirov2.com',
            'is_staff': True,
            'is_superuser': True,
        }
    )
    admin_user.set_password('admin')
    admin_user.is_staff = True
    admin_user.is_superuser = True
    admin_user.save()

    perfil_admin = inicializar_estrutura_padrao_usuario(
        user=admin_user,
        recebe_duas_datas=True,
        salario=Decimal('8500.00')
    )
    perfil_admin.cpf = '123.456.789-00'
    perfil_admin.celular = '(11) 99999-8888'
    perfil_admin.saldo_inicial = Decimal('1500.00')
    perfil_admin.recebe_duas_datas = True
    perfil_admin.salario_bruto_mensal = Decimal('8500.00')
    perfil_admin.percentual_adiantamento = Decimal('40.00')
    perfil_admin.usa_quinto_dia_util = False
    perfil_admin.dia_fechamento_fixo = 5
    perfil_admin.dia_adiantamento = 20
    perfil_admin.save()

    Lancamento.objects.filter(usuario=admin_user).delete()

    # Gera as 2 parcelas salariais automáticas do mês (Dia 05 = R$ 5.100,00 | Dia 20 = R$ 3.400,00)
    gerar_lancamentos_salariais_mes(admin_user, ano, mes)

    cat_moradia = Categoria.objects.filter(usuario=admin_user, descricao__icontains='Moradia').first()
    cat_educacao = Categoria.objects.filter(usuario=admin_user, descricao__icontains='Educação').first()
    cat_saude = Categoria.objects.filter(usuario=admin_user, descricao__icontains='Saúde').first()
    cat_cartao = Categoria.objects.filter(usuario=admin_user, descricao__icontains='Cartão').first()
    cat_mercado = Categoria.objects.filter(usuario=admin_user, descricao__icontains='Alimentação').first()
    cat_transporte = Categoria.objects.filter(usuario=admin_user, descricao__icontains='Deslocamento').first()
    cat_lazer = Categoria.objects.filter(usuario=admin_user, descricao__icontains='Lazer').first()
    cat_rendimento = Categoria.objects.filter(usuario=admin_user, descricao__icontains='Rendimentos').first()

    # Lançamentos do 1º CICLO: RECEBIMENTO DIA 05 (Contas pagas entre dia 01 e dia 19)
    despesas_fechamento = [
        (datetime.date(ano, mes, 5), 'Aluguel + Condomínio Residencial', cat_moradia, Decimal('2100.00'), Lancamento.STATUS_PAGO, True, 'Pago no dia 05 com o 1º recebimento'),
        (datetime.date(ano, mes, 7), 'Energia Elétrica + Internet Fibra', cat_moradia, Decimal('340.00'), Lancamento.STATUS_PAGO, True, 'Débito automático - 1º Ciclo (Dia 05)'),
        (datetime.date(ano, mes, 10), 'Fatura Cartão de Crédito', cat_cartao, Decimal('1250.00'), Lancamento.STATUS_PAGO, False, 'Vencimento dia 10 - Pago com o salário do dia 05'),
        (datetime.date(ano, mes, 12), 'Plano de Saúde Familiar', cat_saude, Decimal('680.00'), Lancamento.STATUS_PAGO, True, 'Boleto dia 12 - Coberto pelo 1º Ciclo'),
        (datetime.date(ano, mes, 15), 'Rendimento CDB Liquidez Diária', cat_rendimento, Decimal('180.00'), Lancamento.STATUS_PAGO, False, 'Rendimento na 1ª metade do mês'),
    ]
    for dt, desc, cat, val, st, fixo, obs in despesas_fechamento:
        Lancamento.objects.create(
            usuario=admin_user, categoria=cat,
            data=dt, descricao=desc, valor=val,
            ciclo=Lancamento.CICLO_Q2, status=st,
            fixo_recorrente=fixo, observacao=obs
        )

    # Lançamentos do 2º CICLO: RECEBIMENTO DIA 20 (Contas pagas entre dia 20 e dia 31)
    despesas_adiantamento = [
        (datetime.date(ano, mes, 20), 'Supermercado Atacadista (Compra do Mês)', cat_mercado, Decimal('980.00'), Lancamento.STATUS_PAGO, False, 'Pago no dia 20 logo após cair a 2ª parcela'),
        (datetime.date(ano, mes, 21), 'Pós-Graduação / Mensalidade Curso', cat_educacao, Decimal('550.00'), Lancamento.STATUS_PAGO, True, 'Vencimento dia 21 - Pago com o salário do dia 20'),
        (datetime.date(ano, mes, 23), 'Combustível & Tag Pedágio', cat_transporte, Decimal('420.00'), Lancamento.STATUS_PENDENTE, False, 'Alocado no 2º Ciclo (Dia 20)'),
        (datetime.date(ano, mes, 25), 'Assinaturas Streaming & Academia', cat_lazer, Decimal('189.90'), Lancamento.STATUS_AGENDADO, True, 'Recorrente dia 25'),
        (datetime.date(ano, mes, 28), 'Feira Livre & Farmácia', cat_mercado, Decimal('310.00'), Lancamento.STATUS_AGENDADO, False, 'Final do mês - Coberto pelo salário do dia 20'),
    ]
    for dt, desc, cat, val, st, fixo, obs in despesas_adiantamento:
        Lancamento.objects.create(
            usuario=admin_user, categoria=cat,
            data=dt, descricao=desc, valor=val,
            ciclo=Lancamento.CICLO_Q1, status=st,
            fixo_recorrente=fixo, observacao=obs
        )

    # 2. Usuário Mensalista (Modo Data Única: recebe_duas_datas = False)
    mensal_user, _ = User.objects.get_or_create(
        username='mensalista',
        defaults={
            'first_name': 'Mariana',
            'last_name': 'Silva (Salário Único)',
            'email': 'mariana@financeirov2.com',
            'is_staff': False,
        }
    )
    mensal_user.set_password('admin')
    mensal_user.save()
    perfil_mensal = inicializar_estrutura_padrao_usuario(
        user=mensal_user,
        recebe_duas_datas=False,
        salario=Decimal('6000.00')
    )
    perfil_mensal.recebe_duas_datas = False
    perfil_mensal.saldo_inicial = Decimal('1000.00')
    perfil_mensal.save()
    Lancamento.objects.filter(usuario=mensal_user).delete()
    gerar_lancamentos_salariais_mes(mensal_user, ano, mes)

    print("Seed concluído com sucesso (sem módulo de contas bancárias)!")


if __name__ == '__main__':
    popular_dados()
