from flask import Flask, request, jsonify, session, redirect, url_for, send_from_directory
from werkzeug.security import generate_password_hash, check_password_hash
from functools import wraps
import json
import os
import threading
import requests
from datetime import datetime

# ============ KONFIGURASI ============
app = Flask(__name__)
app.secret_key = 'LPG-SECRET-KEY-GANTI-DENGAN-RANDOM-STRING-PANJANG'

TELEGRAM_TOKEN = '8750135615:AAFZF-xcNW_wB49CxO_Lc_vvwSAb76sepAY'
TELEGRAM_CHAT_ID = '7051115490'
EDIT_LOCK_SECONDS = 3600

DATA_DIR = 'data'
USERS_FILE = os.path.join(DATA_DIR, 'users.json')
TRANSAKSI_FILE = os.path.join(DATA_DIR, 'transaksi.json')
HARGA_FILE = os.path.join(DATA_DIR, 'harga.json')

JENIS_TRANSAKSI = ['Pembelian', 'Penjualan']
JENIS_PENGELUARAN = ['Operasional', 'Administrasi', 'Lain-lain']
SEMUA_JENIS = JENIS_TRANSAKSI + JENIS_PENGELUARAN

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
        if 'transaksi' in path: return []
        elif 'harga' in path: return {'Pembelian': 0, 'Penjualan': 0}
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
            return jsonify({'error': 'Akses ditolak.'}), 403
        return f(*args, **kwargs)
    return decorated

def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if 'username' not in session:
            return jsonify({'error': 'Silakan login'}), 401
        return f(*args, **kwargs)
    return decorated

def update_harga_memory(jenis, harga):
    if jenis not in JENIS_TRANSAKSI: return
    harga_data = load_json(HARGA_FILE)
    if harga > 0:
        harga_data[jenis] = harga
        save_json(HARGA_FILE, harga_data)

# ============ EVENT-DRIVEN TELEGRAM BACKUP ============
def send_telegram_backup_sync(action_desc=""):
    """Kirim file transaksi.json ke Telegram (synchronous)"""
    try:
        if not os.path.exists(TRANSAKSI_FILE):
            return False, "File tidak ditemukan"

        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendDocument"

        # Hitung ringkasan data
        data_list = load_json(TRANSAKSI_FILE)
        total_transaksi = len(data_list)

        caption = (
            f"📊 *Backup Data LPG*\n"
            f"🔄 Aksi: {action_desc}\n"
            f"🕐 Waktu: {datetime.now().strftime('%d/%m/%Y %H:%M:%S')}\n"
            f"📋 Total Transaksi: {total_transaksi}\n"
            f"📁 File: transaksi.json"
        )

        with open(TRANSAKSI_FILE, 'rb') as f:
            files = {'document': ('transaksi.json', f, 'application/json')}
            data = {'chat_id': TELEGRAM_CHAT_ID, 'caption': caption, 'parse_mode': 'Markdown'}
            response = requests.post(url, files=files, data=data, timeout=30)

        if response.status_code == 200:
            result = response.json()
            if result.get('ok'):
                return True, "OK"
            return False, result.get('description')
        return False, f"HTTP {response.status_code}"
    except Exception as e:
        return False, str(e)

def trigger_backup(action_desc=""):
    """Trigger backup di background thread (non-blocking)"""
    def _do_backup():
        try:
            success, msg = send_telegram_backup_sync(action_desc)
            ts = datetime.now().strftime('%H:%M:%S')
            if success:
                print(f"[{ts}] ✅ Backup terkirim: {action_desc}")
            else:
                print(f"[{ts}] ❌ Backup gagal: {msg}")
        except Exception as e:
            print(f"[{ts}] ❌ Backup error: {e}")

    thread = threading.Thread(target=_do_backup, daemon=True)
    thread.start()

# ============ ROUTES ============
@app.route('/')
def index():
    if 'username' not in session: return redirect(url_for('login_page'))
    return redirect(url_for('dashboard'))

@app.route('/login')
def login_page():
    return send_from_directory('.', 'login.html')

@app.route('/dashboard')
def dashboard():
    if 'username' not in session: return redirect(url_for('login_page'))
    return send_from_directory('.', 'lpg.html')

