import os
import time
import logging
from typing import Set, List, Dict
import requests
from bs4 import BeautifulSoup
from dotenv import load_dotenv

# Настройка логгера
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("news_bot.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# Загрузка переменных окружения
load_dotenv()

# Конфигурация
CONFIG = {
    "RBC_URL": "https://www.rbc.ru/",
    "TELEGRAM_TOKEN": os.getenv("TELEGRAM_TOKEN"),
    "CHANNEL_ID": os.getenv("CHANNEL_ID"),
    "SENT_ARTICLES_FILE": "sent_articles.txt",
    "CHECK_INTERVAL": int(os.getenv("CHECK_INTERVAL", 900)),
    "USER_AGENT": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
    "REQUEST_TIMEOUT": 10,
    "MAX_MESSAGE_LENGTH": 4096
}


class NewsBot:
    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": CONFIG["USER_AGENT"]})

    def load_sent_articles(self) -> Set[str]:
        try:
            with open(CONFIG["SENT_ARTICLES_FILE"], "r", encoding="utf-8") as f:
                return {line.strip() for line in f.readlines()}
        except FileNotFoundError:
            return set()

    def save_sent_article(self, link: str) -> None:
        with open(CONFIG["SENT_ARTICLES_FILE"], "a", encoding="utf-8") as f:
            f.write(link + "\n")

    def fetch_articles(self) -> List[Dict[str, str]]:
        try:
            response = self.session.get(
                CONFIG["RBC_URL"],
                timeout=CONFIG["REQUEST_TIMEOUT"]
            )
            response.raise_for_status()

            soup = BeautifulSoup(response.text, 'html.parser')
            articles = []

            for item in soup.find_all('a', class_='main__feed__link'):
                title = item.text.strip()
                link = item['href']
                if not link.startswith('http'):
                    link = CONFIG["RBC_URL"] + link.lstrip('/')
                articles.append({'title': title, 'link': link})

            return articles

        except Exception as e:
            logger.error(f"Ошибка получения статей: {e}")
            return []

    def parse_article_content(self, url: str) -> str:
        try:
            response = self.session.get(
                url,
                timeout=CONFIG["REQUEST_TIMEOUT"]
            )
            soup = BeautifulSoup(response.text, 'html.parser')

            # Поиск основного контента
            content = soup.find('div', class_='article__text') or soup.find('article')
            if not content:
                return "Текст статьи не найден"

            # Удаление ненужных элементов
            for element in content.find_all(['script', 'style', 'aside', 'div.article__incut']):
                element.decompose()

            return '\n\n'.join(
                p.get_text(strip=True) 
                for p in content.find_all(['p', 'h2', 'h3']) 
                if p.get_text(strip=True)
            )

        except Exception as e:
            logger.error(f"Ошибка парсинга статьи: {e}")
            return ""

    def send_telegram_message(self, text: str) -> bool:
        try:
            url = f"https://api.telegram.org/bot{CONFIG['TELEGRAM_TOKEN']}/sendMessage"
            payload = {
                "chat_id": CONFIG["CHANNEL_ID"],
                "text": text,
                "parse_mode": "HTML",
                "disable_web_page_preview": True
            }
            response = self.session.post(url, data=payload, timeout=CONFIG["REQUEST_TIMEOUT"])
            return response.status_code == 200
        except Exception as e:
            logger.error(f"Ошибка отправки в Telegram: {e}")
            return False

    def format_message(self, title: str, content: str, link: str) -> List[str]:
        message_template = (
            f"<b>📰 {title}</b>\n\n"
            "{content}"
            f"\n\n<a href='{link}'>🔗 Источник</a>"
        )
        
        max_content_length = CONFIG["MAX_MESSAGE_LENGTH"] - len(message_template) + len("{content}")
        parts = [content[i:i+max_content_length] for i in range(0, len(content), max_content_length)]
        
        return [message_template.format(content=part) for part in parts]

    def run(self):
        logger.info("🚀 Бот запущен")
        try:
            while True:
                sent_articles = self.load_sent_articles()
                new_articles = [
                    article 
                    for article in self.fetch_articles()
                    if article['link'] not in sent_articles
                ]

                for article in new_articles:
                    content = self.parse_article_content(article['link'])
                    if not content:
                        continue

                    for message in self.format_message(article['title'], content, article['link']):
                        if self.send_telegram_message(message):
                            logger.info(f"Отправлена статья: {article['title'][:50]}...")
                            time.sleep(1)
                    
                    self.save_sent_article(article['link'])
                    time.sleep(2)

                logger.info(f"Следующая проверка через {CONFIG['CHECK_INTERVAL'] // 60} минут...")
                time.sleep(CONFIG["CHECK_INTERVAL"])

        except KeyboardInterrupt:
            logger.info("\n🛑 Скрипт остановлен")
        except Exception as e:
            logger.error(f"Критическая ошибка: {e}")


if __name__ == "__main__":
    bot = NewsBot()
    bot.run()
