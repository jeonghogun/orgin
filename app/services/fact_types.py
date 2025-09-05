from enum import Enum

class FactType(str, Enum):
    USER_NAME = "user_name"
    JOB = "job"
    HOBBY = "hobby"
    MBTI = "mbti"
    GOAL = "goal"

class FactSensitivity(str, Enum):
    PUBLIC = "public"
    PRIVATE = "private"
    LOW = "low"
    HIGH = "high"
