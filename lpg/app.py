from flask import Flask, request, jsonify, session, redirect, url_for, send_from_directory
from werkzeug.security import generate_password_hash, check_password_hash
from functools import wraps
import json
import os
import threading
import time
import requests
from datetime import datetime

# ============ KONFIGURASI ============
app = Flask(__name__)
app.secret_key = 'LPG-SECRET-KEY-GANTI-DENGAN-RANDOM-STRING-PANJANG'

TELEGRAM_TOKEN = '8750135615:AAFZF-xcNW_wB49CxO_Lc_vvwSAb76sepAY'
TELEGRAM_CHAT_ID = '7051115490'
BACKUP_INTERVAL = 300        # 5 menit
EDIT_LOCK_SECONDS = 3600     # 1 jam

DATA_DIR = 'data'
USERS_FILE = os.path.join(DATA_DIR, 'users.json')
TRANSAKSI_FILE = os.path.join(DATA_DIR, 'transaksi.json')
HARGA_FILE = os.path.join(DATA_DIR, 'harga.json')

# ============ INIT ============
os.makedirs(DATA_DIR, exist_ok=True)

def init_files():
    if not os.path.exists(USERS_FILE):
        save_json(USERS_FILE, {'pegawai': []})
    if not os.path.exists(TRANSAKSI_FILE):
        save_json(TRANSAKSI_FILE, [])
    if not os.path.exists(HARGA_FILE):
        save_json(HARGA_FILE, {'Pembelian': 0, 'Penjualan': 0})

