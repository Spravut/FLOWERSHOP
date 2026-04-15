from django.contrib import admin
from .models import Product, Cart, Order, CustomBouquetRequest, Review


@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = ['name', 'price', 'category', 'in_stock', 'created_at']
    list_filter = ['category', 'occasion', 'in_stock']
    search_fields = ['name', 'description']


@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    list_display = ['id', 'customer_name', 'total_price', 'status', 'payment_method', 'created_at']
    list_filter = ['status', 'payment_method']
    search_fields = ['customer_name', 'phone', 'email']
    list_editable = ['status']
    readonly_fields = ['created_at']
    ordering = ['-created_at']
    list_per_page = 25

    fieldsets = (
        ('Статус заказа', {
            'fields': ('status',)
        }),
        ('Данные клиента', {
            'fields': ('user', 'customer_name', 'phone', 'email')
        }),
        ('Доставка и оплата', {
            'fields': ('address', 'delivery_date', 'delivery_time', 'payment_method', 'wishes')
        }),
        ('Итог', {
            'fields': ('total_price', 'created_at')
        }),
    )

    actions = ['mark_processing', 'mark_delivering', 'mark_completed', 'mark_cancelled']

    def _bulk_status_change(self, request, queryset, new_status, label):
        count = 0
        for order in queryset:
            if order.status != new_status:
                order.status = new_status
                order.save()
                count += 1
        self.message_user(request, f'Заказов переведено в "{label}": {count}')

    def mark_processing(self, request, queryset):
        self._bulk_status_change(request, queryset, 'processing', 'В обработке')
    mark_processing.short_description = 'Перевести в "В обработке"'

    def mark_delivering(self, request, queryset):
        self._bulk_status_change(request, queryset, 'delivering', 'Передан курьеру')
    mark_delivering.short_description = 'Перевести в "Передан курьеру"'

    def mark_completed(self, request, queryset):
        self._bulk_status_change(request, queryset, 'completed', 'Выполнен')
    mark_completed.short_description = 'Перевести в "Выполнен"'

    def mark_cancelled(self, request, queryset):
        self._bulk_status_change(request, queryset, 'cancelled', 'Отменён')
    mark_cancelled.short_description = 'Перевести в "Отменён"'


admin.site.register(Cart)


@admin.register(CustomBouquetRequest)
class CustomBouquetRequestAdmin(admin.ModelAdmin):
    list_display = ('created_at', 'occasion', 'budget', 'phone', 'status', 'name')
    list_filter = ('status', 'occasion', 'created_at')
    search_fields = ('name', 'phone', 'email', 'occasion', 'preferred_flowers')
    readonly_fields = ('created_at', 'updated_at')
    list_per_page = 20
    ordering = ('-created_at',)
    
    fieldsets = (
        ('Информация о заявке', {
            'fields': ('status', 'created_at', 'updated_at')
        }),
        ('Данные клиента', {
            'fields': ('name', 'phone', 'email')
        }),
        ('Детали букета', {
            'fields': ('occasion', 'preferred_flowers', 'color_scheme', 'budget', 'wishes')
        }),
    )


@admin.register(Review)
class ReviewAdmin(admin.ModelAdmin):
    list_display = ('name', 'rating', 'is_approved', 'created_at')
    list_filter = ('is_approved', 'rating', 'created_at')
    search_fields = ('name', 'text')
    list_editable = ('is_approved',)
    list_per_page = 20
    ordering = ('-created_at',)
    
    actions = ['approve_reviews', 'reject_reviews']
    
    def approve_reviews(self, request, queryset):
        queryset.update(is_approved=True)
        self.message_user(request, f'Одобрено отзывов: {queryset.count()}')
    approve_reviews.short_description = 'Одобрить выбранные отзывы'
    
    def reject_reviews(self, request, queryset):
        queryset.update(is_approved=False)
        self.message_user(request, f'Отклонено отзывов: {queryset.count()}')
    reject_reviews.short_description = 'Отклонить выбранные отзывы'
