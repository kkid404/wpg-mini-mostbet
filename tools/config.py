import configparser


def config_read(path):
    config = configparser.ConfigParser()
    config.read(path, encoding="utf-8")
    return config


def config_write(config, path):
    with open(path, "w") as file:
        config.write(file)