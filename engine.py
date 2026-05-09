import os
import shutil
import uuid
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

def buat_kunci_dari_password(password: str, salt: bytes):
    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=32,
        salt=salt,
        iterations=480000,
    )
    # AES-GCM butuh raw bytes murni, BUKAN base64
    return kdf.derive(password.encode())

def kunci_brankas_logic(nama_folder, password_kamu):
    file_zip = nama_folder + ".zip"
    path_simpan = None
    try:
        salt = os.urandom(16)
        kunci = buat_kunci_dari_password(password_kamu, salt)
        
        # Panggil mesin AES-GCM
        aesgcm = AESGCM(kunci)
        # Bikin Nonce 12-byte acak (Wajib untuk AES-GCM)
        nonce = os.urandom(12) 

        while True:
            id_acak = uuid.uuid4().hex[:8]
            nama_file_kunci = f"brankas_{id_acak}.locked"
            path_simpan = os.path.join(os.path.dirname(nama_folder), nama_file_kunci)
            if not os.path.exists(path_simpan): break

        abs_path = os.path.abspath(nama_folder)
        parent_dir = os.path.dirname(abs_path)
        target_dir = os.path.basename(abs_path)
        shutil.make_archive(nama_folder, 'zip', parent_dir, target_dir)

        with open(file_zip, "rb") as fz:
            zip_data = fz.read()

        nama_bytes = target_dir.encode('utf-8')
        panjang_nama = len(nama_bytes).to_bytes(2, byteorder='big')
        
        # Payload murni tanpa diubah ke teks
        payload = panjang_nama + nama_bytes + zip_data
        
        # Proses enkripsi tingkat tinggi
        encrypted_data = aesgcm.encrypt(nonce, payload, None)

        # Simpan struktur baru: SALT + NONCE + CIPHERTEXT
        with open(path_simpan, "wb") as fk:
            fk.write(salt + nonce + encrypted_data)

        os.remove(file_zip)
        shutil.rmtree(nama_folder)
        size_kb = os.path.getsize(path_simpan) / 1024
        return True, f"Berhasil!\n\nNama Brankas: {nama_file_kunci}\nUkuran: {size_kb:.1f} KB"
        
    except Exception as e:
        if os.path.exists(file_zip): os.remove(file_zip)
        if path_simpan and os.path.exists(path_simpan): os.remove(path_simpan)
        return False, str(e)

def buka_brankas_logic(path_file_kunci, password_kamu, force=False):
    try:
        with open(path_file_kunci, "rb") as fk:
            data_brankas = fk.read()
            
        # Ekstrak 3 gerbong data
        salt = data_brankas[:16]
        nonce = data_brankas[16:28] # Nonce berada di byte 16 sampai 27
        encrypted_data = data_brankas[28:] # Sisanya adalah data terenkripsi
        
        kunci = buat_kunci_dari_password(password_kamu, salt)
        aesgcm = AESGCM(kunci)

        try:
            # Buka gemboknya menggunakan Nonce yang sama
            payload = aesgcm.decrypt(nonce, encrypted_data, None)
        except:
            return "WRONG_PW", None

        panjang_nama = int.from_bytes(payload[:2], byteorder='big')
        nama_folder_tujuan = payload[2:2 + panjang_nama].decode('utf-8')
        zip_data = payload[2 + panjang_nama:]
        
        base_dir = os.path.dirname(path_file_kunci)
        path_tujuan_full = os.path.join(base_dir, nama_folder_tujuan)

        if os.path.exists(path_tujuan_full) and not force:
            return "OVERWRITE", nama_folder_tujuan

        file_zip_sementara = os.path.join(base_dir, "temp_" + uuid.uuid4().hex[:8] + ".zip")
        with open(file_zip_sementara, "wb") as fz:
            fz.write(zip_data)
            
        shutil.unpack_archive(file_zip_sementara, base_dir, 'zip')
        os.remove(file_zip_sementara)
        
        return "SUCCESS", nama_folder_tujuan
        
    except Exception as e:
        return "ERROR", str(e)