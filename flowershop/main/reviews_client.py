import logging
from datetime import datetime
from typing import Optional, Tuple

import requests
from django.conf import settings

logger = logging.getLogger(__name__)

BASE_URL = getattr(settings, 'REVIEWS_SERVICE_URL', 'http://localhost:8000')
TIMEOUT = 10


class ReviewDisplay:
    def __init__(self, data: dict):
        self.id = data.get('id')
        self.name = data.get('name', '')
        self.text = data.get('text', '')
        self.rating = int(data.get('rating', 5))
        self.is_approved = data.get('is_approved', False)
        created = data.get('created_at')
        if isinstance(created, str):
            try:
                self.created_at = datetime.fromisoformat(created.replace('Z', '+00:00'))
            except ValueError:
                self.created_at = datetime.now()
        else:
            self.created_at = created or datetime.now()

    def get_stars(self) -> str:
        return '★' * self.rating + '☆' * (5 - self.rating)


def fetch_reviews(approved_only: bool = True, limit: int = 50, offset: int = 0) -> tuple[list, int]:
    try:
        resp = requests.get(
            f'{BASE_URL}/reviews',
            params={'approved_only': approved_only, 'limit': limit, 'offset': offset},
            timeout=TIMEOUT,
        )
        resp.raise_for_status()
        data = resp.json()
        items = [ReviewDisplay(r) for r in data.get('items', [])]
        total = data.get('total', len(items))
        return items, total
    except requests.RequestException as e:
        logger.warning('Reviews service unavailable: %s', e)
        return [], 0


def fetch_rating_summary(approved_only: bool = True, product_id: Optional[int] = None) -> tuple[Optional[float], int]:
    try:
        params = {'approved_only': approved_only}
        if product_id is not None:
            params['product_id'] = product_id
        resp = requests.get(f'{BASE_URL}/ratings/summary', params=params, timeout=TIMEOUT)
        resp.raise_for_status()
        data = resp.json()
        return data.get('average'), data.get('count', 0)
    except requests.RequestException as e:
        logger.warning('Reviews service rating summary unavailable: %s', e)
        return None, 0


def create_review(
    name: str,
    text: str,
    rating: int = 5,
    product_id: Optional[int] = None,
    user_id: Optional[int] = None,
) -> Tuple[Optional[dict], Optional[str]]:
    payload = {'name': name, 'text': text, 'rating': rating}
    if product_id is not None:
        payload['product_id'] = product_id
    if user_id is not None:
        payload['user_id'] = user_id
    try:
        resp = requests.post(f'{BASE_URL}/reviews', json=payload, timeout=TIMEOUT)
        if resp.status_code == 201:
            return resp.json(), None
        if resp.status_code == 422:
            try:
                data = resp.json()
                detail = data.get('detail')
                if isinstance(detail, list) and detail:
                    first = detail[0]
                    msg = first.get('msg', str(first)) if isinstance(first, dict) else str(first)
                else:
                    msg = str(detail) if detail else 'Отзыв не прошёл автоматическую проверку.'
            except Exception:
                msg = 'Отзыв не прошёл автоматическую проверку.'
            return None, msg
        resp.raise_for_status()
        return resp.json(), None
    except requests.RequestException as e:
        logger.warning('Reviews service create failed: %s', e)
        return None, 'Сервис отзывов временно недоступен. Попробуйте позже.'
