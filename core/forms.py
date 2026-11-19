from decimal import Decimal, InvalidOperation
from django import forms
from django.contrib.auth.models import User
from .models import PerfilFinanceiro, Categoria, Lancamento


class MoedaBRField(forms.CharField):
    """
    Campo de formulário que aceita valores formatados com máscara monetária brasileira
    (ex: 'R$ 8.500,00', '8.500,00', '-1.250,50' ou '8500.00') e converte para Decimal.
    """
    def __init__(self, *args, permite_negativo=False, **kwargs):
        self.permite_negativo = permite_negativo
        kwargs.setdefault('widget', forms.TextInput(attrs={
            'class': 'form-control mask-money',
            'inputmode': 'numeric',
            'placeholder': 'R$ 0,00',
            'autocomplete': 'off',
        }))
        super().__init__(*args, **kwargs)

    def prepare_value(self, value):
        if value is None or value == '':
            return ''
        if isinstance(value, str):
            # Se já estiver formatado em pt-BR (com vírgula), mantém
            if ',' in value:
                return value
        try:
            dec = Decimal(str(value)).quantize(Decimal('0.01'))
            neg = '-' if dec < 0 else ''
            inteiro, centavos = f"{abs(dec):.2f}".split('.')
            inteiro_fmt = f"{int(inteiro):,}".replace(',', '.')
            return f"R$ {neg}{inteiro_fmt},{centavos}"
        except (InvalidOperation, ValueError, TypeError):
            return value

    def to_python(self, value):
        if value is None:
            return None
        val_str = str(value).strip()
        if not val_str:
            return None
        # Remove símbolo R$, espaços
        negativo = '-' in val_str and self.permite_negativo
        limpo = val_str.replace('R$', '').replace(' ', '').replace('-', '').strip()
        if not limpo:
            return None
        # Se tiver vírgula (padrão BR: 8.500,00), remove pontos de milhar e troca vírgula por ponto
        if ',' in limpo:
            limpo = limpo.replace('.', '').replace(',', '.')
        try:
            dec = Decimal(limpo).quantize(Decimal('0.01'))
            return -dec if negativo else dec
        except (InvalidOperation, ValueError):
            raise forms.ValidationError('Informe um valor monetário válido (ex: R$ 1.500,00).')


class RegistroUsuarioForm(forms.ModelForm):
    nome_completo = forms.CharField(
        max_length=120, label='Nome Completo',
        widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Ex: Carlos Eduardo Silva'})
    )
    cpf = forms.CharField(
        max_length=14, label='CPF', required=False,
        widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': '000.000.000-00'})
    )
    celular = forms.CharField(
        max_length=20, label='Celular', required=False,
        widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': '(11) 99999-9999'})
    )
    recebe_duas_datas = forms.BooleanField(
        required=False, initial=True,
        label='Recebo meu salário dividido em 2 datas no mês (ex: Dia 05 e Dia 20)',
        widget=forms.CheckboxInput(attrs={'class': 'form-check-input'})
    )
    salario_bruto_mensal = MoedaBRField(
        initial=Decimal('6500.00'),
        label='Salário Mensal Total (R$)'
    )
    percentual_adiantamento = forms.DecimalField(
        max_digits=5, decimal_places=2, initial=40.00,
        label='% do 2º Recebimento (Meio do Mês)',
        widget=forms.NumberInput(attrs={'class': 'form-control', 'step': '1'})
    )
    senha = forms.CharField(
        label='Senha',
        widget=forms.PasswordInput(attrs={'class': 'form-control'})
    )
    confirmar_senha = forms.CharField(
        label='Confirmar Senha',
        widget=forms.PasswordInput(attrs={'class': 'form-control'})
    )

    class Meta:
        model = User
        fields = ['username', 'email']
        widgets = {
            'username': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Login de acesso'}),
            'email': forms.EmailInput(attrs={'class': 'form-control', 'placeholder': 'seu@email.com'}),
        }

    def clean(self):
        cleaned_data = super().clean()
        if cleaned_data.get('senha') != cleaned_data.get('confirmar_senha'):
            self.add_error('confirmar_senha', 'A confirmação de senha não confere.')
        return cleaned_data


