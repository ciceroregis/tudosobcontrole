import datetime
from decimal import Decimal
from django.db import models
from django.contrib.auth.models import User


def calcular_quinto_dia_util(ano: int, mes: int) -> datetime.date:
    """
    Calcula a data exata do 5º dia útil de um determinado mês/ano
    (considerando segunda a sexta-feira como dias úteis bancários padrão).
    """
    dias_uteis = 0
    dia = 1
    while True:
        data_atual = datetime.date(ano, mes, dia)
        if data_atual.weekday() < 5:  # 0=Seg, 1=Ter, 2=Qua, 3=Qui, 4=Sex
            dias_uteis += 1
            if dias_uteis == 5:
                return data_atual
        dia += 1


class PerfilFinanceiro(models.Model):
    MODO_QUINZENAL = 'QUINZENAL'
    MODO_MENSAL = 'MENSAL'
    MODO_CHOICES = [
        (MODO_QUINZENAL, 'Salário Dividido em 2 Datas (Adiantamento + Fechamento)'),
        (MODO_MENSAL, 'Salário em Data Única (Fluxo Mensal Tradicional)'),
    ]

    usuario = models.OneToOneField(User, on_delete=models.CASCADE, related_name='perfil')
    cpf = models.CharField(max_length=14, blank=True, default='')
    celular = models.CharField(max_length=20, blank=True, default='')
    nascimento = models.DateField(null=True, blank=True)
    idioma = models.CharField(max_length=10, default='pt_BR')

    # Saldo Inicial Geral do Usuário (substitui o antigo modelo de Contas Bancárias)
    saldo_inicial = models.DecimalField(
        max_digits=12, decimal_places=2, default=Decimal('0.00'),
        verbose_name='Saldo Inicial em Caixa (R$)'
    )

    # Configuração Dinâmica de Recebimento Salarial
    recebe_duas_datas = models.BooleanField(
        default=True,
        verbose_name='Recebe salário em duas datas?',
        help_text='Ative para separar o fluxo de caixa entre 1º Recebimento (Início do Mês) e 2º Recebimento (Meio do Mês).'
    )
    salario_bruto_mensal = models.DecimalField(
        max_digits=12, decimal_places=2, default=Decimal('6000.00'),
        verbose_name='Salário Mensal Base (R$)'
    )
    percentual_adiantamento = models.DecimalField(
        max_digits=5, decimal_places=2, default=Decimal('40.00'),
        verbose_name='% do 2º Recebimento / Adiantamento'
    )
    dia_adiantamento = models.PositiveSmallIntegerField(
        default=20,
        verbose_name='Dia do 2º Recebimento / Adiantamento (Meio do Mês)'
    )
    usa_quinto_dia_util = models.BooleanField(
        default=False,
        verbose_name='1º Recebimento no 5º Dia Útil?'
    )
    dia_fechamento_fixo = models.PositiveSmallIntegerField(
        default=5,
        verbose_name='Dia Fixo do 1º Recebimento (caso não use 5º dia útil)'
    )
    valor_adiantamento_manual = models.DecimalField(
        max_digits=12, decimal_places=2, null=True, blank=True,
        verbose_name='Valor Manual do 2º Recebimento (R$)',
        help_text='Se preenchido, substitui o cálculo por percentual.'
    )
    valor_fechamento_manual = models.DecimalField(
        max_digits=12, decimal_places=2, null=True, blank=True,
        verbose_name='Valor Manual do 1º Recebimento (R$)',
        help_text='Se preenchido, substitui o cálculo automático.'
    )
    estrutura_inicializada = models.BooleanField(default=False)

    class Meta:
        verbose_name = 'Perfil Financeiro'
        verbose_name_plural = 'Perfis Financeiros'

    def __str__(self):
        modo = 'Quinzenal (2 Datas)' if self.recebe_duas_datas else 'Mensal (Data Única)'
        return f"{self.usuario.username} - {modo}"

    @property
    def valor_adiantamento_estimado(self) -> Decimal:
        if not self.recebe_duas_datas:
            return Decimal('0.00')
        if self.valor_adiantamento_manual is not None and self.valor_adiantamento_manual > Decimal('0.00'):
            return self.valor_adiantamento_manual
        return (self.salario_bruto_mensal * (self.percentual_adiantamento / Decimal('100.00'))).quantize(Decimal('0.01'))

    @property
    def valor_fechamento_estimado(self) -> Decimal:
        if not self.recebe_duas_datas:
            if self.valor_fechamento_manual is not None and self.valor_fechamento_manual > Decimal('0.00'):
                return self.valor_fechamento_manual
            return self.salario_bruto_mensal
        if self.valor_fechamento_manual is not None and self.valor_fechamento_manual > Decimal('0.00'):
            return self.valor_fechamento_manual
        return (self.salario_bruto_mensal - self.valor_adiantamento_estimado).quantize(Decimal('0.01'))

    @property
    def label_ciclo_fechamento(self) -> str:
        if not self.recebe_duas_datas:
            return "Salário Integral (Data Única)"
        if self.usa_quinto_dia_util:
            return "1º Recebimento • 5º Dia Útil"
        return f"1º Recebimento • Dia {self.dia_fechamento_fixo:02d}"

    @property
    def label_ciclo_adiantamento(self) -> str:
        return f"2º Recebimento • Dia {self.dia_adiantamento:02d}"

    @property
    def label_curto_fechamento(self) -> str:
        if self.usa_quinto_dia_util:
            return "5º D.Ú."
        return f"Dia {self.dia_fechamento_fixo:02d}"

    @property
    def label_curto_adiantamento(self) -> str:
        return f"Dia {self.dia_adiantamento:02d}"

    def data_fechamento_mes(self, ano: int, mes: int) -> datetime.date:
        if self.usa_quinto_dia_util:
            return calcular_quinto_dia_util(ano, mes)
        return datetime.date(ano, mes, min(self.dia_fechamento_fixo, 28))

    def data_adiantamento_mes(self, ano: int, mes: int) -> datetime.date:
        data_base = datetime.date(ano, mes, min(self.dia_adiantamento, 28))
        if data_base.weekday() == 5:  # Sábado
            return data_base - datetime.timedelta(days=1)
        elif data_base.weekday() == 6:  # Domingo
            return data_base - datetime.timedelta(days=2)
        return data_base


