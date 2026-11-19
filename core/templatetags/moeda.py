from decimal import Decimal, InvalidOperation
from django import template

register = template.Library()


@register.filter(name='moeda')
def moeda(valor):
    """
    Formata qualquer número ou Decimal no padrão monetário brasileiro:
    Ex: 5100 -> 'R$ 5.100,00' | -2100.5 -> '-R$ 2.100,50'
    """
    if valor is None or valor == '':
        return 'R$ 0,00'
    try:
        dec = Decimal(str(valor)).quantize(Decimal('0.01'))
    except (InvalidOperation, ValueError, TypeError):
        return 'R$ 0,00'

    negativo = dec < 0
    dec_abs = abs(dec)
    inteiro, centavos = f"{dec_abs:.2f}".split('.')
    # Insere ponto a cada 3 dígitos da parte inteira
    inteiro_formatado = f"{int(inteiro):,}".replace(',', '.')
    prefixo = '-R$ ' if negativo else 'R$ '
    return f"{prefixo}{inteiro_formatado},{centavos}"


@register.filter(name='moeda_sem_rs')
def moeda_sem_rs(valor):
    """
    Formata apenas o número no padrão brasileiro sem o prefixo R$:
    Ex: 8500 -> '8.500,00' (ideal para preencher inputs com máscara monetária).
    """
    if valor is None or valor == '':
        return ''
    try:
        dec = Decimal(str(valor)).quantize(Decimal('0.01'))
    except (InvalidOperation, ValueError, TypeError):
        return ''

    negativo = dec < 0
    dec_abs = abs(dec)
    inteiro, centavos = f"{dec_abs:.2f}".split('.')
    inteiro_formatado = f"{int(inteiro):,}".replace(',', '.')
    sinal = '-' if negativo else ''
    return f"{sinal}{inteiro_formatado},{centavos}"
