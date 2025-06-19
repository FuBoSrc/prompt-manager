from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth import login
from django.contrib import messages
from .models import User, Prompt, Tag, Menu
from django import forms
from django.contrib.auth.decorators import login_required
from django.forms import ModelForm, ModelMultipleChoiceField
from django.forms.widgets import SelectMultiple
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST, require_http_methods, require_GET
from django.http import JsonResponse, HttpResponseNotAllowed
import json
import requests # 引入 requests 库
from langchain_community.llms import Ollama
from langchain.callbacks.manager import CallbackManager
from langchain.callbacks.streaming_stdout import StreamingStdOutCallbackHandler
from django.utils import timezone
from django.core.files.storage import default_storage
import os
import tempfile

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
    menu = forms.ModelChoiceField(queryset=Menu.objects.all(), required=True, label='分类')
    class Meta:
        model = Prompt
        fields = ['title', 'content', 'description', 'tags', 'version', 'menu']

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
        menus = Menu.objects.all().order_by('parent_id', 'id')
        if request.method == 'POST':
            form = PromptForm(request.POST)
            form.fields['tags'].queryset = tags
            form.fields['menu'].queryset = menus
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
            form.fields['menu'].queryset = menus
        return render(request, 'prompts/prompt_list.html', {'form': form, 'tags': tags, 'mode': mode})

    elif mode == 'edit':
        prompt = get_object_or_404(Prompt, pk=pk, owner=request.user)
        menus = Menu.objects.all().order_by('parent_id', 'id')
        if request.method == 'POST':
            form = PromptForm(request.POST, instance=prompt)
            form.fields['tags'].queryset = tags
            form.fields['menu'].queryset = menus
            if form.is_valid():
                form.save()
                messages.success(request, '提示词已更新！')
                return redirect('prompt_list')  # Redirect to list view
        else:
            form = PromptForm(instance=prompt)
            form.fields['tags'].queryset = tags
            form.fields['menu'].queryset = menus
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

# 菜单树递归序列化

def serialize_menu(menu):
    return {
        'id': menu.id,
        'name': menu.name,
        'parent': menu.parent_id,
        'children': [serialize_menu(child) for child in menu.children.all().order_by('id')],
        'created_at': menu.created_at,
        'updated_at': menu.updated_at,
    }

@csrf_exempt
def menu_api(request, menu_id=None):
    if request.method == 'GET':
        # 查询菜单树
        roots = Menu.objects.filter(parent=None).order_by('id')
        data = [serialize_menu(menu) for menu in roots]
        return JsonResponse({'success': True, 'menus': data})
    elif request.method == 'POST':
        # 新增菜单
        try:
            data = json.loads(request.body)
            name = data.get('name')
            parent_id = data.get('parent')
            parent = Menu.objects.get(id=parent_id) if parent_id else None
            menu = Menu.objects.create(name=name, parent=parent)
            return JsonResponse({'success': True, 'menu': serialize_menu(menu)})
        except Exception as e:
            return JsonResponse({'success': False, 'error': str(e)})
    elif request.method == 'PUT' and menu_id:
        # 修改菜单
        try:
            data = json.loads(request.body)
            menu = Menu.objects.get(id=menu_id)
            menu.name = data.get('name', menu.name)
            parent_id = data.get('parent')
            menu.parent = Menu.objects.get(id=parent_id) if parent_id else None
            menu.save()
            return JsonResponse({'success': True, 'menu': serialize_menu(menu)})
        except Exception as e:
            return JsonResponse({'success': False, 'error': str(e)})
    elif request.method == 'DELETE' and menu_id:
        # 删除菜单
        try:
            menu = Menu.objects.get(id=menu_id)
            menu.delete()
            return JsonResponse({'success': True})
        except Exception as e:
            return JsonResponse({'success': False, 'error': str(e)})
    else:
        return HttpResponseNotAllowed(['GET', 'POST', 'PUT', 'DELETE'])

@require_GET
def ollama_models(request):
    try:
        # Query local Ollama service for models
        response = requests.get("http://localhost:11434/api/tags", timeout=5)
        response.raise_for_status()
        data = response.json()
        # The models are in data['models'] or data['models'][i]['name'] depending on Ollama's API
        # For Ollama v0.1.34+, the endpoint returns {"models": [{"name": "llama2"}, ...]}
        models = [m['name'] for m in data.get('models', []) if 'embed' not in m['name']]
        return JsonResponse({'success': True, 'models': models})
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=500)

