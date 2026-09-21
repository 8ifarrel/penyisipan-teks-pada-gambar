# Routes/Blueprint Flask.
#
# Berisi tabel routing saja (endpoint -> handler). Logic tiap fitur ada di
# app/services/ (satu file per fitur: embed_service.py, extract_service.py),
# dan logic kripto/steganografi murni ada di app/crypto & app/stego.
#
# Kunci AES-128 ditampilkan ke pengguna dalam bentuk hex (32 karakter),
# tidak pernah disimpan ke file/session di server; hanya disisipkan ke HTML
# halaman hasil sekali saat response dikirim.

from flask import Blueprint, render_template, request, send_file

from app.services import embed_service, extract_service
from app.utils.temp_files import cleanup_old_temp_files, resolve_temp_file_path

main_bp = Blueprint("main", __name__)


@main_bp.route("/")
def index():
  return render_template("index.html")


@main_bp.route("/sisipkan", methods=["GET", "POST"])
def sisipkan():
  if request.method == "GET":
    return embed_service.show_form()
  return embed_service.handle_submit()


@main_bp.route("/pratinjau/<file_id>")
def pratinjau_stego(file_id):
  """Menyajikan citra stego untuk ditampilkan (bukan diunduh) di halaman hasil."""
  cleanup_old_temp_files()
  file_path = resolve_temp_file_path(file_id)
  return send_file(file_path, mimetype="image/png")


@main_bp.route("/unduh/<file_id>")
def unduh_stego(file_id):
  """Menyajikan citra stego sebagai unduhan (Content-Disposition: attachment)."""
  cleanup_old_temp_files()
  file_path = resolve_temp_file_path(file_id)
  return send_file(
    file_path,
    mimetype="image/png",
    as_attachment=True,
    download_name="citra_stego.png",
  )


@main_bp.route("/ekstraksi", methods=["GET", "POST"])
def ekstraksi():
  if request.method == "GET":
    return extract_service.show_form()
  return extract_service.handle_submit()
