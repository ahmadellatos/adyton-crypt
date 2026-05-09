import customtkinter as ctk
from tkinter import filedialog
import threading
from engine import kunci_brankas_logic, buka_brankas_logic

# Setting Tema Global
ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue") 

class AppBrankas(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title("Digital Locker - Professional")
        
        # Penempatan jendela di tengah layar (Matematika Presisi)
        app_width, app_height = 500, 580
        screen_width = self.winfo_screenwidth()
        screen_height = self.winfo_screenheight()
        x = int((screen_width / 2) - (app_width / 2))
        y = int((screen_height / 2) - (app_height / 2))
        self.geometry(f"{app_width}x{app_height}+{x}+{y}")
        self.resizable(False, False)

        # 1. Navigasi Tab Modern (Segmented Control style via CTkTabview)
        self.tabview = ctk.CTkTabview(self, width=460, height=530, corner_radius=15)
        self.tabview.pack(padx=20, pady=10)
        self.tab_kunci = self.tabview.add("Kunci Folder")
        self.tab_buka = self.tabview.add("Buka Brankas")
        
        self.setup_tab_kunci()
        self.setup_tab_buka()

    # ==========================================
    # TAB 1: KUNCI FOLDER
    # ==========================================
    def setup_tab_kunci(self):
        self.path_folder_kunci = None
        self.show_pw_v1 = False

        # Header
        ctk.CTkLabel(self.tab_kunci, text="Pilih Folder untuk Diamankan", font=("Arial", 16, "bold")).pack(pady=(15, 10))
        
        # 4. Kontrol Pengguna: Container Path + Tombol Clear
        self.frame_path_kunci = ctk.CTkFrame(self.tab_kunci, fg_color="transparent")
        self.frame_path_kunci.pack(fill="x", padx=30)
        
        self.btn_browse_kunci = ctk.CTkButton(self.frame_path_kunci, text="📂 Browse Folder", command=self.pilih_folder, corner_radius=8)
        self.btn_browse_kunci.pack(side="left", expand=True, fill="x", padx=(0, 5))
        
        self.btn_clear_kunci = ctk.CTkButton(self.frame_path_kunci, text="✖️", width=35, fg_color="#333333", hover_color="#555555", command=self.clear_pilihan_kunci)
        # Tombol clear disembunyikan dulu
        
        self.lbl_path_folder = ctk.CTkLabel(self.tab_kunci, text="Belum ada folder dipilih", text_color="gray", font=("Arial", 11))
        self.lbl_path_folder.pack(pady=(2, 10))

        # 3. Label Teks di atas Input Field
        ctk.CTkLabel(self.tab_kunci, text="Password Brankas", font=("Arial", 12, "bold")).pack(anchor="w", padx=35)
        
        # 5. Fitur Tampilkan Password Terintegrasi (Eye Icon)
        self.frame_pw1 = ctk.CTkFrame(self.tab_kunci, fg_color="transparent")
        self.frame_pw1.pack(fill="x", padx=30, pady=(0, 10))
        
        self.entry_pw_kunci = ctk.CTkEntry(self.frame_pw1, placeholder_text="Buat password kuat...", show="*", height=35, corner_radius=8)
        self.entry_pw_kunci.pack(side="left", expand=True, fill="x")
        
        self.btn_eye_kunci = ctk.CTkButton(self.frame_pw1, text="👁️", width=35, height=35, fg_color="transparent", hover_color="#2B2B2B", command=self.toggle_pw_kunci)
        self.btn_eye_kunci.pack(side="right", padx=(5, 0))

        ctk.CTkLabel(self.tab_kunci, text="Konfirmasi Password", font=("Arial", 12, "bold")).pack(anchor="w", padx=35)
        self.entry_pw_kunci_konfirm = ctk.CTkEntry(self.tab_kunci, placeholder_text="Ulangi password...", show="*", height=35, corner_radius=8)
        self.entry_pw_kunci_konfirm.pack(fill="x", padx=30, pady=(0, 15))
        self.entry_pw_kunci_konfirm.bind("<Return>", lambda e: self.proses_kunci())

        # 2. Tombol Aksi Utama Biru (Safe/Formal)
        self.btn_eksekusi_kunci = ctk.CTkButton(self.tab_kunci, text="KUNCI SEKARANG", font=("Arial", 13, "bold"), height=40, corner_radius=10, command=self.proses_kunci)
        self.btn_eksekusi_kunci.pack(fill="x", padx=30, pady=10)
        
        self.lbl_status_kunci = ctk.CTkLabel(self.tab_kunci, text="", font=("Arial", 12))
        self.lbl_status_kunci.pack(pady=5)

    def toggle_pw_kunci(self):
        self.show_pw_v1 = not self.show_pw_v1
        char = "" if self.show_pw_v1 else "*"
        self.entry_pw_kunci.configure(show=char)
        self.entry_pw_kunci_konfirm.configure(show=char)

    def clear_pilihan_kunci(self):
        self.path_folder_kunci = None
        self.lbl_path_folder.configure(text="Belum ada folder dipilih", text_color="gray")
        self.btn_clear_kunci.pack_forget()

    def pilih_folder(self):
        folder = filedialog.askdirectory()
        if folder:
            self.path_folder_kunci = folder
            tampil = folder if len(folder) < 45 else "..." + folder[-42:]
            self.lbl_path_folder.configure(text=tampil, text_color="#1f6aa5")
            self.btn_clear_kunci.pack(side="right", padx=(5, 0))
            self.lbl_status_kunci.configure(text="")

    def proses_kunci(self):
        if not self.path_folder_kunci:
            self.lbl_status_kunci.configure(text="⚠️ Pilih folder dulu!", text_color="#E67E22")
            return
        pw, pw2 = self.entry_pw_kunci.get(), self.entry_pw_kunci_konfirm.get()
        if not pw:
            self.lbl_status_kunci.configure(text="⚠️ Password kosong!", text_color="#E67E22")
            return
        if pw != pw2:
            self.lbl_status_kunci.configure(text="⚠️ Password tidak cocok!", text_color="#E67E22")
            return
        
        self.btn_eksekusi_kunci.configure(state="disabled", text="⏳ Memproses...")
        threading.Thread(target=self._run_kunci, args=(self.path_folder_kunci, pw), daemon=True).start()

    def _run_kunci(self, path, pw):
        res, msg = kunci_brankas_logic(path, pw)
        self.after(0, lambda: self._selesai_kunci(res, msg))

    def _selesai_kunci(self, sukses, pesan):
        self.btn_eksekusi_kunci.configure(state="normal", text="KUNCI SEKARANG")
        if sukses:
            self.lbl_status_kunci.configure(text="✔️ " + pesan, text_color="#2ECC71")
            self.entry_pw_kunci.delete(0, 'end'); self.entry_pw_kunci_konfirm.delete(0, 'end')
            self.clear_pilihan_kunci()
        else:
            self.lbl_status_kunci.configure(text="❌ " + pesan, text_color="#E74C3C")

    # ==========================================
    # TAB 2: BUKA BRANKAS
    # ==========================================
    def setup_tab_buka(self):
        self.path_file_buka = None
        self.show_pw_v2 = False
        self.menunggu_konfirmasi_timpa = False

        ctk.CTkLabel(self.tab_buka, text="Pilih Brankas untuk Dibongkar", font=("Arial", 16, "bold")).pack(pady=(15, 10))
        
        self.frame_path_buka = ctk.CTkFrame(self.tab_buka, fg_color="transparent")
        self.frame_path_buka.pack(fill="x", padx=30)
        
        self.btn_browse_buka = ctk.CTkButton(self.frame_path_buka, text="📄 Browse .locked", command=self.pilih_file, corner_radius=8)
        self.btn_browse_buka.pack(side="left", expand=True, fill="x")
        
        self.btn_clear_buka = ctk.CTkButton(self.frame_path_buka, text="✖️", width=35, fg_color="#333333", command=self.clear_pilihan_buka)
        
        self.lbl_path_file = ctk.CTkLabel(self.tab_buka, text="File belum dipilih", text_color="gray", font=("Arial", 11))
        self.lbl_path_file.pack(pady=(2, 10))

        ctk.CTkLabel(self.tab_buka, text="Masukkan Password Brankas", font=("Arial", 12, "bold")).pack(anchor="w", padx=35)
        self.frame_pw2 = ctk.CTkFrame(self.tab_buka, fg_color="transparent")
        self.frame_pw2.pack(fill="x", padx=30, pady=(0, 15))
        
        self.entry_pw_buka = ctk.CTkEntry(self.frame_pw2, placeholder_text="Ketik password di sini...", show="*", height=35, corner_radius=8)
        self.entry_pw_buka.pack(side="left", expand=True, fill="x")
        self.entry_pw_buka.bind("<Return>", lambda e: self.proses_buka())
        
        self.btn_eye_buka = ctk.CTkButton(self.frame_pw2, text="👁️", width=35, height=35, fg_color="transparent", hover_color="#2B2B2B", command=self.toggle_pw_buka)
        self.btn_eye_buka.pack(side="right", padx=(5, 0))

        self.btn_eksekusi_buka = ctk.CTkButton(self.tab_buka, text="BUKA BRANKAS", font=("Arial", 13, "bold"), height=40, corner_radius=10, fg_color="#2980B9", hover_color="#1F618D", command=self.proses_buka)
        self.btn_eksekusi_buka.pack(fill="x", padx=30, pady=10)
        
        self.lbl_status_buka = ctk.CTkLabel(self.tab_buka, text="", font=("Arial", 12))
        self.lbl_status_buka.pack(pady=5)

    def toggle_pw_buka(self):
        self.show_pw_v2 = not self.show_pw_v2
        self.entry_pw_buka.configure(show="" if self.show_pw_v2 else "*")

    def clear_pilihan_buka(self):
        self.path_file_buka = None
        self.lbl_path_file.configure(text="File belum dipilih", text_color="gray")
        self.btn_clear_buka.pack_forget()

    def pilih_file(self):
        f = filedialog.askopenfilename(filetypes=[("Locked Files", "*.locked")])
        if f: 
            self.path_file_buka = f
            tampil = f if len(f) < 45 else "..." + f[-42:]
            self.lbl_path_file.configure(text=tampil, text_color="#1f6aa5")
            self.btn_clear_buka.pack(side="right", padx=(5, 0))
            self.menunggu_konfirmasi_timpa = False
            self.btn_eksekusi_buka.configure(text="BUKA BRANKAS", fg_color="#2980B9")

    def proses_buka(self):
        force = False
        if self.menunggu_konfirmasi_timpa:
            force = True
            self.menunggu_konfirmasi_timpa = False
            self.btn_eksekusi_buka.configure(text="BUKA BRANKAS", fg_color="#2980B9")

        if not self.path_file_buka:
            self.lbl_status_buka.configure(text="⚠️ Pilih file .locked dulu!", text_color="#E67E22")
            return
        pw = self.entry_pw_buka.get()
        if not pw:
            self.lbl_status_buka.configure(text="⚠️ Masukkan password!", text_color="#E67E22")
            return

        self.btn_eksekusi_buka.configure(state="disabled", text="⏳ Membuka...")
        threading.Thread(target=self._run_buka, args=(self.path_file_buka, pw, force), daemon=True).start()

    def _run_buka(self, path, pw, force):
        status, msg = buka_brankas_logic(path, pw, force)
        self.after(0, lambda: self._selesai_buka(status, msg))

    def _selesai_buka(self, status, msg):
        self.btn_eksekusi_buka.configure(state="normal")
        if status == "SUCCESS":
            self.lbl_status_buka.configure(text=f"✔️ Berhasil! Folder '{msg}' kembali.", text_color="#2ECC71")
            self.entry_pw_buka.delete(0, 'end'); self.clear_pilihan_buka()
        elif status == "WRONG_PW":
            self.lbl_status_buka.configure(text="❌ Password Salah!", text_color="#E74C3C")
            self.btn_eksekusi_buka.configure(text="BUKA BRANKAS")
        elif status == "OVERWRITE":
            self.menunggu_konfirmasi_timpa = True
            self.btn_eksekusi_buka.configure(text="⚠️ KLIK LAGI UNTUK TIMPA", fg_color="#E67E22")
            self.lbl_status_buka.configure(text=f"Folder '{msg}' sudah ada!", text_color="#E67E22")
        else:
            self.lbl_status_buka.configure(text="❌ Error: " + msg, text_color="#E74C3C")
            