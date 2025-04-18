import logging


def init_logger(name):
    logger = logging.getLogger(name)
    log_path = f"logs/{name}.log"
    FORMAT = "%(asctime)s :: %(name)s:%(lineno)s :: %(levelname)s :: %(message)s"
    sh = logging.StreamHandler()
    sh.setFormatter(logging.Formatter(FORMAT))
    fh = logging.FileHandler(filename=log_path)
    fh.setFormatter(logging.Formatter(FORMAT))
    logger.setLevel(logging.DEBUG)
    sh.setLevel(logging.DEBUG)
    fh.setLevel(logging.DEBUG)
    logger.addHandler(sh)
    logger.addHandler(fh)
    logger.debug("Логирование запущено.")
    return logger
