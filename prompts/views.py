from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth import login
from django.contrib import messages
from .models import User, Prompt, Tag
from django import forms
from django.contrib.auth.decorators import login_required
from django.forms import ModelForm, ModelMultipleChoiceField
from django.forms.widgets import SelectMultiple
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST, require_http_methods
from django.http import JsonResponse
import json
import requests # 引入 requests 库
from langchain_community.llms import Ollama
from langchain.callbacks.manager import CallbackManager
from langchain.callbacks.streaming_stdout import StreamingStdOutCallbackHandler

# Create your views here.

class RegisterForm(forms.ModelForm):
    password = forms.CharField(widget=forms.PasswordInput, label='密码')
    password2 = forms.CharField(widget=forms.PasswordInput, label='确认密码')
    class Meta:
        model = User
        fields = ['username', 'email', 'password']
        labels = {
            'username': '用户名',
            'email': '邮箱',
        }

    def clean(self):
        cleaned_data = super().clean()
        password = cleaned_data.get('password')
        password2 = cleaned_data.get('password2')
        if password and password2 and password != password2:
            self.add_error('password2', '两次输入的密码不一致')
        return cleaned_data

    def save(self, commit=True):
        user = super().save(commit=False)
        user.set_password(self.cleaned_data['password'])
        if commit:
            user.save()
        return user

def register(request):
    if request.method == 'POST':
        form = RegisterForm(request.POST)
        if form.is_valid():
            user = form.save()
            login(request, user)
            messages.success(request, '注册成功，欢迎！')
            return redirect('prompt_list')
    else:
        form = RegisterForm()
    return render(request, 'prompts/register.html', {'form': form})

@login_required
def home_main(request):
    return render(request, 'prompts/home_main.html')

def home(request):
    if request.user.is_authenticated:
        return redirect('home_main')
    return render(request, 'prompts/home.html')

class PromptForm(ModelForm):
    tags = ModelMultipleChoiceField(queryset=Tag.objects.all(), required=False, widget=SelectMultiple)
    class Meta:
        model = Prompt
        fields = ['title', 'content', 'description', 'tags', 'version']

    def clean_title(self):
        title = self.cleaned_data['title']
        qs = Prompt.objects.filter(title=title)
        if self.instance.pk:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise forms.ValidationError('该标题已存在，请更换标题。')
        return title

@login_required
def manage_prompts(request, mode='list', pk=None):
    tags = Tag.objects.filter(is_public=True) | Tag.objects.filter(owner=request.user)
    tags = tags.distinct()

    if mode == 'list':
        prompts = Prompt.objects.filter(owner=request.user).order_by('-updated_at')
        search_query = request.GET.get('q')
        if search_query:
            prompts = prompts.filter(title__icontains=search_query)
        return render(request, 'prompts/prompt_list.html', {'prompts': prompts, 'tags': tags, 'mode': mode, 'search_query': search_query})

    elif mode == 'create':
        if request.method == 'POST':
            form = PromptForm(request.POST)
            form.fields['tags'].queryset = tags
            if form.is_valid():
                prompt = form.save(commit=False)
                prompt.owner = request.user
                prompt.save()
                form.save_m2m()
                messages.success(request, '提示词已创建！')
                return redirect('prompt_list')
            else:
                messages.error(request, '创建失败，请检查表单内容。')
        else:
            form = PromptForm()
            form.fields['tags'].queryset = tags
        return render(request, 'prompts/prompt_list.html', {'form': form, 'tags': tags, 'mode': mode})

    elif mode == 'edit':
        prompt = get_object_or_404(Prompt, pk=pk, owner=request.user)
        if request.method == 'POST':
            form = PromptForm(request.POST, instance=prompt)
            form.fields['tags'].queryset = tags
            if form.is_valid():
                form.save()
                messages.success(request, '提示词已更新！')
                return redirect('prompt_list')  # Redirect to list view
        else:
            form = PromptForm(instance=prompt)
            form.fields['tags'].queryset = tags
        return render(request, 'prompts/prompt_list.html', {'form': form, 'prompt': prompt, 'tags': tags, 'mode': mode})

    elif mode == 'detail':
        prompt = get_object_or_404(Prompt, pk=pk, owner=request.user)
        return render(request, 'prompts/prompt_list.html', {'prompt': prompt, 'tags': tags, 'mode': mode})

    return redirect('prompt_list') # Default redirect

