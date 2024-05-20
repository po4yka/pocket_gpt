import pocket
from config.config import POCKET_CONSUMER_KEY, POCKET_ACCESS_TOKEN


def get_pocket_instance():
    return pocket.Pocket(POCKET_CONSUMER_KEY, POCKET_ACCESS_TOKEN)


def retrieve_pocket_articles():
    pocket_instance = get_pocket_instance()
    articles = pocket_instance.get(state='all', detailType='complete')
    return articles['list'].values()
