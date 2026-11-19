from decimal import Decimal
import datetime
from django.contrib.auth.models import User
from .models import PerfilFinanceiro, Categoria, Lancamento


def inicializar_estrutura_padrao_usuario(user: User, recebe_duas_datas: bool = True, salario: Decimal = Decimal('6500.00')):
    """
    Cria o PerfilFinanceiro e a Árvore de Categorias do usuário.
    Sem necessidade de Contas Bancárias.
    """
    perfil, _ = PerfilFinanceiro.objects.get_or_create(
        usuario=user,
        defaults={
            'recebe_duas_datas': recebe_duas_datas,
            'salario_bruto_mensal': salario,
            'saldo_inicial': Decimal('0.00'),
            'percentual_adiantamento': Decimal('40.00'),
            'dia_adiantamento': 20,
            'usa_quinto_dia_util': False,
            'dia_fechamento_fixo': 5,
            'estrutura_inicializada': False,
        }
    )

    if not Categoria.objects.filter(usuario=user).exists():
        # Raiz: DESPESAS (-1)
        despesas = Categoria.objects.create(
            usuario=user, pai=None, descricao='DESPESAS',
            fator=Categoria.FATOR_DESPESA, ciclo_sugerido=Categoria.CICLO_AMBOS, icone='bi-arrow-down-circle'
        )
        sub_despesas = [
            ('Moradia (Aluguel / Condomínio / Luz)', Categoria.CICLO_Q2, 'bi-house-door'),
            ('Alimentação & Supermercado', Categoria.CICLO_Q1, 'bi-cart4'),
            ('Vestuário', Categoria.CICLO_Q1, 'bi-bag'),
            ('Deslocamento / Combustível / Transporte', Categoria.CICLO_Q1, 'bi-car-front'),
            ('Cuidados Pessoais & Farmácia', Categoria.CICLO_Q1, 'bi-heart-pulse'),
            ('Educação & Cursos', Categoria.CICLO_Q1, 'bi-mortarboard'),
            ('Saúde / Plano de Saúde', Categoria.CICLO_Q2, 'bi-hospital'),
            ('Lazer & Assinaturas (Streaming)', Categoria.CICLO_Q1, 'bi-controller'),
            ('Despesas Financeiras / Cartão de Crédito', Categoria.CICLO_Q2, 'bi-credit-card'),
        ]
        for desc, ciclo, icone in sub_despesas:
            Categoria.objects.create(
                usuario=user, pai=despesas, descricao=desc,
                fator=Categoria.FATOR_DESPESA, ciclo_sugerido=ciclo, icone=icone
            )

        # Raiz: RECEITAS (+1)
        receitas = Categoria.objects.create(
            usuario=user, pai=None, descricao='RECEITAS',
            fator=Categoria.FATOR_RECEITA, ciclo_sugerido=Categoria.CICLO_AMBOS, icone='bi-arrow-up-circle'
        )
        sub_receitas = [
            ('Salário - 1º Recebimento (Início do Mês)', Categoria.CICLO_Q2, 'bi-cash-stack'),
            ('Salário - 2º Recebimento (Meio do Mês)', Categoria.CICLO_Q1, 'bi-wallet2'),
            ('Restituições & Reembolsos', Categoria.CICLO_AMBOS, 'bi-arrow-repeat'),
            ('Rendimentos & Dividendos', Categoria.CICLO_Q2, 'bi-graph-up-arrow'),
        ]
        for desc, ciclo, icone in sub_receitas:
            Categoria.objects.create(
                usuario=user, pai=receitas, descricao=desc,
                fator=Categoria.FATOR_RECEITA, ciclo_sugerido=ciclo, icone=icone
            )

    if not perfil.estrutura_inicializada:
        perfil.estrutura_inicializada = True
        perfil.save(update_fields=['estrutura_inicializada'])

    return perfil


