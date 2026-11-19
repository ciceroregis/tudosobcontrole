from .models import PerfilFinanceiro


def financeiro_context(request):
    if not request.user.is_authenticated:
        return {}

    perfil, _ = PerfilFinanceiro.objects.get_or_create(usuario=request.user)

    return {
        'perfil_usuario': perfil,
    }