# ============ AUTH ============
@app.route('/api/login', methods=['POST'])
def login():
    data = request.json or {}
    username = data.get('username', '').strip()
    password = data.get('password', '')
    if not username:
        return jsonify({'success': False, 'error': 'Username wajib'}), 400
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
    nama = session.get('nama') or session.get('username') or 'User'
    return jsonify({'username': session['username'], 'role': session.get('role', 'pegawai'), 'nama': nama})

# ============ USER MANAGEMENT ============
@app.route('/api/users', methods=['GET'])
@admin_required
def get_users():
    users = load_json(USERS_FILE)
    return jsonify({'pegawai': [{'username': u['username'], 'nama': u.get('nama', '')} for u in users['pegawai']]})

@app.route('/api/users', methods=['POST'])
@admin_required
def create_user():
    data = request.json or {}
    username = data.get('username', '').strip().lower()
    password = data.get('password', '')
    nama = data.get('nama', '').strip()
    if not username or not password:
        return jsonify({'error': 'Username dan password wajib'}), 400
    if username == '@adminsandi':
        return jsonify({'error': 'Username tidak valid'}), 400
    if len(password) < 4:
        return jsonify({'error': 'Password min 4 karakter'}), 400
    users = load_json(USERS_FILE)
    if any(u['username'] == username for u in users['pegawai']):
        return jsonify({'error': 'Username sudah terdaftar'}), 400
    users['pegawai'].append({'username': username, 'password': generate_password_hash(password), 'nama': nama or username})
    save_json(USERS_FILE, users)

    # 🔔 Trigger backup: tambah pegawai
    trigger_backup(f"Tambah pegawai @{username} ({nama or username})")

    return jsonify({'success': True})

@app.route('/api/users/<username>', methods=['DELETE'])
@admin_required
def delete_user(username):
    users = load_json(USERS_FILE)
    users['pegawai'] = [u for u in users['pegawai'] if u['username'] != username]
    save_json(USERS_FILE, users)

    # 🔔 Trigger backup: hapus pegawai
    trigger_backup(f"Hapus pegawai @{username}")

    return jsonify({'success': True})

# ============ PRICE MEMORY ============
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
        tanggal = data.get('tanggal', '')
        jenis = data.get('jenis', '')
        keterangan = data.get('keterangan', '').strip()

        if not tanggal or jenis not in SEMUA_JENIS:
            return jsonify({'error': 'Data tidak valid'}), 400

        is_pengeluaran = jenis in JENIS_PENGELUARAN

        if is_pengeluaran:
            total = int(data.get('totalNilai', 0))
            if total <= 0:
                return jsonify({'error': 'Total pengeluaran harus > 0'}), 400
            jumlah, harga = 0, 0
        else:
            jumlah = int(data.get('jumlahTabung', 0))
            harga = int(data.get('hargaPerPcs', 0))
            if jumlah <= 0 or harga <= 0:
                return jsonify({'error': 'Jumlah dan harga harus > 0'}), 400
            total = jumlah * harga

        transaksi_baru = {
            'id': int(datetime.now().timestamp() * 1000),
            'tanggal': tanggal,
            'jenis': jenis,
            'keterangan': keterangan,
            'jumlahTabung': jumlah,
            'hargaPerPcs': harga,
            'totalNilai': total,
            'createdBy': session['username'],
            'createdAt': datetime.now().isoformat()
        }

        data_list = load_json(TRANSAKSI_FILE)
        data_list.append(transaksi_baru)
        save_json(TRANSAKSI_FILE, data_list)

        if not is_pengeluaran:
            update_harga_memory(jenis, harga)

        # 🔔 Trigger backup: tambah transaksi
        trigger_backup(f"Tambah {jenis} - {jumlah} tabung @ {format_rp(harga)} oleh {session['username']}")

        return jsonify({'success': True, 'data': transaksi_baru})
    except (ValueError, TypeError) as e:
        return jsonify({'error': f'Data tidak valid: {str(e)}'}), 400