@csrf_exempt
@login_required
@require_POST
def import_prompts_excel(request):
    user = request.user
    file = request.FILES.get('file')
    if not file:
        return JsonResponse({'success': False, 'error': '未收到上传文件'}, status=400)
    filename = file.name.lower()
    if not (filename.endswith('.xlsx') or filename.endswith('.xls')):
        return JsonResponse({'success': False, 'error': '仅支持Excel文件（.xls, .xlsx）'}, status=400)

    # Save file to temp location
    with tempfile.NamedTemporaryFile(delete=False, suffix=os.path.splitext(filename)[1]) as tmp:
        for chunk in file.chunks():
            tmp.write(chunk)
        tmp_path = tmp.name

    try:
        if filename.endswith('.xlsx'):
            import openpyxl
            wb = openpyxl.load_workbook(tmp_path)
            ws = wb.active
            rows = list(ws.iter_rows(values_only=True))
        else:
            import xlrd
            wb = xlrd.open_workbook(tmp_path)
            ws = wb.sheet_by_index(0)
            rows = [ws.row_values(i) for i in range(ws.nrows)]
        if not rows or len(rows) < 2:
            return JsonResponse({'success': False, 'error': 'Excel文件内容为空或缺少数据行'}, status=400)
        header = [str(h).strip().lower() for h in rows[0]]
        if 'title' not in header or 'content' not in header:
            return JsonResponse({'success': False, 'error': 'Excel文件必须包含title和content字段'}, status=400)
        idx_title = header.index('title')
        idx_content = header.index('content')
        idx_desc = header.index('description') if 'description' in header else None
        from .models import Prompt
        imported = 0
        for row in rows[1:]:
            title = row[idx_title]
            content = row[idx_content]
            if title and content:
                title = str(row[idx_title]).strip()
                content = str(row[idx_content]).strip()
                description = str(row[idx_desc]).strip() if idx_desc is not None else ''
                try:
                    prompt = Prompt(
                        title=title,
                        content=content,
                        description=description,
                        owner=user,
                        created_at=timezone.now(),
                        updated_at=timezone.now(),
                        menu_id=1
                    )
                    prompt.save()
                    imported += 1
                except Exception as db_err:
                    return JsonResponse({'success': False, 'error': f'导入失败：{str(db_err)}'}, status=500)
        return JsonResponse({'success': True, 'imported': imported})
    except Exception as e:
        return JsonResponse({'success': False, 'error': f'解析Excel失败: {str(e)}'}, status=500)
    finally:
        os.remove(tmp_path)

@csrf_exempt
@login_required
@require_POST
def save_prompt(request):
    try:
        data = json.loads(request.body)
        title = data.get('title', '').strip()
        content = data.get('content', '').strip()
        role = data.get('role', '').strip()
        goal = data.get('goal', '').strip()
        context = data.get('context', '').strip()
        output_format = data.get('output_format', '').strip()
        example = data.get('example', '').strip()
        tags = data.get('tags', [])
        menu_id = data.get('menu_id', 1)
        # 校验必填
        if not title or not content or not role or not goal:
            return JsonResponse({'success': False, 'error': '标题、内容、角色、目标为必填项'}, status=400)
        prompt = Prompt.objects.create(
            title=title,
            content=content,
            role=role,
            goal=goal,
            context=context,
            output_format=output_format,
            example=example,
            owner=request.user,
            menu_id=menu_id
        )
        if tags:
            prompt.tags.set(tags)
        prompt.save()
        return JsonResponse({'success': True, 'id': prompt.id})
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=500)

@csrf_exempt
@login_required
@require_POST
def optimize_prompt(request):
    try:
        data = json.loads(request.body)
        content = data.get('content', '').strip()
        if not content:
            return JsonResponse({'success': False, 'error': 'content为必填项'}, status=400)
        # 读取系统提示词
        optimize_path = os.path.join(os.path.dirname(__file__), 'optimize.md')
        with open(optimize_path, 'r', encoding='utf-8') as f:
            system_prompt = f.read()
        # 构造llm输入
        user_input = content
        # 这里假设有llm_api(system_prompt, user_input)函数，返回优化结果
        # 你可以替换为实际的llm调用代码
        result = call_llm(system_prompt, user_input)
        return JsonResponse({'success': True, 'template': result})
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=500)

def call_llm(system_prompt, user_input):
    # TODO: 替换为实际的LLM调用逻辑
    # 这里只是示例，返回拼接内容
    inputs = f"[系统提示词]\n{system_prompt}\n[用户输入]\n{user_input}"
    results = gemini_models(user_input=inputs)
    return results

def gemini_models(user_input):
    print(user_input)
    try:
        url = "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key=AIzaSyCFYiouMGo8GstBBGGDuLk2Y6KOX--d638"
        headers = {"Content-Type": "application/json"}
        payload = {
            "contents": [
                {
                    "parts": [
                        {"text": user_input}
                    ]
                }
            ]
        }
        response = requests.post(url, headers=headers, json=payload, timeout=100)
        response.raise_for_status()
        data = response.json()
        candidates = data.get('candidates', [])
        if not candidates:
            return ''
        parts = candidates[0].get('content', {}).get('parts', [])
        text = ''.join([part.get('text', '') for part in parts])
        return text
    except Exception as e:
        print(e)
        return ''
