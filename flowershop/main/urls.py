from django.urls import path
from . import views

urlpatterns = [
    # Основные страницы
    path('', views.home, name='home'),
    path('about/', views.about, name='about'),
    path('catalog/', views.catalog, name='catalog'),
    path('popular/', views.popular, name='popular'),
    path('reviews/', views.reviews, name='reviews'),
    path('custom/', views.custom, name='custom'),
    path('custom-bouquet/', views.custom_bouquet, name='custom_bouquet'),
    
    # Аутентификация
    path('login/', views.login_view, name='login'),
    path('logout/', views.logout_view, name='logout'),
    path('register/', views.register_view, name='register'),
    path('profile/', views.profile, name='profile'),
    
    # Корзина и заказы
    path('cart/', views.cart, name='cart'),
    path('cart/add/<int:product_id>/', views.add_to_cart, name='add_to_cart'),
    path('cart/remove/<int:cart_id>/', views.remove_from_cart, name='remove_from_cart'),
    path('cart/update/<int:cart_id>/', views.update_cart, name='update_cart'),
    path('checkout/', views.checkout, name='checkout'),
    path('order/success/<int:order_id>/', views.order_success, name='order_success'),
    path('orders/', views.order_history, name='order_history'),
    
    # Информационные страницы
    path('delivery/', views.delivery, name='delivery'),
    path('care/', views.care, name='care'),
    path('contacts/', views.contacts, name='contacts'),
    path('flower/<str:flower_name>/', views.flower_info, name='flower_info'),
    
    # Уход и доставка
    path('delivery-info/', views.delivery_info, name='delivery_info'),
    path('care-guide/', views.care_guide, name='care_guide'),
]

handler404 = 'main.views.page_not_found'
handler500 = 'main.views.server_error'
handler400 = 'main.views.bad_request'
handler403 = 'main.views.permission_denied'