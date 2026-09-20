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

  # Dipakai Flask untuk menandatangani session cookie flash message.
  # Diambil dari environment variable jika tersedia, jika tidak dibangkitkan
  # acak setiap kali proses dijalankan.
  app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY") or secrets.token_hex(32)

  os.makedirs(app.instance_path, exist_ok=True)

  from app.routes import main_bp
  app.register_blueprint(main_bp)

  # Menyediakan variabel developer_mode ke seluruh template, mengikuti
  # status debug Flask (app.debug). Dipakai untuk menampilkan/menyembunyikan
  # panel "Info Developer" di halaman hasil.
  @app.context_processor
  def inject_developer_mode():
    return {"developer_mode": app.debug}

  return app
