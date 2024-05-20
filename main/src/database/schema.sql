-- articles table
CREATE TABLE
    articles (
        article_id INTEGER PRIMARY KEY,
        title TEXT NOT NULL,
        url TEXT NOT NULL UNIQUE,
        content TEXT,
        author TEXT,
        date_published TEXT,
        lead_image_url TEXT,
        excerpt TEXT,
        word_count INTEGER,
        direction TEXT,
        total_pages INTEGER,
        rendered_pages INTEGER,
        date_added TEXT,
        date_retrieved TEXT
    );

-- tags table
CREATE TABLE
    tags (
        tag_id INTEGER PRIMARY KEY,
        tag_name TEXT NOT NULL UNIQUE
    );

-- article_tags mapping table
CREATE TABLE
    article_tags (
        article_id INTEGER,
        tag_id INTEGER,
        FOREIGN KEY (article_id) REFERENCES articles (article_id),
        FOREIGN KEY (tag_id) REFERENCES tags (tag_id),
        PRIMARY KEY (article_id, tag_id)
    );

-- summaries table
CREATE TABLE
    summaries (
        summary_id INTEGER PRIMARY KEY,
        article_id INTEGER,
        summary_text TEXT,
        summary_length INTEGER,
        FOREIGN KEY (article_id) REFERENCES articles (article_id)
    );

-- collections table
CREATE TABLE
    collections (
        collection_id INTEGER PRIMARY KEY,
        collection_name TEXT NOT NULL,
        description TEXT
    );

-- collection_articles mapping table
CREATE TABLE
    collection_articles (
        collection_id INTEGER,
        article_id INTEGER,
        FOREIGN KEY (collection_id) REFERENCES collections (collection_id),
        FOREIGN KEY (article_id) REFERENCES articles (article_id),
        PRIMARY KEY (collection_id, article_id)
    );
