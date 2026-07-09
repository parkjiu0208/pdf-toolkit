# -*- coding: utf-8 -*-
"""
PDF 도구 상자 — PDF/PNG 변환 통합 GUI
  - PDF → PNG 변환 (페이지 선택 가능)
  - PDF → 페이지 추출해서 새 PDF
  - PDF → 텍스트 추출 (텍스트 레이어 없으면 자동 OCR)
  - PNG/JPG 여러 장 → PDF 합치기
"""

import os
import sys
import shutil
import threading
import traceback
import subprocess
from pathlib import Path

import tkinter as tk
from tkinter import ttk, filedialog, messagebox

try:
    from tkinterdnd2 import DND_FILES, TkinterDnD
    HAS_DND = True
except ImportError:
    HAS_DND = False

import fitz  # PyMuPDF
import img2pdf

# ---------------------------------------------------------------- 설정

IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".bmp", ".tif", ".tiff", ".webp"}
DPI_CHOICES = ["150 (보통)", "200 (권장)", "300 (고화질)", "600 (인쇄용)"]
DEFAULT_DPI_INDEX = 1

TESSERACT_CANDIDATES = [
    r"C:\Program Files\Tesseract-OCR\tesseract.exe",
    r"C:\Program Files (x86)\Tesseract-OCR\tesseract.exe",
    os.path.expandvars(r"%LOCALAPPDATA%\Programs\Tesseract-OCR\tesseract.exe"),
]


def app_base_dir():
    """리소스 기준 폴더. PyInstaller로 묶였을 땐 임시 추출 폴더."""
    if getattr(sys, "frozen", False):
        return Path(sys._MEIPASS)
    return Path(__file__).parent


def find_tesseract():
    """Tesseract 실행 파일 경로를 찾는다. 번들 우선, 없으면 None."""
    bundled = app_base_dir() / "vendor" / "tesseract" / "tesseract.exe"
    if bundled.is_file():
        return str(bundled)
    exe = shutil.which("tesseract")
    if exe:
        return exe
    for cand in TESSERACT_CANDIDATES:
        if os.path.isfile(cand):
            return cand
    return None


# ---------------------------------------------------------------- 핵심 로직

def parse_page_range(text, total_pages):
    """'1-3,5,8' → 0-based 페이지 인덱스 리스트. 빈 문자열/'전체'면 모든 페이지."""
    text = text.strip()
    if not text or text in ("전체", "all", "ALL", "*"):
        return list(range(total_pages))
    pages = []
    for part in text.split(","):
        part = part.strip()
        if not part:
            continue
        if "-" in part:
            a, _, b = part.partition("-")
            start, end = int(a), int(b)
            if start > end:
                start, end = end, start
            pages.extend(range(start - 1, end))
        else:
            pages.append(int(part) - 1)
    # 중복 제거하되 순서 유지, 범위 검증
    seen = set()
    result = []
    for p in pages:
        if p < 0 or p >= total_pages:
            raise ValueError(f"{p + 1}페이지는 없습니다 (총 {total_pages}페이지).")
        if p not in seen:
            seen.add(p)
            result.append(p)
    return result


def make_output_dir(src_path):
    """원본 옆에 '파일명_output' 폴더 생성."""
    src = Path(src_path)
    out = src.parent / f"{src.stem}_output"
    out.mkdir(exist_ok=True)
    return out


def pdf_to_png(pdf_path, pages, dpi, progress=None):
    """PDF 페이지들을 PNG로 저장. 저장된 파일 목록 반환."""
    out_dir = make_output_dir(pdf_path)
    stem = Path(pdf_path).stem
    saved = []
    with fitz.open(pdf_path) as doc:
        zoom = dpi / 72
        mat = fitz.Matrix(zoom, zoom)
        for i, pno in enumerate(pages):
            pix = doc[pno].get_pixmap(matrix=mat)
            out_file = out_dir / f"{stem}_p{pno + 1:03d}.png"
            pix.save(str(out_file))
            saved.append(out_file)
            if progress:
                progress(i + 1, len(pages))
    return saved, out_dir