class Categoria(models.Model):
    FATOR_RECEITA = 1
    FATOR_DESPESA = -1
    FATOR_CHOICES = [
        (FATOR_RECEITA, 'Receita (+1)'),
        (FATOR_DESPESA, 'Despesa (-1)'),
    ]

    CICLO_Q1 = 'Q1_ADIANTAMENTO'
    CICLO_Q2 = 'Q2_FECHAMENTO'
    CICLO_AMBOS = 'AMBOS'
    CICLO_SUGERIDO_CHOICES = [
        (CICLO_Q2, '1º Ciclo • Início do Mês (Dia 05 / 5º D.Ú.)'),
        (CICLO_Q1, '2º Ciclo • Meio do Mês (Dia 15 / Dia 20)'),
        (CICLO_AMBOS, 'Flexível / Ambos os Ciclos'),
    ]

    usuario = models.ForeignKey(User, on_delete=models.CASCADE, related_name='categorias')
    pai = models.ForeignKey('self', null=True, blank=True, on_delete=models.CASCADE, related_name='filhos')
    descricao = models.CharField(max_length=80)
    fator = models.SmallIntegerField(choices=FATOR_CHOICES, default=FATOR_DESPESA)
    ciclo_sugerido = models.CharField(max_length=20, choices=CICLO_SUGERIDO_CHOICES, default=CICLO_AMBOS)
    icone = models.CharField(max_length=40, default='bi-tag')

    class Meta:
        ordering = ['fator', 'descricao']
        verbose_name = 'Categoria'
        verbose_name_plural = 'Categorias'

    def __str__(self):
        if self.pai:
            return f"{self.pai.descricao} › {self.descricao}"
        return self.descricao


