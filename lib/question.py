from typing import Union, List


class Question:
    def __init__(self, title: str, link: str, question_id: int, creation_date: int, tags: List):
        self.title = title
        self.link = link
        self.question_id = question_id
        self.creation_date = creation_date
        self.tags = tags

    def __str__(self):
        return "title: {}, link: {}, question_id: {}, tags: {}".format(self.title, self.link, self.question_id, self.tags)
