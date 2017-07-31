TOKEN = '339108677:AAFwvvFhrbp-0__Zizc1Gi8Ongbh4v9SCFs'
DB_CONNECTION = 'postgresql://telebot:qwerty@localhost/telebot'

WEBHOOK_HOST = 'mysterious-hollows-20085.herokuapp.com'
WEBHOOK_PORT = 8443
WEBHOOK_LISTEN = '0.0.0.0'

WEBHOOK_SSL_CERT = 'webhook_cert.pem'
WEBHOOK_SSL_PRIV = 'webhook_private.key'

WEBHOOK_URL_BASE = "https://%s:%s" % (WEBHOOK_HOST, WEBHOOK_PORT)
WEBHOOK_URL_PATH = "/%s/" % TOKEN
