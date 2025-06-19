from django.urls import path
from . import views
from django.contrib.auth import views as auth_views

urlpatterns = [
    path('', views.home, name='home'),
    path('main/', views.home_main, name='home_main'),
    path('register/', views.register, name='register'),
    path('login/', auth_views.LoginView.as_view(template_name='prompts/login.html'), name='login'),
    path('logout/', auth_views.LogoutView.as_view(), name='logout'),
    path('prompts/', views.manage_prompts, name='prompt_list'),
    path('prompts/create/', views.manage_prompts, {'mode': 'create'}, name='prompt_create'),
    path('prompts/<int:pk>/', views.manage_prompts, {'mode': 'detail'}, name='prompt_detail'),
    path('prompts/<int:pk>/edit/', views.manage_prompts, {'mode': 'edit'}, name='prompt_edit'),
    path('prompts/<int:pk>/delete/', views.prompt_delete, name='prompt_delete'),
    path('api/prompt/<int:pk>/update/', views.update_prompt, name='update_prompt'),
    path('api/ollama_chat/', views.ollama_chat, name='ollama_chat'),
    path('tags/', views.tag_manage, name='tag_manage'),
    path('prompt_manage/', views.prompt_manage, name='prompt_manage'),
] 