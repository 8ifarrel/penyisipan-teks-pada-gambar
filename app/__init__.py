# Flask application factory.
#
# Menyatukan seluruh modul (crypto, stego, metrics, routes) menjadi satu
# aplikasi Flask.

import os
import secrets

from flask import Flask


def create_app():
  app = Flask(__name__)

  # TODO: pindahkan ke config terpisah jika diperlukan (mis. app/config.py)
  app.config["MAX_CONTENT_LENGTH"] = 16 * 1024 * 1024  # batas ukuran unggahan

  # SECRET_KEY diperlukan Flask untuk menandatangani session cookie yang
  # dipakai mekanisme flash message. Diambil dari environment variable
  # jika tersedia (untuk deployment sungguhan); jika tidak, dibangkitkan
  # acak setiap kali proses dijalankan. Ini cukup untuk pengembangan lokal,
  # karena aplikasi ini tidak menyimpan data sensitif apa pun di session
  # (key AES TIDAK pernah disimpan di server, hanya ditampilkan sekali
  # pada halaman hasil).
  app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY") or secrets.token_hex(32)

  os.makedirs(app.instance_path, exist_ok=True)

  from app.routes import main_bp
  app.register_blueprint(main_bp)

  return app
