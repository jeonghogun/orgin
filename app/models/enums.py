from enum import Enum


class RoomType(str, Enum):
    MAIN = "main"
    SUB = "sub"
    REVIEW = "review"
