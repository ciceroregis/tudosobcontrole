from django.contrib import admin
from .models import PerfilFinanceiro, Categoria, Lancamento

admin.site.register(PerfilFinanceiro)
admin.site.register(Categoria)
admin.site.register(Lancamento)