class Lancamento(models.Model):
    CICLO_Q1 = 'Q1_ADIANTAMENTO'
    CICLO_Q2 = 'Q2_FECHAMENTO'
    CICLO_UNICO = 'MENSAL_UNICO'
    CICLO_CHOICES = [
        (CICLO_Q2, '1º Ciclo (Início do Mês • Dia 05 / 5º Dia Útil)'),
        (CICLO_Q1, '2º Ciclo (Meio do Mês • Dia 15 / Dia 20)'),
        (CICLO_UNICO, 'Ciclo Mensal Único'),
    ]

    STATUS_PAGO = 'PAGO'
    STATUS_PENDENTE = 'PENDENTE'
    STATUS_AGENDADO = 'AGENDADO'
    STATUS_ATRASADO = 'ATRASADO'
    STATUS_CHOICES = [
        (STATUS_PAGO, 'Pago / Recebido'),
        (STATUS_PENDENTE, 'Pendente'),
        (STATUS_AGENDADO, 'Agendado'),
        (STATUS_ATRASADO, 'Atrasado'),
    ]

    ORIGEM_SALARIO_Q1 = 'SALARIO_ADIANTAMENTO'
    ORIGEM_SALARIO_Q2 = 'SALARIO_FECHAMENTO'
    ORIGEM_SALARIO_UNICO = 'SALARIO_UNICO'
    ORIGEM_NORMAL = 'NORMAL'
    ORIGEM_CHOICES = [
        (ORIGEM_NORMAL, 'Lançamento Comum'),
        (ORIGEM_SALARIO_Q2, 'Salário - 1º Recebimento (Início do Mês)'),
        (ORIGEM_SALARIO_Q1, 'Salário - 2º Recebimento (Meio do Mês)'),
        (ORIGEM_SALARIO_UNICO, 'Salário - Recebimento Mensal Único'),
    ]

    usuario = models.ForeignKey(User, on_delete=models.CASCADE, related_name='lancamentos')
    categoria = models.ForeignKey(Categoria, on_delete=models.PROTECT, related_name='lancamentos')
    data = models.DateField(verbose_name='Data de Vencimento / Movimento')
    descricao = models.CharField(max_length=140, verbose_name='Descrição')
    valor = models.DecimalField(max_digits=12, decimal_places=2, verbose_name='Valor (R$)')
    ciclo = models.CharField(
        max_length=20, choices=CICLO_CHOICES, default=CICLO_Q2,
        verbose_name='Ciclo Salarial Alocado'
    )
    status = models.CharField(
        max_length=15, choices=STATUS_CHOICES, default=STATUS_PAGO,
        verbose_name='Status de Pagamento'
    )
    origem_salarial = models.CharField(
        max_length=25, choices=ORIGEM_CHOICES, default=ORIGEM_NORMAL
    )
    fixo_recorrente = models.BooleanField(default=False, verbose_name='Despesa/Receita Fixa Mensal')
    observacao = models.CharField(max_length=255, blank=True, default='')

    class Meta:
        ordering = ['data', 'id']
        verbose_name = 'Lançamento'
        verbose_name_plural = 'Lançamentos'

    def __str__(self):
        sinal = '+' if self.categoria.fator > 0 else '-'
        return f"{self.data:%d/%m/%Y} | {self.descricao} ({sinal} R$ {self.valor})"

    @property
    def valor_assinado(self) -> Decimal:
        return self.valor * Decimal(self.categoria.fator)

    @property
    def is_receita(self) -> bool:
        return self.categoria.fator > 0

    @property
    def is_ciclo_adiantamento(self) -> bool:
        return self.ciclo == self.CICLO_Q1

    @property
    def is_ciclo_fechamento(self) -> bool:
        return self.ciclo == self.CICLO_Q2

    def save(self, *args, **kwargs):
        if not self.ciclo or self.ciclo == self.CICLO_UNICO:
            perfil = getattr(self.usuario, 'perfil', None)
            if perfil and perfil.recebe_duas_datas:
                dia_corte = perfil.dia_adiantamento
                if self.data.day >= dia_corte:
                    self.ciclo = self.CICLO_Q1
                else:
                    self.ciclo = self.CICLO_Q2
        super().save(*args, **kwargs)