@login_required
def tag_manage(request):
    if request.method == 'POST':
        tag_name = request.POST.get('tag_name')
        if tag_name:
            # 检查用户是否已创建同名私有标签
            if Tag.objects.filter(name=tag_name, owner=request.user, is_public=False).exists():
                messages.error(request, f'你已存在名为 "{tag_name}" 的私有标签。')
            # 检查是否存在同名公共标签
            elif Tag.objects.filter(name=tag_name, is_public=True).exists():
                messages.error(request, f'名为 "{tag_name}" 的公共标签已存在，请更换名称。')
            else:
                # 创建私有标签
                Tag.objects.create(name=tag_name, owner=request.user, is_public=False)
                messages.info(request, f'标签 "{tag_name}" 已成功创建为私有标签。')
        return redirect('tag_manage')

    public_tags = Tag.objects.filter(is_public=True).order_by('name')
    private_tags = Tag.objects.filter(owner=request.user, is_public=False).order_by('name')
    return render(request, 'prompts/tag_manage.html', {
        'public_tags': public_tags,
        'private_tags': private_tags
    })

@login_required
def prompt_delete(request, pk):
    print(f'Delete request for prompt with ID: {pk}')
    print(f'Request method: {request.method}')
    print(f'Request POST data: {request.POST}')
    
    try:
        prompt = get_object_or_404(Prompt, pk=pk, owner=request.user)
        print(f'Found prompt: {prompt.title}')
        
        if request.method == 'POST':
            try:
                prompt.delete()
                print('Prompt deleted successfully')
                messages.success(request, '提示词已成功删除！')
                return redirect('prompt_list')
            except Exception as e:
                print(f'Error deleting prompt: {str(e)}')
                messages.error(request, f'删除失败：{str(e)}')
                return redirect('prompt_list')
        return render(request, 'prompts/prompt_delete_confirm.html', {'prompt': prompt})
    except Exception as e:
        print(f'Error in prompt_delete view: {str(e)}')
        messages.error(request, f'操作失败：{str(e)}')
        return redirect('prompt_list')

@csrf_exempt
@require_POST
def update_prompt(request, pk):
    try:
        prompt = get_object_or_404(Prompt, pk=pk, owner=request.user)
        data = json.loads(request.body)
        prompt.content = data.get('content', prompt.content)
        prompt.save()
        messages.success(request, '提示词内容已成功更新！')
        return JsonResponse({'success': True, 'content': prompt.content})
    except Prompt.DoesNotExist:
        messages.error(request, '提示词不存在或无权限编辑。')
        return JsonResponse({'success': False, 'error': 'Prompt not found or no permission.'}, status=404)
    except Exception as e:
        messages.error(request, f'更新失败：{str(e)}')
        return JsonResponse({'success': False, 'error': str(e)}, status=500)

@csrf_exempt
@require_http_methods(["POST"])
def ollama_chat(request):
    if request.method == 'POST':
        try:
            data = json.loads(request.body)
            model = data.get('model', 'llama2')
            prompt_content = data.get('prompt_content', '') # 左侧提示词内容
            user_input = data.get('user_input', '')
            temperature = float(data.get('temperature', 0.7))
            max_tokens = int(data.get('max_tokens', 2000))

            # 使用 LangChain 调用 Ollama
            callback_manager = CallbackManager([StreamingStdOutCallbackHandler()])
            llm = Ollama(
                model=model,
                callback_manager=callback_manager,
                base_url="http://localhost:11434",
                temperature=temperature,
                num_predict=max_tokens
            )
            
            # 构建完整的提示词
            full_prompt = f"{prompt_content}\n\nUser: {user_input}\nAssistant:"
            
            # 获取模型响应
            response = llm.invoke(full_prompt)
            
            return JsonResponse({'success': True, 'response': response})

        except Exception as e:
            print(f"Unexpected error in ollama_chat: {e}")
            return JsonResponse({'success': False, 'error': f'对话请求失败：{str(e)}'}, status=500)

    return JsonResponse({'success': False, 'error': 'Invalid request method.'}, status=405)

@login_required
def prompt_manage(request):
    return render(request, 'prompts/prompt_manage.html')
