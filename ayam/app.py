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
app.secret_key = 'AYAM-KUB-SECRET-KEY-GANTI-DENGAN-RANDOM-STRING-PANJANG'

TELEGRAM_TOKEN = '8750135615:AAFZF-xcNW_wB49CxO_Lc_vvwSAb76sepAY'
TELEGRAM_CHAT_ID = '7051115490'
BACKUP_INTERVAL = 300
EDIT_LOCK_SECONDS = 3600

DATA_DIR = 'data'
USERS_FILE = os.path.join(DATA_DIR, 'users.json')
AYAM_FILE = os.path.join(DATA_DIR, 'ayam.json')
HARGA_FILE = os.path.join(DATA_DIR, 'harga.json')

JENIS_TRANSAKSI = ['Penjualan', 'Retur']
JENIS_PENGELUARAN = ['Operasional', 'Administrasi', 'Lain-lain']
SEMUA_JENIS = JENIS_TRANSAKSI + JENIS_PENGELUARAN

# ============ INIT ============
os.makedirs(DATA_DIR, exist_ok=True)

def init_files():
    if not os.path.exists(USERS_FILE):
        save_json(USERS_FILE, {'pegawai': []})
    if not os.path.exists(AYAM_FILE):
        save_json(AYAM_FILE, [])
    if not os.path.exists(HARGA_FILE):
        save_json(HARGA_FILE, {
            'Penjualan': {'jantan': 0, 'betina': 0},
            'Retur': {'jantan': 0, 'betina': 0}
        })

