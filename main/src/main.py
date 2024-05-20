from database.db_manager import create_tables, connect_db
from services.pocket_service import retrieve_pocket_articles
from utils.data_processor import process_article
from datetime import datetime


def main():
    create_tables()

    articles = retrieve_pocket_articles()
    conn = connect_db()
    cursor = conn.cursor()

    for article in articles:
        processed_article = process_article(article)

        cursor.execute('''
            INSERT OR IGNORE INTO articles (
                title, url, content, author, date_published, lead_image_url, excerpt,
                word_count, direction, total_pages, rendered_pages, date_added, date_retrieved
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            processed_article['title'],
            processed_article['url'],
            processed_article['content'],
            processed_article['author'],
            processed_article['date_published'],
            processed_article['lead_image_url'],
            processed_article['excerpt'],
            processed_article['word_count'],
            processed_article['direction'],
            processed_article['total_pages'],
            processed_article['rendered_pages'],
            datetime.fromtimestamp(int(article['time_added'])).isoformat(),
            datetime.now().isoformat()
        ))

        article_id = cursor.lastrowid

        cursor.execute('''
            INSERT INTO summaries (article_id, summary_text, summary_length)
            VALUES (?, ?, ?)
        ''', (article_id, processed_article['summary'], len(processed_article['summary'].split())))

        for tag in processed_article['tags']:
            cursor.execute('''
                INSERT OR IGNORE INTO tags (tag_name)
                VALUES (?)
            ''', (tag.strip(),))

            cursor.execute('''
                INSERT INTO article_tags (article_id, tag_id)
                SELECT ?, tag_id FROM tags WHERE tag_name = ?
            ''', (article_id, tag.strip()))

    conn.commit()
    conn.close()


if __name__ == '__main__':
    main()
