from flask import Flask, request, jsonify, send_file
import json
import os
import requests
from datetime import datetime

app = Flask(__name__)

# Konfigurasi Telegram
TELEGRAM_TOKEN = "8750135615:AAFZF-xcNW_wB49CxO_Lc_vvwSAb76sepAY"
CHAT_ID = "7051115490"
DATA_FILE = "bku_data.json"

# Fungsi untuk memuat data dari JSON
def load_data():
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, 'r', encoding='utf-8') as f:
            data = json.load(f)
            # Jika format baru (ada pembungkus), ambil array 'transaksi'
            if isinstance(data, dict) and 'transaksi' in data:
                return data['transaksi']
            # Jika format lama (hanya array), kembalikan apa adanya
            elif isinstance(data, list):
                return data
    return []

# Fungsi untuk menyimpan data ke JSON dengan Format Baru
def save_data(data_list):
    formatted_tx = []
    
    # 1. Format ulang setiap transaksi dan hitung netto
    for t in data_list:
        # Hitung netto
        netto = (t.get('penerimaan', 0) - t.get('penarikan', 0) - 
                 t.get('pengeluaran', 0) - t.get('ppn', 0) - t.get('pph22', 0))
        
        formatted_tx.append({
            "tanggal": t.get('tanggal', ''),
            "uraian": t.get('uraian', ''),
            "nomorBukti": t.get('nomorBukti', t.get('nomor_bukti', '')), # Kompatibel dengan key lama
            "penerimaan": t.get('penerimaan', 0),
            "penarikan": t.get('penarikan', 0),
            "pengeluaran": t.get('pengeluaran', 0),
            "ppn": t.get('ppn', 0),
            "pph22": t.get('pph22', 0),
            "netto": netto
        })

    # 2. Buat struktur JSON pembungkus (Wrapper)
    wrapper = {
        "aplikasi": "Buku Keuangan",
        "versi": "2.0",
        "tanggalSimpan": datetime.now().isoformat(timespec='milliseconds') + "Z",
        "jumlahTransaksi": len(formatted_tx),
        "transaksi": formatted_tx
    }
    
    # 3. Simpan ke file (indent=1 agar formatnya rapi seperti contoh)
    with open(DATA_FILE, 'w', encoding='utf-8') as f:
        json.dump(wrapper, f, indent=1, ensure_ascii=False)

# Fungsi untuk mengirim FILE JSON ke Telegram sebagai Backup
def send_telegram_backup():
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendDocument"
    try:
        with open(DATA_FILE, 'rb') as f:
            files = {'document': (DATA_FILE, f, 'application/json')}
            data = {
                'chat_id': CHAT_ID,
                'caption': f"🔄 <b>Backup Otomatis Buku Keuangan</b>\n⏰ {datetime.now().strftime('%d-%m-%Y %H:%M:%S')}",
                'parse_mode': 'HTML'
            }
            requests.post(url, data=data, files=files, timeout=15)
    except Exception as e:
        print(f"Error sending backup: {e}")

@app.route('/')
def home():
    return send_file('BKU.html')

@app.route('/api/data', methods=['GET', 'POST'])
def handle_data():
    if request.method == 'POST':
        data_req = request.json
        transactions = data_req.get('transactions', [])
        
        save_data(transactions)
        send_telegram_backup()
        
        return jsonify({"status": "success"})
    else:
        return jsonify(load_data())

@app.route('/api/download')
def download_json():
    return send_file(DATA_FILE, as_attachment=True, download_name='bku_data.json')

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5003, debug=True)