def load_json(path):
    try:
        with open(path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        if 'transaksi' in path:
            return []
        elif 'harga' in path:
            return {'Pembelian': 0, 'Penjualan': 0}
        return {'pegawai': []}

def save_json(path, data):
    temp_path = path + '.tmp'
    with open(temp_path, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    os.replace(temp_path, path)

init_files()

# ============ HELPERS ============
def admin_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if session.get('role') != 'admin':
            return jsonify({'error': 'Akses ditolak. Hanya admin.'}), 403
        return f(*args, **kwargs)
    return decorated

def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if 'username' not in session:
            return jsonify({'error': 'Silakan login terlebih dahulu'}), 401
        return f(*args, **kwargs)
    return decorated

def update_harga_memory(jenis, harga):
    """Simpan harga terakhir untuk auto-fill"""
    harga_data = load_json(HARGA_FILE)
    if harga > 0:
        harga_data[jenis] = harga
        save_json(HARGA_FILE, harga_data)

# ============ TELEGRAM BACKUP ============
def send_telegram_backup():
    try:
        if not os.path.exists(TRANSAKSI_FILE):
            return False, "File transaksi tidak ditemukan"

        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendDocument"
        caption = (
            f"📊 *Backup Otomatis LPG*\n"
            f"🕐 Waktu: {datetime.now().strftime('%d/%m/%Y %H:%M:%S')}\n"
            f"📁 File: transaksi.json"
        )

        with open(TRANSAKSI_FILE, 'rb') as f:
            files = {'document': ('transaksi.json', f, 'application/json')}
            data = {'chat_id': TELEGRAM_CHAT_ID, 'caption': caption, 'parse_mode': 'Markdown'}
            response = requests.post(url, files=files, data=data, timeout=30)

        if response.status_code == 200:
            result = response.json()
            if result.get('ok'):
                return True, "Backup berhasil"
            else:
                return False, f"Telegram error: {result.get('description')}"
        else:
            return False, f"HTTP {response.status_code}"
    except Exception as e:
        return False, f"Error: {str(e)}"

def backup_loop():
    print(f"✅ Auto backup Telegram aktif (setiap {BACKUP_INTERVAL} detik)")
    while True:
        time.sleep(BACKUP_INTERVAL)
        try:
            success, msg = send_telegram_backup()
            timestamp = datetime.now().strftime('%H:%M:%S')
            status = "✅" if success else f"❌ {msg}"
            print(f"[{timestamp}] {status}")
        except Exception as e:
            print(f"[Backup Error] {e}")

# ============ ROUTES ============
@app.route('/')
def index():
    if 'username' not in session:
        return redirect(url_for('login_page'))
    return redirect(url_for('dashboard'))

@app.route('/login')
def login_page():
    return send_from_directory('.', 'login.html')

@app.route('/dashboard')
def dashboard():
    if 'username' not in session:
        return redirect(url_for('login_page'))
    return send_from_directory('.', 'lpg.html')

# ============ AUTH ============
@app.route('/api/login', methods=['POST'])
def login():
    data = request.json or {}
    username = data.get('username', '').strip()
    password = data.get('password', '')

    if not username:
        return jsonify({'success': False, 'error': 'Username wajib diisi'}), 400

    if username == '@adminsandi':
        session['username'] = username
        session['role'] = 'admin'
        session['nama'] = 'Administrator'
        return jsonify({'success': True, 'role': 'admin', 'nama': 'Administrator'})

    users = load_json(USERS_FILE)
    for u in users['pegawai']:
        if u['username'] == username and check_password_hash(u['password'], password):
            session['username'] = u['username']
            session['role'] = 'pegawai'
            session['nama'] = u.get('nama', u['username'])
            return jsonify({'success': True, 'role': 'pegawai', 'nama': u.get('nama')})

    return jsonify({'success': False, 'error': 'Username atau password salah'}), 401

@app.route('/api/logout', methods=['POST'])
def logout():
    session.clear()
    return jsonify({'success': True})

@app.route('/api/me')
def me():
    if 'username' not in session:
        return jsonify({'error': 'Not logged in'}), 401
    return jsonify({
        'username': session['username'],
        'role': session['role'],
        'nama': session.get('nama', session['username'])
    })

# ============ USER MANAGEMENT ============
@app.route('/api/users', methods=['GET'])
@admin_required
def get_users():
    users = load_json(USERS_FILE)
    safe_list = [{'username': u['username'], 'nama': u.get('nama', '')} for u in users['pegawai']]
    return jsonify({'pegawai': safe_list})

@app.route('/api/users', methods=['POST'])
@admin_required
def create_user():
    data = request.json or {}
    username = data.get('username', '').strip().lower()
    password = data.get('password', '')
    nama = data.get('nama', '').strip()

    if not username or not password:
        return jsonify({'error': 'Username dan password wajib diisi'}), 400
    if username == '@adminsandi':
        return jsonify({'error': 'Username tidak valid'}), 400
    if len(password) < 4:
        return jsonify({'error': 'Password minimal 4 karakter'}), 400

    users = load_json(USERS_FILE)
    for u in users['pegawai']:
        if u['username'] == username:
            return jsonify({'error': 'Username sudah terdaftar'}), 400

    users['pegawai'].append({
        'username': username,
        'password': generate_password_hash(password),
        'nama': nama or username
    })
    save_json(USERS_FILE, users)
    return jsonify({'success': True})

@app.route('/api/users/<username>', methods=['DELETE'])
@admin_required
def delete_user(username):
    users = load_json(USERS_FILE)
    users['pegawai'] = [u for u in users['pegawai'] if u['username'] != username]
    save_json(USERS_FILE, users)
    return jsonify({'success': True})

# ============ PRICE MEMORY API ============
@app.route('/api/harga', methods=['GET'])
@login_required
def get_harga():
    return jsonify(load_json(HARGA_FILE))

# ============ TRANSAKSI LPG ============
@app.route('/api/transaksi', methods=['GET'])
@login_required
def get_transaksi():
    return jsonify(load_json(TRANSAKSI_FILE))

@app.route('/api/transaksi', methods=['POST'])
@login_required
def add_transaksi():
    data = request.json or {}
    try:
        jumlah = int(data.get('jumlahTabung', 0))
        harga = int(data.get('hargaPerPcs', 0))
        tanggal = data.get('tanggal', '')
        jenis = data.get('jenis', '')

        if jumlah <= 0 or harga <= 0:
            return jsonify({'error': 'Jumlah dan harga harus lebih dari 0'}), 400

        if not tanggal or jenis not in ['Pembelian', 'Penjualan']:
            return jsonify({'error': 'Data tidak valid'}), 400

        transaksi_baru = {
            'id': int(datetime.now().timestamp() * 1000),
            'tanggal': tanggal,
            'jenis': jenis,
            'jumlahTabung': jumlah,
            'hargaPerPcs': harga,
            'totalNilai': jumlah * harga,
            'createdBy': session['username'],
            'createdAt': datetime.now().isoformat()
        }

        data_list = load_json(TRANSAKSI_FILE)
        data_list.append(transaksi_baru)
        save_json(TRANSAKSI_FILE, data_list)

        # Auto-save harga untuk price memory
        update_harga_memory(jenis, harga)

        return jsonify({'success': True, 'data': transaksi_baru})

    except (ValueError, TypeError) as e:
        return jsonify({'error': f'Data tidak valid: {str(e)}'}), 400

# ============ EDIT TRANSAKSI (dengan Time-Lock) ============
@app.route('/api/transaksi/<int:id>', methods=['PUT'])
@login_required
def edit_transaksi(id):
    data_list = load_json(TRANSAKSI_FILE)
    target = next((t for t in data_list if t['id'] == id), None)

    if not target:
        return jsonify({'error': 'Transaksi tidak ditemukan'}), 404

    # === VALIDASI PERMISSION ===
    if session['role'] == 'pegawai':
        # Pegawai hanya bisa edit miliknya sendiri
        if target.get('createdBy') != session['username']:
            return jsonify({'error': 'Anda hanya bisa mengedit transaksi Anda sendiri'}), 403

        # Check time-lock 1 jam
        try:
            created_at = datetime.fromisoformat(target['createdAt'])
            elapsed = (datetime.now() - created_at).total_seconds()
            if elapsed > EDIT_LOCK_SECONDS:
                return jsonify({'error': 'Transaksi sudah di-lock (lebih dari 1 jam). Hubungi admin untuk perubahan.'}), 403
        except (ValueError, KeyError):
            return jsonify({'error': 'Data transaksi tidak valid'}), 400

    # Admin bisa edit semua tanpa batas waktu

    # === UPDATE DATA ===
    data = request.json or {}
    try:
        tanggal = data.get('tanggal', target['tanggal'])
        jenis = data.get('jenis', target['jenis'])
        jumlah = int(data.get('jumlahTabung', target['jumlahTabung']))
        harga = int(data.get('hargaPerPcs', target['hargaPerPcs']))

        if jenis not in ['Pembelian', 'Penjualan']:
            return jsonify({'error': 'Jenis transaksi tidak valid'}), 400

        if jumlah <= 0 or harga <= 0:
            return jsonify({'error': 'Jumlah dan harga harus lebih dari 0'}), 400

        # Update target
        target['tanggal'] = tanggal
        target['jenis'] = jenis
        target['jumlahTabung'] = jumlah
        target['hargaPerPcs'] = harga
        target['totalNilai'] = jumlah * harga
        target['editedBy'] = session['username']
        target['editedAt'] = datetime.now().isoformat()

        save_json(TRANSAKSI_FILE, data_list)

        # Update price memory
        update_harga_memory(jenis, harga)

        return jsonify({'success': True, 'data': target})

    except (ValueError, TypeError) as e:
        return jsonify({'error': f'Data tidak valid: {str(e)}'}), 400

# ============ HAPUS / RESET ============
@app.route('/api/transaksi/<int:id>', methods=['DELETE'])
@admin_required
def delete_transaksi(id):
    data_list = load_json(TRANSAKSI_FILE)
    original_len = len(data_list)
    data_list = [t for t in data_list if t['id'] != id]
    if len(data_list) == original_len:
        return jsonify({'error': 'Transaksi tidak ditemukan'}), 404
    save_json(TRANSAKSI_FILE, data_list)
    return jsonify({'success': True})

@app.route('/api/transaksi', methods=['DELETE'])
@admin_required
def reset_transaksi():
    save_json(TRANSAKSI_FILE, [])
    return jsonify({'success': True})

# ============ BACKUP MANUAL ============
@app.route('/api/backup-now', methods=['POST'])
@admin_required
def backup_now():
    success, msg = send_telegram_backup()
    if success:
        return jsonify({'success': True, 'message': 'Backup berhasil'})
    return jsonify({'success': False, 'error': msg}), 500

# ============ START ============
if __name__ == '__main__':
    backup_thread = threading.Thread(target=backup_loop, daemon=True)
    backup_thread.start()

    print("=" * 60)
    print("📊 Server LPG berjalan di:")
    print("   ➜ http://localhost:5000")
    print("=" * 60)
    print("👑 Admin login : @adminsandi (tanpa password)")
    print(f"⏰ Edit lock   : {EDIT_LOCK_SECONDS} detik (1 jam)")
    print(f"📱 Auto backup : setiap {BACKUP_INTERVAL} detik")
    print("=" * 60)

    app.run(host='0.0.0.0', port=5000, debug=False, threaded=True)
