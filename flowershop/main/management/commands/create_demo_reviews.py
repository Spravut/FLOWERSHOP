from django.core.management.base import BaseCommand
from main.models import Review


class Command(BaseCommand):
    help = 'Creates demo reviews'

    def handle(self, *args, **options):
        reviews_data = [
            {
                'name': 'Мария',
                'text': 'Заказывала букет на годовщину свадьбы. Цветы были свежие, доставка вовремя. Муж был в восторге! Обязательно буду заказывать еще.',
                'rating': 5,
                'is_approved': True
            },
            {
                'name': 'Александр',
                'text': 'Подарил девушке букет Лунная ночь. Она сказала, что это самый красивый букет, который она когда-либо получала. Спасибо за эмоции!',
                'rating': 5,
                'is_approved': True
            },
            {
                'name': 'Екатерина',
                'text': 'Очень понравился сервис. Помогли подобрать букет для мамы на день рождения. Цветы стояли больше недели!',
                'rating': 4,
                'is_approved': True
            },
            {
                'name': 'Дмитрий',
                'text': 'Заказал авторский букет для жены. Флорист учла все пожелания! Букет превзошел все ожидания. Отличная работа!',
                'rating': 5,
                'is_approved': True
            },
            {
                'name': 'Ольга',
                'text': 'Заказываю цветы в Fleur de Reve уже третий раз. Каждый раз букеты шикарные и свежие. Очень нравится индивидуальный подход!',
                'rating': 5,
                'is_approved': True
            },
            {
                'name': 'Игорь',
                'text': 'Порадовала быстрая доставка и аккуратная упаковка. Цветы приехали в идеальном состоянии. Рекомендую всем!',
                'rating': 5,
                'is_approved': True
            },
        ]

        created_count = 0
        for data in reviews_data:
            review, created = Review.objects.get_or_create(
                name=data['name'],
                defaults=data
            )
            if created:
                created_count += 1

        self.stdout.write(
            self.style.SUCCESS(f'Created {created_count} reviews. Total: {Review.objects.count()}')
        )

