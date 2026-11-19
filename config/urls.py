from django.contrib import admin
from django.urls import path
from core import views

urlpatterns = [
    path('django-admin/', admin.site.urls),
    path('', views.dashboard_view, name='dashboard'),
    path('login/', views.login_view, name='login'),
    path('logout/', views.logout_view, name='logout'),
    path('registro/', views.registro_view, name='registro'),
    path('fluxo-quinzenal/', views.fluxo_quinzenal_view, name='fluxo_quinzenal'),
    path('alternar-modo-salarial/', views.alternar_modo_salarial_rapido, name='alternar_modo_salarial'),
    path('lancamento/<int:pk>/status/', views.alternar_status_lancamento, name='alternar_status_lancamento'),
    path('lancamento/<int:pk>/ciclo/', views.alternar_ciclo_lancamento, name='alternar_ciclo_lancamento'),
    path('lancamento/<int:pk>/excluir/', views.excluir_lancamento, name='excluir_lancamento'),
    path('categorias/', views.categorias_view, name='categorias'),
    path('admin-usuarios/', views.usuarios_admin_view, name='usuarios_admin'),
]
