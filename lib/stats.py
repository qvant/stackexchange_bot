import os
import psutil
import datetime
from typing import Dict

global startup


def get_memory_usage() -> float:
    process = psutil.Process(os.getpid())
    return round(process.memory_full_info().rss / 1024 ** 2, 2)


def get_memory_percent() -> float:
    process = psutil.Process(os.getpid())
    return round(process.memory_percent("rss"), 2)


def get_cpu_times() -> str:
    process = psutil.Process(os.getpid())
    return str(process.cpu_times())


def get_cpu_percent() -> str:
    process = psutil.Process(os.getpid())
    return str(process.cpu_percent())


def set_startup():
    global startup
    startup = datetime.datetime.now().replace(microsecond=0)


def uptime() -> datetime.timedelta:
    global startup
    return datetime.datetime.now().replace(microsecond=0) - startup


def get_stats() -> Dict:
    stats = {"memory_usage": get_memory_usage(), "memory_parcent": get_cpu_percent(), "cpu_times": get_cpu_times(),
             "cpu_percent": get_cpu_percent(), "uptime": uptime()}
    return stats