@app.route('/api/transaksi/<int:id>', methods=['PUT'])
@login_required
def edit_transaksi(id):
    data_list = load_json(TRANSAKSI_FILE)
    target = next((t for t in data_list if t['id'] == id), None)
    if not target:
        return jsonify({'error': 'Transaksi tidak ditemukan'}), 404

    if session['role'] == 'pegawai':
        if target.get('createdBy') != session['username']:
            return jsonify({'error': 'Hanya bisa edit transaksi sendiri'}), 403
        try:
            created_at = datetime.fromisoformat(target['createdAt'])
            if (datetime.now() - created_at).total_seconds() > EDIT_LOCK_SECONDS:
                return jsonify({'error': 'Transaksi sudah di-lock (>1 jam)'}), 403
        except (ValueError, KeyError):
            return jsonify({'error': 'Data tidak valid'}), 400

    data = request.json or {}
    try:
        tanggal = data.get('tanggal', target['tanggal'])
        jenis = data.get('jenis', target['jenis'])
        keterangan = data.get('keterangan', target.get('keterangan', ''))

        if jenis not in SEMUA_JENIS:
            return jsonify({'error': 'Jenis tidak valid'}), 400

        is_pengeluaran = jenis in JENIS_PENGELUARAN

        if is_pengeluaran:
            total = int(data.get('totalNilai', target['totalNilai']))
            if total <= 0:
                return jsonify({'error': 'Total harus > 0'}), 400
            jumlah, harga = 0, 0
        else:
            jumlah = int(data.get('jumlahTabung', target.get('jumlahTabung', 0)))
            harga = int(data.get('hargaPerPcs', target.get('hargaPerPcs', 0)))
            if jumlah <= 0 or harga <= 0:
                return jsonify({'error': 'Jumlah dan harga harus > 0'}), 400
            total = jumlah * harga

        target.update({
            'tanggal': tanggal, 'jenis': jenis, 'keterangan': keterangan.strip(),
            'jumlahTabung': jumlah, 'hargaPerPcs': harga, 'totalNilai': total,
            'editedBy': session['username'], 'editedAt': datetime.now().isoformat()
        })

        save_json(TRANSAKSI_FILE, data_list)
        if not is_pengeluaran:
            update_harga_memory(jenis, harga)

        # 🔔 Trigger backup: edit transaksi
        trigger_backup(f"Edit {jenis} (ID:{id}) oleh {session['username']}")

        return jsonify({'success': True, 'data': target})
    except (ValueError, TypeError) as e:
        return jsonify({'error': f'Data tidak valid: {str(e)}'}), 400

@app.route('/api/transaksi/<int:id>', methods=['DELETE'])
@admin_required
def delete_transaksi(id):
    data_list = load_json(TRANSAKSI_FILE)
    original_len = len(data_list)
    data_list = [t for t in data_list if t['id'] != id]
    if len(data_list) == original_len:
        return jsonify({'error': 'Tidak ditemukan'}), 404
    save_json(TRANSAKSI_FILE, data_list)

    # 🔔 Trigger backup: hapus transaksi
    trigger_backup(f"Hapus transaksi ID:{id} oleh {session['username']}")

    return jsonify({'success': True})

@app.route('/api/transaksi', methods=['DELETE'])
@admin_required
def reset_transaksi():
    save_json(TRANSAKSI_FILE, [])

    # 🔔 Trigger backup: reset semua data
    trigger_backup(f"⚠️ RESET SEMUA DATA oleh {session['username']}")

    return jsonify({'success': True})

# ============ MANUAL BACKUP ============
@app.route('/api/backup-now', methods=['POST'])
@admin_required
def backup_now():
    success, msg = send_telegram_backup_sync(f"Backup manual oleh {session['username']}")
    if success: return jsonify({'success': True})
    return jsonify({'success': False, 'error': msg}), 500

# ============ HELPER FORMAT ============
def format_rp(angka):
    return f"Rp {angka:,.0f}".replace(',', '.')

# ============ START ============
if __name__ == '__main__':
    print("=" * 60)
    print("📊 Server LPG: http://localhost:5000")
    print("👑 Admin: @adminsandi | ⏰ Lock: 1 jam")
    print("⚡ Backup: Event-driven (otomatis saat ada perubahan)")
    print("=" * 60)
    app.run(host='0.0.0.0', port=5000, debug=False, threaded=True)