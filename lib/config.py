import codecs
import datetime
import json

from .security import is_password_encrypted, encrypt_password, decrypt_password
from .log import get_logger
from .stats import set_startup

LOG_CONFIG = "config"
CONFIG_PARAM_LOG_LEVEL = "LOG_LEVEL"
CONFIG_PARAM_DB_PORT = "DB_PORT"
CONFIG_PARAM_DB_NAME = "DB_NAME"
CONFIG_PARAM_DB_HOST = "DB_HOST"
CONFIG_PARAM_DB_USER = "DB_USER"
CONFIG_PARAM_DB_PASSWORD = "DB_PASSWORD"
CONFIG_PARAM_NEW_PATH = "CONFIG_PATH"
CONFIG_PARAM_CONFIG_RELOAD_TIME = "CONFIG_RELOAD_TIME"
CONFIG_PARAM_SERVER_NAME = "SERVER_NAME"
CONFIG_PARAM_UPDATE_INTERVAL = "UPDATE_INTERVAL"
CONFIG_PARAM_HALT_ON_ERRORS = "HALT_ON_ERRORS"
CONFIG_PARAM_BOT_SECRET = "BOT_SECRET"
CONFIG_PARAM_ADMIN_LIST = "ADMIN_ACCOUNTS"

MODE_CORE = "core"
MODE_BOT = "bot"
MODE_WORKER = "worker"
MODE_UPDATER = "updater"


class Config:
    def __init__(self, file: str, reload: bool = False):
        f = file
        fp = codecs.open(f, 'r', "utf-8")
        config = json.load(fp)
        if not reload:
            self.logger = get_logger(LOG_CONFIG, is_system=True)
            set_startup()
        self.logger.info("Read settings from {0}".format(file))
        self.file_path = file
        self.old_file_path = file
        self.log_level = config.get(CONFIG_PARAM_LOG_LEVEL)
        self.logger.setLevel(self.log_level)
        self.server_name = config.get(CONFIG_PARAM_SERVER_NAME)
        self.supress_errors = False
        self.update_interval = int(config.get(CONFIG_PARAM_UPDATE_INTERVAL))
        if not config.get(CONFIG_PARAM_HALT_ON_ERRORS):
            self.supress_errors = True
        self.secret = config.get(CONFIG_PARAM_BOT_SECRET)
        self.db_name = config.get(CONFIG_PARAM_DB_NAME)
        self.db_port = config.get(CONFIG_PARAM_DB_PORT)
        self.db_host = config.get(CONFIG_PARAM_DB_HOST)
        self.db_user = config.get(CONFIG_PARAM_DB_USER)
        self.db_password_read = config.get(CONFIG_PARAM_DB_PASSWORD)
        if config.get(CONFIG_PARAM_NEW_PATH) is not None:
            self.file_path = config.get(CONFIG_PARAM_NEW_PATH)
        self.reload_time = config.get(CONFIG_PARAM_CONFIG_RELOAD_TIME)
        self.next_reload = datetime.datetime.now()
        self.reloaded = False
        self.db_credential_changed = False

        if is_password_encrypted(self.db_password_read):
            self.logger.info("DB password encrypted, do nothing")
            self.db_password = decrypt_password(self.db_password_read, self.server_name, self.db_port)
        else:
            self.logger.info("DB password in plain text, start encrypt")
            password = encrypt_password(self.db_password_read, self.server_name, self.db_port)
            self._save_db_password(password)
            self.logger.info("DB password encrypted and save back in config")
            self.db_password = self.db_password_read

        if is_password_encrypted(self.secret):
            self.logger.info("Secret in cypher text, start decryption")
            self.secret = decrypt_password(self.secret, self.server_name, self.db_port)
            self.logger.info("Secret was decrypted")
        else:
            self.logger.info("Secret in plain text, start encryption")
            new_password = encrypt_password(self.secret, self.server_name, self.db_port)
            self._save_secret(new_password)
            self.logger.info("Secret was encrypted and saved")

        self.admin_list = config.get(CONFIG_PARAM_ADMIN_LIST)

    def _save_db_password(self, password: str):
        fp = codecs.open(self.file_path, 'r', "utf-8")
        config = json.load(fp)
        fp.close()
        fp = codecs.open(self.file_path, 'w', "utf-8")
        config[CONFIG_PARAM_DB_PASSWORD] = password
        json.dump(config, fp, indent=2)
        fp.close()

    def _save_secret(self, password: str):
        fp = codecs.open(self.file_path, 'r', "utf-8")
        config = json.load(fp)
        fp.close()
        fp = codecs.open(self.file_path, 'w', "utf-8")
        config[CONFIG_PARAM_BOT_SECRET] = password
        json.dump(config, fp, indent=2)
        fp.close()

    def renew_if_needed(self):
        if datetime.datetime.now() >= self.next_reload:
            self.logger.debug("Time to reload settings")
            old_file_path = self.old_file_path
            old_db_password = self.db_password
            try:
                self.__init__(self.file_path, reload=True)
                self.reloaded = True
                if self.db_password != old_db_password:
                    self.logger.info("DB password changed, need to reconnect")
                    self.db_credential_changed = True
            except BaseException as exc:
                self.logger.critical("Can't reload settings from new path {0}, error {1}".format(self.file_path, exc))
                self.old_file_path = old_file_path
                self.file_path = old_file_path
        else:
            self.logger.debug("Too early to reload settings")

    def mark_reload_finish(self):
        self.reloaded = False
        self.db_credential_changed = False