class PerfilSalarialForm(forms.ModelForm):
    saldo_inicial = MoedaBRField(required=False, permite_negativo=True, label='Saldo Inicial em Caixa (R$)')
    salario_bruto_mensal = MoedaBRField(required=True, label='Salário Mensal Base Total (R$)')
    valor_fechamento_manual = MoedaBRField(
        required=False,
        label='Valor Manual do 1º Recebimento (R$)',
        widget=forms.TextInput(attrs={
            'class': 'form-control mask-money',
            'inputmode': 'numeric',
            'placeholder': 'Opcional: R$ 0,00 (Automático se vazio)',
            'autocomplete': 'off',
        })
    )
    valor_adiantamento_manual = MoedaBRField(
        required=False,
        label='Valor Manual do 2º Recebimento (R$)',
        widget=forms.TextInput(attrs={
            'class': 'form-control mask-money',
            'inputmode': 'numeric',
            'placeholder': 'Opcional: R$ 0,00 (Automático se vazio)',
            'autocomplete': 'off',
        })
    )

    class Meta:
        model = PerfilFinanceiro
        fields = [
            'recebe_duas_datas',
            'saldo_inicial',
            'salario_bruto_mensal',
            'percentual_adiantamento',
            'valor_fechamento_manual',
            'valor_adiantamento_manual',
            'dia_adiantamento',
            'usa_quinto_dia_util',
            'dia_fechamento_fixo',
        ]
        widgets = {
            'recebe_duas_datas': forms.CheckboxInput(attrs={'class': 'form-check-input', 'role': 'switch'}),
            'percentual_adiantamento': forms.NumberInput(attrs={'class': 'form-control', 'step': '1', 'min': '0', 'max': '100'}),
            'dia_adiantamento': forms.NumberInput(attrs={'class': 'form-control', 'min': '1', 'max': '31'}),
            'usa_quinto_dia_util': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'dia_fechamento_fixo': forms.NumberInput(attrs={'class': 'form-control', 'min': '1', 'max': '31'}),
        }

    def clean_saldo_inicial(self):
        val = self.cleaned_data.get('saldo_inicial')
        return val if val is not None else Decimal('0.00')


class CategoriaForm(forms.ModelForm):
    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        if user:
            self.fields['pai'].queryset = Categoria.objects.filter(usuario=user, pai__isnull=True)
            self.fields['pai'].required = True

    class Meta:
        model = Categoria
        fields = ['pai', 'descricao', 'ciclo_sugerido', 'icone']
        widgets = {
            'pai': forms.Select(attrs={'class': 'form-select'}),
            'descricao': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Nome da subcategoria'}),
            'ciclo_sugerido': forms.Select(attrs={'class': 'form-select'}),
            'icone': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'bi-tag'}),
        }


class LancamentoForm(forms.ModelForm):
    valor = MoedaBRField(
        required=True,
        label='Valor (R$)',
        widget=forms.TextInput(attrs={
            'class': 'form-control mask-money fw-bold',
            'inputmode': 'numeric',
            'placeholder': 'R$ 0,00',
            'autocomplete': 'off',
        })
    )

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        if user:
            self.fields['categoria'].queryset = Categoria.objects.filter(
                usuario=user, pai__isnull=False
            ).select_related('pai').order_by('fator', 'descricao')

    class Meta:
        model = Lancamento
        fields = ['data', 'descricao', 'categoria', 'valor', 'ciclo', 'status', 'fixo_recorrente', 'observacao']
        widgets = {
            'data': forms.DateInput(format='%Y-%m-%d', attrs={'class': 'form-control', 'type': 'date'}),
            'descricao': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Ex: Aluguel, Supermercado, Luz...'}),
            'categoria': forms.Select(attrs={'class': 'form-select'}),
            'ciclo': forms.Select(attrs={'class': 'form-select'}),
            'status': forms.Select(attrs={'class': 'form-select'}),
            'fixo_recorrente': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'observacao': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Opcional'}),
        }
