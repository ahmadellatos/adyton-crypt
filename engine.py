import os
import shutil
import uuid
import tempfile
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from cryptography.hazmat.backends import default_backend

# Ukuran sepotong data yang ditarik ke RAM (64 KB)
CHUNK_SIZE = 64 * 1024 

def secure_delete(path):
    """
    Menghapus file/folder secara aman dengan menimpa data aslinya (Zero-fill)
    sebelum dihapus agar tidak bisa di-recover.
    """
    if not os.path.exists(path):
        return

    if os.path.isfile(path):
        try:
            ukuran = os.path.getsize(path)
            # Timpa file dengan byte kosong secara streaming agar hemat RAM
            with open(path, "r+b") as f:
                bytes_ditulis = 0
                while bytes_ditulis < ukuran:
                    chunk = min(CHUNK_SIZE, ukuran - bytes_ditulis)
                    f.write(b'\x00' * chunk)
                    bytes_ditulis += chunk
            os.remove(path)
        except Exception:
            pass # Lanjutkan walau gagal di file tertentu
            
    elif os.path.isdir(path):
        for root, dirs, files in os.walk(path, topdown=False):
            for name in files:
                secure_delete(os.path.join(root, name))
            for name in dirs:
                try:
                    os.rmdir(os.path.join(root, name))
                except OSError:
                    pass
        try:
            os.rmdir(path)
        except OSError:
            shutil.rmtree(path, ignore_errors=True)


def buat_kunci_dari_password(password: str, salt: bytes):
    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=32,
        salt=salt,
        iterations=480000,
        backend=default_backend()
    )
    return kdf.derive(password.encode())


def kunci_brankas_logic(nama_folder, password_kamu, hapus_asli=False):
    # Gunakan direktori Temp OS agar tidak mengotori folder target
    id_acak_temp = uuid.uuid4().hex[:8]
    temp_zip_base = os.path.join(tempfile.gettempdir(), f"brankas_temp_{id_acak_temp}")
    file_zip = temp_zip_base + ".zip"
    
    path_simpan = None
    
    try:
        salt = os.urandom(16)
        kunci = buat_kunci_dari_password(password_kamu, salt)
        nonce = os.urandom(12) 

        while True:
            id_acak = uuid.uuid4().hex[:8]
            nama_file_kunci = f"brankas_{id_acak}.locked"
            path_simpan = os.path.join(os.path.dirname(nama_folder), nama_file_kunci)
            if not os.path.exists(path_simpan): break

        abs_path = os.path.abspath(nama_folder)
        parent_dir = os.path.dirname(abs_path)
        target_dir = os.path.basename(abs_path)
        
        # Buat file zip sementara di folder Temp
        shutil.make_archive(temp_zip_base, 'zip', parent_dir, target_dir)

        # Setup Encryptor mode Streaming
        encryptor = Cipher(
            algorithms.AES(kunci),
            modes.GCM(nonce),
            backend=default_backend()
        ).encryptor()

        # Mulai tulis ke file target (Brankas)
        with open(path_simpan, "wb") as fk:
            fk.write(salt)
            fk.write(nonce)
            
            nama_bytes = target_dir.encode('utf-8')
            panjang_nama = len(nama_bytes).to_bytes(2, byteorder='big')
            fk.write(encryptor.update(panjang_nama + nama_bytes))
            
            with open(file_zip, "rb") as fz:
                while True:
                    chunk = fz.read(CHUNK_SIZE)
                    if not chunk:
                        break
                    fk.write(encryptor.update(chunk))
            
            encryptor.finalize()
            fk.write(encryptor.tag)

        # Bersihkan file zip sementara secara aman
        secure_delete(file_zip)
        
        # Hapus folder asli JIKA user meminta (Checkbox di UI)
        if hapus_asli:
            secure_delete(nama_folder)
        
        size_kb = os.path.getsize(path_simpan) / 1024
        return True, f"Berhasil!\n\nNama Brankas: {nama_file_kunci}\nUkuran: {size_kb:.1f} KB"
        
    except Exception as e:
        if os.path.exists(file_zip): secure_delete(file_zip)
        if path_simpan and os.path.exists(path_simpan): os.remove(path_simpan)
        return False, str(e)


def buka_brankas_logic(path_file_kunci, password_kamu, force=False):
    file_zip_sementara = None
    try:
        ukuran_file_total = os.path.getsize(path_file_kunci)
        
        with open(path_file_kunci, "rb") as fk:
            salt = fk.read(16)
            nonce = fk.read(12)
            
            fk.seek(-16, os.SEEK_END)
            tag = fk.read(16)
            
            panjang_ciphertext = ukuran_file_total - 44
            fk.seek(28) 

            kunci = buat_kunci_dari_password(password_kamu, salt)
            decryptor = Cipher(
                algorithms.AES(kunci),
                modes.GCM(nonce, tag),
                backend=default_backend()
            ).decryptor()

            bytes_left = panjang_ciphertext
            first_chunk_size = min(1024, bytes_left)
            first_chunk = fk.read(first_chunk_size)
            bytes_left -= len(first_chunk)
            
            try:
                decrypted_first = decryptor.update(first_chunk)
            except Exception:
                return "WRONG_PW", None

            panjang_nama = int.from_bytes(decrypted_first[:2], byteorder='big')
            nama_folder_tujuan = decrypted_first[2:2 + panjang_nama].decode('utf-8')
            
            base_dir = os.path.dirname(path_file_kunci)
            path_tujuan_full = os.path.join(base_dir, nama_folder_tujuan)
            
            if os.path.exists(path_tujuan_full) and not force:
                return "OVERWRITE", nama_folder_tujuan

            # Letakkan temporary file di Temp OS
            id_acak_temp = uuid.uuid4().hex[:8]
            file_zip_sementara = os.path.join(tempfile.gettempdir(), f"dec_temp_{id_acak_temp}.zip")
            
            with open(file_zip_sementara, "wb") as fz:
                fz.write(decrypted_first[2 + panjang_nama:])
                
                while bytes_left > 0:
                    chunk = fk.read(min(CHUNK_SIZE, bytes_left))
                    bytes_left -= len(chunk)
                    fz.write(decryptor.update(chunk))
            
            try:
                decryptor.finalize() 
            except Exception:
                # Jika verifikasi password/korupsi file gagal, amankan file temp
                secure_delete(file_zip_sementara)
                return "WRONG_PW", None
                
        # Ekstrak lalu hancurkan zip sementara dengan aman
        shutil.unpack_archive(file_zip_sementara, base_dir, 'zip')
        secure_delete(file_zip_sementara)
        
        return "SUCCESS", nama_folder_tujuan
        
    except Exception as e:
        if file_zip_sementara and os.path.exists(file_zip_sementara): 
            secure_delete(file_zip_sementara)
        return "ERROR", str(e)