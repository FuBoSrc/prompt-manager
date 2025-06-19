from django.contrib.auth.models import AbstractUser
from django.db import models
from django.core.exceptions import ValidationError

# Create your models here.

class User(AbstractUser):
    email = models.EmailField(unique=True)

class Tag(models.Model):
    name = models.CharField(max_length=50)
    is_public = models.BooleanField(default=True)
    owner = models.ForeignKey(User, null=True, blank=True, on_delete=models.CASCADE)

    def __str__(self):
        return self.name

class Menu(models.Model):
    name = models.CharField(max_length=100)
    parent = models.ForeignKey('self', null=True, blank=True, related_name='children', on_delete=models.CASCADE)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.name

class Prompt(models.Model):
    title = models.CharField(max_length=200, unique=True)
    content = models.TextField()
    description = models.TextField(blank=True)
    tags = models.ManyToManyField(Tag, blank=True)
    version = models.CharField(max_length=20, default="1.0.0")
    owner = models.ForeignKey(User, on_delete=models.CASCADE)
    menu = models.ForeignKey(Menu, on_delete=models.PROTECT, related_name='prompts')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.title

    def clean(self):
        if Prompt.objects.exclude(pk=self.pk).filter(title=self.title).exists():
            raise ValidationError({'title': '该标题已存在，请更换标题。'})