def pdf_extract_pages(pdf_path, pages, progress=None):
    """선택한 페이지만으로 새 PDF 생성."""
    out_dir = make_output_dir(pdf_path)
    stem = Path(pdf_path).stem
    out_file = out_dir / f"{stem}_추출.pdf"
    with fitz.open(pdf_path) as src:
        new = fitz.open()
        for i, pno in enumerate(pages):
            new.insert_pdf(src, from_page=pno, to_page=pno)
            if progress:
                progress(i + 1, len(pages))
        new.save(str(out_file))
        new.close()
    return [out_file], out_dir


def ocr_image(img, tess, ocr_lang="kor+eng"):
    """PIL 이미지 한 장을 OCR. psm 3(자동 레이아웃)과 psm 6(단일 블록)을
    모두 시도해 실제 글자(문자·숫자)를 더 많이 읽은 쪽을 채택 (한글 인식률 개선)."""
    import pytesseract
    pytesseract.pytesseract.tesseract_cmd = tess
    candidates = []
    for psm in ("3", "6"):
        t = pytesseract.image_to_string(
            img, lang=ocr_lang, config=f"--psm {psm}").strip()
        candidates.append(t)
    return max(candidates, key=lambda t: sum(1 for c in t if c.isalnum()))


def pdf_to_text(pdf_path, pages, progress=None, ocr_lang="kor+eng"):
    """텍스트 추출. 텍스트 레이어가 없는 페이지는 자동으로 OCR.
    반환: (저장 파일 목록, 출력 폴더, OCR 사용한 페이지 수)"""
    out_dir = make_output_dir(pdf_path)
    stem = Path(pdf_path).stem
    out_file = out_dir / f"{stem}_텍스트.txt"

    tess = find_tesseract()
    ocr_used = 0
    chunks = []

    with fitz.open(pdf_path) as doc:
        for i, pno in enumerate(pages):
            page = doc[pno]
            text = page.get_text().strip()
            if not text:  # 텍스트 레이어 없음 → OCR 시도
                if tess:
                    from PIL import Image
                    import io
                    pix = page.get_pixmap(matrix=fitz.Matrix(300 / 72, 300 / 72))
                    img = Image.open(io.BytesIO(pix.tobytes("png")))
                    text = ocr_image(img, tess, ocr_lang)
                    ocr_used += 1
                else:
                    text = "[이미지 페이지 — Tesseract 미설치로 OCR 불가]"
            chunks.append(f"===== {pno + 1} 페이지 =====\n{text}\n")
            if progress:
                progress(i + 1, len(pages))

    out_file.write_text("\n".join(chunks), encoding="utf-8")
    return [out_file], out_dir, ocr_used


def images_to_text(image_paths, progress=None, ocr_lang="kor+eng"):
    """이미지(PNG/JPG 등) 여러 장을 OCR해서 텍스트 파일 하나로 저장.
    반환: (저장 파일 목록, 출력 폴더, OCR 사용한 이미지 수)"""
    tess = find_tesseract()
    if not tess:
        raise RuntimeError("이미지 OCR에는 Tesseract가 필요합니다 (README 참고).")

    from PIL import Image
    first = Path(image_paths[0])
    out_dir = make_output_dir(first)
    out_file = out_dir / f"{first.stem}_텍스트.txt"

    chunks = []
    for i, p in enumerate(image_paths):
        img = Image.open(p)
        # 저해상도 이미지는 OCR 정확도를 위해 2배 확대
        if min(img.size) < 1000:
            img = img.resize((img.width * 2, img.height * 2), Image.LANCZOS)
        text = ocr_image(img, tess, ocr_lang)
        header = f"===== {Path(p).name} =====" if len(image_paths) > 1 else ""
        chunks.append(f"{header}\n{text}\n".lstrip())
        if progress:
            progress(i + 1, len(image_paths))

    out_file.write_text("\n".join(chunks), encoding="utf-8")
    return [out_file], out_dir, len(image_paths)