def load_json(path):
    try:
        with open(path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        if 'ayam' in path: return []
        elif 'harga' in path: return {'Penjualan': {'jantan': 0, 'betina': 0}, 'Retur': {'jantan': 0, 'betina': 0}}
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

def update_harga_memory(jenis, harga_jantan, harga_betina):
    if jenis not in JENIS_TRANSAKSI: return
    harga = load_json(HARGA_FILE)
    if jenis not in harga: harga[jenis] = {'jantan': 0, 'betina': 0}
    if harga_jantan > 0: harga[jenis]['jantan'] = harga_jantan
    if harga_betina > 0: harga[jenis]['betina'] = harga_betina
    save_json(HARGA_FILE, harga)

# ============ TELEGRAM BACKUP ============
def send_telegram_backup():
    try:
        if not os.path.exists(AYAM_FILE):
            return False, "File tidak ditemukan"
        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendDocument"
        caption = (f"🐔 *Backup Otomatis Ayam KUB*\n"
                   f"🕐 Waktu: {datetime.now().strftime('%d/%m/%Y %H:%M:%S')}\n"
                   f"📁 File: ayam.json")
        with open(AYAM_FILE, 'rb') as f:
            files = {'document': ('ayam.json', f, 'application/json')}
            data = {'chat_id': TELEGRAM_CHAT_ID, 'caption': caption, 'parse_mode': 'Markdown'}
            response = requests.post(url, files=files, data=data, timeout=30)
        if response.status_code == 200:
            result = response.json()
            if result.get('ok'): return True, "OK"
            return False, result.get('description')
        return False, f"HTTP {response.status_code}"
    except Exception as e:
        return False, str(e)

def backup_loop():
    print(f"✅ Auto backup aktif (setiap {BACKUP_INTERVAL} detik)")
    while True:
        time.sleep(BACKUP_INTERVAL)
        try:
            success, msg = send_telegram_backup()
            ts = datetime.now().strftime('%H:%M:%S')
            print(f"[{ts}] {'✅' if success else f'❌ {msg}'}")
        except Exception as e:
            print(f"[Backup Error] {e}")

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
    return send_from_directory('.', 'ayam.html')

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

# ========== FIX: Endpoint /api/me dengan fallback aman ==========
@app.route('/api/me')
def me():
    if 'username' not in session:
        return jsonify({'error': 'Not logged in'}), 401
    
    # Fallback aman: nama tidak pernah null/undefined
    nama = session.get('nama') or session.get('username') or 'User'
    role = session.get('role') or 'pegawai'
    username = session.get('username') or ''
    
    return jsonify({
        'username': username,
        'role': role,
        'nama': nama
    })

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

# ============ PRICE MEMORY ============
@app.route('/api/harga', methods=['GET'])
@login_required
def get_harga():
    return jsonify(load_json(HARGA_FILE))

# ============ TRANSAKSI AYAM ============
@app.route('/api/ayam', methods=['GET'])
@login_required
def get_ayam():
    return jsonify(load_json(AYAM_FILE))

@app.route('/api/ayam', methods=['POST'])
@login_required
def add_ayam():
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
            jml_jantan = harga_jantan = jml_betina = harga_betina = 0
            total_jantan = total_betina = 0
        else:
            jml_jantan = int(data.get('jmlJantan', 0))
            harga_jantan = int(data.get('hargaJantan', 0))
            jml_betina = int(data.get('jmlBetina', 0))
            harga_betina = int(data.get('hargaBetina', 0))

            if jml_jantan <= 0 and jml_betina <= 0:
                return jsonify({'error': 'Jumlah jantan/betina harus > 0'}), 400

            total_jantan = jml_jantan * harga_jantan
            total_betina = jml_betina * harga_betina
            total = total_jantan + total_betina

        transaksi_baru = {
            'id': int(datetime.now().timestamp() * 1000),
            'tanggal': tanggal,
            'jenis': jenis,
            'keterangan': keterangan,
            'jmlJantan': jml_jantan,
            'hargaJantan': harga_jantan,
            'totalJantan': total_jantan,
            'jmlBetina': jml_betina,
            'hargaBetina': harga_betina,
            'totalBetina': total_betina,
            'total': total,
            'createdBy': session['username'],
            'createdAt': datetime.now().isoformat()
        }

        data_list = load_json(AYAM_FILE)
        data_list.append(transaksi_baru)
        save_json(AYAM_FILE, data_list)

        if not is_pengeluaran:
            update_harga_memory(jenis, harga_jantan, harga_betina)

        return jsonify({'success': True, 'data': transaksi_baru})
    except (ValueError, TypeError) as e:
        return jsonify({'error': f'Data tidak valid: {str(e)}'}), 400

@app.route('/api/ayam/<int:id>', methods=['PUT'])
@login_required
def edit_ayam(id):
    data_list = load_json(AYAM_FILE)
    target = next((t for t in data_list if t['id'] == id), None)
    if not target:
        return jsonify({'error': 'Tidak ditemukan'}), 404

    if session['role'] == 'pegawai':
        if target.get('createdBy') != session['username']:
            return jsonify({'error': 'Hanya bisa edit sendiri'}), 403
        try:
            created_at = datetime.fromisoformat(target['createdAt'])
            if (datetime.now() - created_at).total_seconds() > EDIT_LOCK_SECONDS:
                return jsonify({'error': 'Sudah di-lock (>1 jam)'}), 403
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
            total = int(data.get('totalNilai', target['total']))
            if total <= 0:
                return jsonify({'error': 'Total harus > 0'}), 400
            jml_jantan = harga_jantan = jml_betina = harga_betina = 0
            total_jantan = total_betina = 0
        else:
            jml_jantan = int(data.get('jmlJantan', target.get('jmlJantan', 0)))
            harga_jantan = int(data.get('hargaJantan', target.get('hargaJantan', 0)))
            jml_betina = int(data.get('jmlBetina', target.get('jmlBetina', 0)))
            harga_betina = int(data.get('hargaBetina', target.get('hargaBetina', 0)))

            if jml_jantan <= 0 and jml_betina <= 0:
                return jsonify({'error': 'Jumlah harus > 0'}), 400

            total_jantan = jml_jantan * harga_jantan
            total_betina = jml_betina * harga_betina
            total = total_jantan + total_betina

        target.update({
            'tanggal': tanggal,
            'jenis': jenis,
            'keterangan': keterangan.strip(),
            'jmlJantan': jml_jantan,
            'hargaJantan': harga_jantan,
            'totalJantan': total_jantan,
            'jmlBetina': jml_betina,
            'hargaBetina': harga_betina,
            'totalBetina': total_betina,
            'total': total,
            'editedBy': session['username'],
            'editedAt': datetime.now().isoformat()
        })

        save_json(AYAM_FILE, data_list)
        if not is_pengeluaran:
            update_harga_memory(jenis, harga_jantan, harga_betina)

        return jsonify({'success': True, 'data': target})
    except (ValueError, TypeError) as e:
        return jsonify({'error': f'Data tidak valid: {str(e)}'}), 400

@app.route('/api/ayam/<int:id>', methods=['DELETE'])
@admin_required
def delete_ayam(id):
    data_list = load_json(AYAM_FILE)
    original_len = len(data_list)
    data_list = [t for t in data_list if t['id'] != id]
    if len(data_list) == original_len:
        return jsonify({'error': 'Tidak ditemukan'}), 404
    save_json(AYAM_FILE, data_list)
    return jsonify({'success': True})

@app.route('/api/ayam', methods=['DELETE'])
@admin_required
def reset_ayam():
    save_json(AYAM_FILE, [])
    return jsonify({'success': True})

@app.route('/api/backup-now', methods=['POST'])
@admin_required
def backup_now():
    success, msg = send_telegram_backup()
    if success: return jsonify({'success': True})
    return jsonify({'success': False, 'error': msg}), 500

# ============ START ============
if __name__ == '__main__':
    threading.Thread(target=backup_loop, daemon=True).start()
    print("=" * 60)
    print("🐔 Server Ayam KUB: http://localhost:5001")
    print("👑 Admin: @adminsandi | ⏰ Lock: 1 jam")
    print("=" * 60)
    app.run(host='0.0.0.0', port=5001, debug=False, threaded=True)
