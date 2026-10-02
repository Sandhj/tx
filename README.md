INSTALL CLOUDFLARE

<pre><code>pkg update && pkg upgrade -y
pkg install cloudflared -y</code></pre>

CEK HASIL 
<pre><code>cloudflared --version</code></pre>

LOGIN CLOUDFLARE TUNNEL
<pre><code>cloudflared tunnel login</code></pre>

1. Akan muncul link panjang. Salin link tersebut.
2.Buka browser di HP Anda, paste link tersebut, dan login ke akun Cloudflare Anda.
3. Pilih domain yang ingin Anda gunakan untuk tunnel ini.
4. Pastikan file cert berada di folder cloudflared

MEMBUAT TUNNEL BARU
<pre><code>cloudflared tunnel create nama-tunnel-anda</code></pre>
Akan ada ID unik, simpan itu

Buat config.yaml di folder cloudflared
ISI DENGAN
<pre><code>tunnel: ID_TUNNEL_ANDA
credentials-file: /data/data/com.termux/files/home/.cloudflared/ID_TUNNEL_ANDA.json

ingress:
  - hostname: python.domainanda.com
    service: http://localhost:5000
  - service: http_status:404
</code></pre>

ROUTING DNS (Otomatis membuat sub domain sendiri)
<pre><code>cloudflared tunnel route dns nama-tunnel-anda python.domainanda.com
</code></pre>

# Jika ingin Membuat Banyak sistus, hanya menggunakan 1 ID tunnel Cukup bedakan Portya 

<pre><code>
tunnel: ID_TUNNEL_ANDA
credentials-file: /data/data/com.termux/files/home/.cloudflared/ID_TUNNEL_ANDA.json

ingress:
  # Domain/Subdomain pertama mengarah ke localhost:5000
  - hostname: python.domainanda.com
    service: http://localhost:5000

  # Domain/Subdomain kedua mengarah ke localhost:8080
  - hostname: api.domainanda.com
    service: http://localhost:8080

  # Domain/Subdomain ketiga mengarah ke localhost:3000
  - hostname: app.domainanda.net
    service: http://localhost:3000

  # Aturan terakhir (catch-all) jika tidak ada hostname yang cocok
  - service: http_status:404
  
</code></pre>

SELESAI 

masuk lokasi termux
<pre><code>cd /data/data/com.termux/files/home/.cloudflared</code></pre>

Tips:
Karena Termux akan mematikan proses jika layar dimatikan atau aplikasi ditutup, gunakan  tmux  agar server dan tunnel tetap hidup:

Masuk ke sesi tmux:

tmux new -s server-python

Jalankan Python server:

python app.py

Keluar dari sesi tmux (tekan  CTRL + B , lalu  D ).

Buat sesi baru untuk tunnel:

tmux new -s cloudflare-tunnel

Jalankan tunnel:

cloudflared tunnel run nama-tunnel-anda

Keluar lagi ( CTRL + B , lalu  D ).