def gerar_lancamentos_salariais_mes(user: User, ano: int, mes: int):
    """
    Gera ou atualiza automaticamente os lançamentos de salário no mês selecionado
    diretamente para o usuário (sem vínculo com conta bancária):
    - Se recebe_duas_datas == True: gera o 1º Recebimento (ex: Dia 05 ou 5º D.Ú.) e o 2º Recebimento (ex: Dia 20 ou 15).
    - Se recebe_duas_datas == False: gera um único lançamento de Salário Integral (100%).
    """
    perfil = user.perfil
    cat_fechamento = Categoria.objects.filter(
        usuario=user, fator=Categoria.FATOR_RECEITA, pai__isnull=False
    ).order_by('id').first()

    cat_adiantamento = Categoria.objects.filter(
        usuario=user, fator=Categoria.FATOR_RECEITA, pai__isnull=False
    ).order_by('id')[1:2].first() or cat_fechamento

    data_fechamento = perfil.data_fechamento_mes(ano, mes)
    data_adiantamento = perfil.data_adiantamento_mes(ano, mes)
    hoje = datetime.date.today()

    # Remove lançamentos salariais automáticos anteriores do mesmo mês para recriar limpo
    Lancamento.objects.filter(
        usuario=user,
        data__year=ano, data__month=mes,
        origem_salarial__in=[
            Lancamento.ORIGEM_SALARIO_Q1,
            Lancamento.ORIGEM_SALARIO_Q2,
            Lancamento.ORIGEM_SALARIO_UNICO,
        ]
    ).delete()

    if perfil.recebe_duas_datas:
        rotulo_c1 = "5º Dia Útil" if perfil.usa_quinto_dia_util else f"Dia {perfil.dia_fechamento_fixo:02d}"
        Lancamento.objects.create(
            usuario=user,
            categoria=cat_fechamento,
            data=data_fechamento,
            descricao=f"Salário 1ª Parcela / Fechamento ({rotulo_c1})",
            valor=perfil.valor_fechamento_estimado,
            ciclo=Lancamento.CICLO_Q2,
            status=Lancamento.STATUS_PAGO if data_fechamento <= hoje else Lancamento.STATUS_AGENDADO,
            origem_salarial=Lancamento.ORIGEM_SALARIO_Q2,
            fixo_recorrente=True,
            observacao=f'1º Recebimento do mês — Cobre contas de 01 a {perfil.dia_adiantamento - 1:02d}'
        )
        Lancamento.objects.create(
            usuario=user,
            categoria=cat_adiantamento,
            data=data_adiantamento,
            descricao=f"Salário 2ª Parcela / Adiantamento (Dia {perfil.dia_adiantamento:02d})",
            valor=perfil.valor_adiantamento_estimado,
            ciclo=Lancamento.CICLO_Q1,
            status=Lancamento.STATUS_PAGO if data_adiantamento <= hoje else Lancamento.STATUS_AGENDADO,
            origem_salarial=Lancamento.ORIGEM_SALARIO_Q1,
            fixo_recorrente=True,
            observacao=f'2º Recebimento do mês — Cobre contas de {perfil.dia_adiantamento:02d} a 31'
        )
    else:
        rotulo_unico = "5º Dia Útil" if perfil.usa_quinto_dia_util else f"Dia {perfil.dia_fechamento_fixo:02d}"
        Lancamento.objects.create(
            usuario=user,
            categoria=cat_fechamento,
            data=data_fechamento,
            descricao=f"Salário Mensal Integral (100% - {rotulo_unico})",
            valor=perfil.valor_fechamento_estimado,
            ciclo=Lancamento.CICLO_UNICO,
            status=Lancamento.STATUS_PAGO if data_fechamento <= hoje else Lancamento.STATUS_AGENDADO,
            origem_salarial=Lancamento.ORIGEM_SALARIO_UNICO,
            fixo_recorrente=True,
            observacao='Recebimento salarial integral em data única mensal'
        )