def images_to_pdf(image_paths, progress=None):
    """이미지 여러 장 → PDF 한 개 (무손실)."""
    first = Path(image_paths[0])
    out_dir = make_output_dir(first)
    out_file = out_dir / f"{first.stem}_합침.pdf" if len(image_paths) > 1 \
        else out_dir / f"{first.stem}.pdf"

    # img2pdf는 알파 채널을 지원 안 하므로 RGBA는 흰 배경으로 변환
    from PIL import Image
    import io
    converted = []
    for i, p in enumerate(image_paths):
        img = Image.open(p)
        if img.mode in ("RGBA", "LA", "P"):
            img = img.convert("RGBA")
            bg = Image.new("RGB", img.size, (255, 255, 255))
            bg.paste(img, mask=img.split()[-1])
            buf = io.BytesIO()
            bg.save(buf, format="PNG")
            converted.append(buf.getvalue())
        else:
            converted.append(str(p))
        if progress:
            progress(i + 1, len(image_paths))

    with open(out_file, "wb") as f:
        f.write(img2pdf.convert(converted))
    return [out_file], out_dir


# ---------------------------------------------------------------- GUI

class App:
    def __init__(self, root):
        self.root = root
        self.files = []       # 선택된 파일들 (Path)
        self.total_pages = 0  # 첫 PDF의 페이지 수
        self.busy = False
        self.last_out_dir = None

        root.title("PDF 도구 상자")
        root.geometry("560x520")
        root.minsize(520, 480)

        style = ttk.Style()
        try:
            style.theme_use("vista")
        except tk.TclError:
            pass

        pad = {"padx": 14, "pady": 6}

        # --- 드롭 영역
        self.drop = tk.Label(
            root,
            text="\n여기로 PDF / 이미지 파일을 끌어다 놓으세요\n\n(또는 클릭해서 파일 선택)\n",
            relief="groove", bd=2, bg="#f2f6fb", fg="#345",
            font=("맑은 고딕", 11),
            cursor="hand2",
        )
        self.drop.pack(fill="x", **pad)
        self.drop.bind("<Button-1>", lambda e: self.pick_files())
        if HAS_DND:
            self.drop.drop_target_register(DND_FILES)
            self.drop.dnd_bind("<<Drop>>", self.on_drop)

        # --- 선택된 파일 표시
        self.file_label = tk.Label(root, text="선택된 파일 없음",
                                   anchor="w", fg="#666", font=("맑은 고딕", 9))
        self.file_label.pack(fill="x", padx=16)

        # --- 페이지 범위 + DPI
        opt = ttk.Frame(root)
        opt.pack(fill="x", **pad)
        ttk.Label(opt, text="페이지:").pack(side="left")
        self.page_var = tk.StringVar(value="전체")
        page_entry = ttk.Entry(opt, textvariable=self.page_var, width=18)
        page_entry.pack(side="left", padx=(4, 2))
        ttk.Label(opt, text="예) 1-3,5,8", foreground="#999").pack(side="left")

        ttk.Label(opt, text="   화질:").pack(side="left")
        self.dpi_var = tk.StringVar(value=DPI_CHOICES[DEFAULT_DPI_INDEX])
        dpi_box = ttk.Combobox(opt, textvariable=self.dpi_var,
                               values=DPI_CHOICES, width=12, state="readonly")
        dpi_box.pack(side="left", padx=4)

        # --- 기능 버튼
        btns = ttk.Frame(root)
        btns.pack(fill="x", **pad)
        for col in range(3):
            btns.columnconfigure(col, weight=1)

        self.btn_png = ttk.Button(btns, text="PNG로 변환",
                                  command=lambda: self.run_task("png"))
        self.btn_pdf = ttk.Button(btns, text="PDF로 추출",
                                  command=lambda: self.run_task("extract"))
        self.btn_txt = ttk.Button(btns, text="텍스트 / OCR",
                                  command=lambda: self.run_task("text"))
        self.btn_png.grid(row=0, column=0, sticky="ew", padx=3, ipady=8)
        self.btn_pdf.grid(row=0, column=1, sticky="ew", padx=3, ipady=8)
        self.btn_txt.grid(row=0, column=2, sticky="ew", padx=3, ipady=8)

        self.btn_merge = ttk.Button(btns, text="이미지들을 PDF로 합치기",
                                    command=lambda: self.run_task("merge"))
        self.btn_merge.grid(row=1, column=0, columnspan=3,
                            sticky="ew", padx=3, pady=(6, 0), ipady=8)

        # --- 진행 바
        self.prog = ttk.Progressbar(root, mode="determinate")
        self.prog.pack(fill="x", padx=16, pady=(4, 0))

        # --- 상태 표시줄
        status = ttk.Frame(root)
        status.pack(fill="x", side="bottom", padx=14, pady=10)
        self.status_label = tk.Label(status, text="준비됨", anchor="w",
                                     fg="#333", font=("맑은 고딕", 9))
        self.status_label.pack(side="left", fill="x", expand=True)
        self.btn_open = ttk.Button(status, text="결과 폴더 열기",
                                   command=self.open_out_dir, state="disabled")
        self.btn_open.pack(side="right")

        # --- OCR 안내
        if not find_tesseract():
            tip = tk.Label(root, text="ℹ 스캔본 OCR을 쓰려면 Tesseract 설치가 필요합니다 (README 참고)",
                           fg="#b60", font=("맑은 고딕", 8), anchor="w")
            tip.pack(fill="x", side="bottom", padx=16)

        if not HAS_DND:
            self.set_status("tkinterdnd2 미설치 — 드래그앤드롭 대신 클릭으로 파일을 선택하세요.")

    # ------------------------------------------------ 파일 선택

    def on_drop(self, event):
        paths = self.root.tk.splitlist(event.data)
        self.set_files([Path(p) for p in paths])

    def pick_files(self):
        paths = filedialog.askopenfilenames(
            title="파일 선택",
            filetypes=[("PDF / 이미지", "*.pdf;*.png;*.jpg;*.jpeg;*.bmp;*.tif;*.tiff;*.webp"),
                       ("모든 파일", "*.*")])
        if paths:
            self.set_files([Path(p) for p in paths])

    def set_files(self, paths):
        valid = [p for p in paths
                 if p.suffix.lower() == ".pdf" or p.suffix.lower() in IMAGE_EXTS]
        if not valid:
            messagebox.showwarning("파일 형식", "PDF 또는 이미지 파일만 지원합니다.")
            return
        self.files = valid
        pdfs = [p for p in valid if p.suffix.lower() == ".pdf"]
        imgs = [p for p in valid if p.suffix.lower() in IMAGE_EXTS]

        desc = []
        if pdfs:
            try:
                with fitz.open(pdfs[0]) as doc:
                    self.total_pages = len(doc)
                desc.append(f"{pdfs[0].name} (총 {self.total_pages}페이지)")
                if len(pdfs) > 1:
                    desc.append(f"외 PDF {len(pdfs) - 1}개")
            except Exception as e:
                messagebox.showerror("오류", f"PDF를 열 수 없습니다:\n{e}")
                return
        if imgs:
            desc.append(f"이미지 {len(imgs)}장")
        self.file_label.config(text="선택됨:  " + ", ".join(desc), fg="#1a4d8f")
        self.set_status("파일 준비 완료 — 원하는 작업 버튼을 누르세요.")

    # ------------------------------------------------ 작업 실행

    def run_task(self, kind):
        if self.busy:
            return
        pdfs = [p for p in self.files if p.suffix.lower() == ".pdf"]
        imgs = [p for p in self.files if p.suffix.lower() in IMAGE_EXTS]

        if kind == "merge":
            if not imgs:
                messagebox.showinfo("안내", "먼저 이미지 파일(PNG/JPG 등)을 선택하세요.")
                return
        elif kind == "text":
            if not pdfs and not imgs:
                messagebox.showinfo("안내", "먼저 PDF 또는 이미지 파일을 선택하세요.")
                return
            if imgs and not find_tesseract():
                messagebox.showwarning(
                    "OCR 불가",
                    "이미지 OCR에는 Tesseract가 필요합니다.\nREADME의 설치 안내를 참고하세요.")
                return
        else:
            if not pdfs:
                messagebox.showinfo("안내", "먼저 PDF 파일을 선택하세요.")
                return

        threading.Thread(target=self._work, args=(kind, pdfs, imgs),
                         daemon=True).start()

    def _work(self, kind, pdfs, imgs):
        self.busy = True
        self._set_buttons("disabled")
        try:
            dpi = int(self.dpi_var.get().split()[0])
            all_saved = []
            out_dir = None
            ocr_total = 0

            if kind == "merge":
                self.set_status(f"이미지 {len(imgs)}장을 PDF로 합치는 중…")
                saved, out_dir = images_to_pdf(imgs, self.on_progress)
                all_saved += saved
            else:
                for pdf in pdfs:
                    with fitz.open(pdf) as doc:
                        total = len(doc)
                    pages = parse_page_range(self.page_var.get(), total)
                    label = f"{pdf.name} ({len(pages)}페이지)"
                    if kind == "png":
                        self.set_status(f"PNG 변환 중… {label}")
                        saved, out_dir = pdf_to_png(pdf, pages, dpi, self.on_progress)
                    elif kind == "extract":
                        self.set_status(f"PDF 추출 중… {label}")
                        saved, out_dir = pdf_extract_pages(pdf, pages, self.on_progress)
                    elif kind == "text":
                        self.set_status(f"텍스트 추출 중… {label}")
                        saved, out_dir, ocr_used = pdf_to_text(pdf, pages, self.on_progress)
                        ocr_total += ocr_used
                    all_saved += saved
                if kind == "text" and imgs:
                    self.set_status(f"이미지 {len(imgs)}장 OCR 중…")
                    saved, out_dir, ocr_used = images_to_text(imgs, self.on_progress)
                    ocr_total += ocr_used
                    all_saved += saved

            self.last_out_dir = out_dir
            msg = f"완료! 파일 {len(all_saved)}개 저장됨"
            if kind == "text" and ocr_total:
                msg += f" (OCR 사용: {ocr_total}페이지)"
            self.set_status(msg)
            self.root.after(0, lambda: self.btn_open.config(state="normal"))
            self.root.after(0, self.open_out_dir)

        except ValueError as e:
            self.set_status("페이지 범위 오류")
            self.root.after(0, lambda: messagebox.showerror("페이지 범위 오류", str(e)))
        except Exception:
            err = traceback.format_exc()
            self.set_status("오류 발생")
            self.root.after(0, lambda: messagebox.showerror("오류", err[-1500:]))
        finally:
            self.busy = False
            self._set_buttons("normal")
            self.root.after(0, lambda: self.prog.config(value=0))

    # ------------------------------------------------ 보조

    def on_progress(self, done, total):
        self.root.after(0, lambda: self.prog.config(maximum=total, value=done))

    def set_status(self, text):
        self.root.after(0, lambda: self.status_label.config(text=text))

    def _set_buttons(self, state):
        def apply():
            for b in (self.btn_png, self.btn_pdf, self.btn_txt, self.btn_merge):
                b.config(state=state)
        self.root.after(0, apply)

    def open_out_dir(self):
        if self.last_out_dir and Path(self.last_out_dir).is_dir():
            subprocess.Popen(["explorer", str(self.last_out_dir)])


def main():
    root = TkinterDnD.Tk() if HAS_DND else tk.Tk()
    App(root)
    root.mainloop()


if __name__ == "__main__":
    main()
