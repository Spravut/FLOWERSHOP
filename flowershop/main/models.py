from django.db import models
from django.contrib.auth.models import User
from model_utils import FieldTracker

class Category(models.Model):
    name = models.CharField(max_length=100)
    slug = models.SlugField(unique=True)
    
    def __str__(self):
        return self.name

class Product(models.Model):
    CATEGORY_CHOICES = [
        ('bouquet', 'Готовые букеты'),
        ('single', 'Цветы поштучно'),
        ('box', 'Цветы в коробке'),
        ('plant', 'Комнатные растения'),
        ('gift', 'Подарки'),
        ('sale', 'Акции'),
        ('seasonal', 'Сезонные'),
    ]
    
    OCCASION_CHOICES = [
        ('birthday', 'День рождения'),
        ('love', 'Любовь/Романтика'),
        ('wedding', 'Свадьба'),
        ('anniversary', 'Юбилей'),
        ('sorry', 'Извинения'),
        ('congrats', 'Поздравления'),
        ('universal', 'Универсальный'),
        ('spring', 'Весна'),
        ('luxury', 'Роскошь'),
        ('date', 'Свидание'),
        ('new_year', 'Новый год'),
        ('surprise', 'Сюрприз'),
        ('home', 'Дом'),
        ('office', 'Офис'),
        ('man', 'Мужчине'),
        ('relax', 'Релакс'),
        ('autumn', 'Осень'),
    ]
    
    name = models.CharField(max_length=200)
    price = models.DecimalField(max_digits=10, decimal_places=2)
    original_price = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    category = models.CharField(max_length=20, choices=CATEGORY_CHOICES)
    occasion = models.CharField(max_length=20, choices=OCCASION_CHOICES, blank=True)
    color = models.CharField(max_length=50, blank=True)
    description = models.TextField()
    image = models.ImageField(upload_to='products/')
    in_stock = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    
    def __str__(self):
        return self.name

class Cart(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    product = models.ForeignKey(Product, on_delete=models.CASCADE)
    quantity = models.IntegerField(default=1)
    created_at = models.DateTimeField(auto_now_add=True)

class Order(models.Model):
    STATUS_CHOICES = [
        ('new', 'Новый'),
        ('processing', 'В обработке'),
        ('delivering', 'Передан курьеру'),
        ('completed', 'Выполнен'),
        ('cancelled', 'Отменен'),
    ]
    
    PAYMENT_CHOICES = [
        ('online', 'Онлайн-карта'),
        ('cash', 'При получении'),
    ]
    
    user = models.ForeignKey(User, on_delete=models.CASCADE, null=True, blank=True)
    customer_name = models.CharField(max_length=100)
    phone = models.CharField(max_length=20)
    email = models.EmailField()
    address = models.TextField()
    delivery_date = models.DateField()
    delivery_time = models.CharField(max_length=50)
    payment_method = models.CharField(max_length=20, choices=PAYMENT_CHOICES)
    wishes = models.TextField(blank=True)
    total_price = models.DecimalField(max_digits=10, decimal_places=2)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='new')
    created_at = models.DateTimeField(auto_now_add=True)

    tracker = FieldTracker(fields=["status"])

    def __str__(self):
        return f"Заказ #{self.id} - {self.customer_name}"
    

class CustomBouquetRequest(models.Model):
    occasion = models.CharField('Повод', max_length=100)
    preferred_flowers = models.CharField('Предпочтительные цветы', max_length=200)
    color_scheme = models.CharField('Цветовая гамма', max_length=100)
    budget = models.IntegerField('Бюджет')
    wishes = models.TextField('Пожелания')
    name = models.CharField('Имя', max_length=100, blank=True)
    phone = models.CharField('Телефон', max_length=20, blank=True)
    email = models.EmailField('Email', blank=True)
    status = models.CharField('Статус', max_length=50, default='новая', 
                              choices=[('новая', 'Новая'), ('обработана', 'Обработана'), ('в работе', 'В работе')])
    created_at = models.DateTimeField('Создано', auto_now_add=True)
    updated_at = models.DateTimeField('Обновлено', auto_now=True)
    
    class Meta:
        verbose_name = 'Заявка на авторский букет'
        verbose_name_plural = 'Заявки на авторские букеты'
        ordering = ['-created_at']
    
    def __str__(self):
        return f'Заявка от {self.created_at.strftime("%d.%m.%Y %H:%M")} - {self.occasion}'


class Review(models.Model):
    RATING_CHOICES = [
        (5, '★★★★★'),
        (4, '★★★★☆'),
        (3, '★★★☆☆'),
        (2, '★★☆☆☆'),
        (1, '★☆☆☆☆'),
    ]
    
    user = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)
    name = models.CharField('Имя', max_length=100)
    text = models.TextField('Текст отзыва')
    rating = models.IntegerField('Оценка', choices=RATING_CHOICES, default=5)
    is_approved = models.BooleanField('Одобрен', default=False)
    created_at = models.DateTimeField('Создано', auto_now_add=True)
    
    class Meta:
        verbose_name = 'Отзыв'
        verbose_name_plural = 'Отзывы'
        ordering = ['-created_at']
    
    def __str__(self):
        return f'Отзыв от {self.name} - {self.rating}★'
    
    def get_stars(self):
        return '★' * self.rating + '☆' * (5 - self.rating)
