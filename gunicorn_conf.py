"""Gunicorn 配置

所有配置项都可用环境变量覆盖，默认值与项目无关，便于在不同环境部署：

    pip install -r requirements.txt
    gunicorn -c gunicorn_conf.py app:app

常用环境变量：
    GUNICORN_BIND          监听地址，默认 0.0.0.0:8000
    GUNICORN_WORKERS       进程数，默认 4
    GUNICORN_THREADS       每进程线程数，默认 2
    GUNICORN_LOG_LEVEL     日志级别，默认 info
    GUNICORN_ACCESS_LOG    访问日志路径，默认 '-'（标准输出）
    GUNICORN_ERROR_LOG     错误日志路径，默认 '-'（标准错误）
    GUNICORN_PIDFILE       进程文件路径，默认 <项目目录>/gunicorn.pid

需要以低权限用户运行时，请在命令行追加 --user/--group（而不是写死在配置里，
否则非 root 用户加载配置会直接失败）：
    gunicorn -c gunicorn_conf.py --user www --group www app:app
"""
import os

BASE_DIR = os.path.dirname(os.path.abspath(__file__))


def _env_int(name, default):
    try:
        return int(os.environ.get(name, default))
    except (TypeError, ValueError):
        return default


# 监听地址与端口
bind = os.environ.get('GUNICORN_BIND', '0.0.0.0:8000')

# 进程数与线程数
workers = _env_int('GUNICORN_WORKERS', 4)
threads = _env_int('GUNICORN_THREADS', 2)

# 启动模式
worker_class = os.environ.get('GUNICORN_WORKER_CLASS', 'sync')

# 超时时间（秒）
timeout = _env_int('GUNICORN_TIMEOUT', 30)

# 进程文件（用于停止/重启服务）
pidfile = os.environ.get('GUNICORN_PIDFILE', os.path.join(BASE_DIR, 'gunicorn.pid'))

# 访问日志与错误日志，默认输出到标准输出/错误
accesslog = os.environ.get('GUNICORN_ACCESS_LOG', '-')
errorlog = os.environ.get('GUNICORN_ERROR_LOG', '-')

# 日志级别
loglevel = os.environ.get('GUNICORN_LOG_LEVEL', 'info')

# 请求行长度上限
limit_request_line = 4094
