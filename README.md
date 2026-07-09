# PDF 도구 상자 (PDF Toolkit)

PDF ↔ 이미지 변환, 페이지 추출, OCR 텍스트 추출을 하나의 창에서 처리하는 윈도우용 데스크톱 앱입니다.
**설치 없이 exe 하나로 실행**되며, 한글 OCR 엔진(Tesseract)까지 내장되어 있습니다.

## 기능

| 기능 | 설명 |
|------|------|
| 🖼 **PDF → PNG** | 원하는 페이지를 PNG 이미지로 변환 (150/200/300/600 DPI) |
| 📄 **페이지 추출** | `1-3,5,8` 형식으로 페이지를 골라 새 PDF 생성 |
| 🔍 **텍스트 / OCR** | PDF는 텍스트 레이어가 있으면 즉시 추출, 스캔본이면 자동 OCR. PNG/JPG 이미지도 바로 OCR (한글+영어) |
| 📚 **이미지 → PDF** | PNG/JPG 여러 장을 무손실로 PDF 한 개로 병합 |

- 파일을 창에 **끌어다 놓거나** 클릭해서 선택
- 결과물은 원본 옆 `파일명_output` 폴더에 저장되고 완료 시 자동으로 열림

## 다운로드

👉 [Releases](../../releases)에서 `PDF도구상자.exe`를 받아 더블클릭하면 끝.
설치, 파이썬, Tesseract 전부 필요 없습니다.

> ⚠️ 처음 실행 시 내장 파일 압축 해제 때문에 몇 초 걸릴 수 있습니다.
> Windows Defender SmartScreen 경고가 뜨면 "추가 정보 → 실행"을 누르세요 (서명되지 않은 exe라 뜨는 정상 경고입니다).

## 소스로 실행

```bash
pip install -r requirements.txt
python app.py
```

스캔본 OCR을 쓰려면 [Tesseract](https://github.com/UB-Mannheim/tesseract/wiki)를 설치하세요 (Korean 언어팩 체크).
`vendor/tesseract/` 폴더에 포터블 복사본이 있으면 그것을 우선 사용합니다.

## exe 직접 빌드

1. Tesseract 설치 (위 링크, Korean 포함)
2. `build.bat` 실행 → `dist/PDF도구상자.exe` 생성

## 기술 스택

- [PyMuPDF](https://github.com/pymupdf/PyMuPDF) — PDF 렌더링/추출
- [img2pdf](https://gitlab.mister-muffin.de/josch/img2pdf) — 무손실 이미지→PDF
- [Tesseract OCR](https://github.com/tesseract-ocr/tesseract) — 한글/영어 OCR (Apache-2.0, 바이너리 동봉)
- Tkinter + [tkinterdnd2](https://github.com/pmgagne/tkinterdnd2) — GUI / 드래그앤드롭

## 라이선스

이 프로젝트 코드는 [MIT License](LICENSE)를 따릅니다.
동봉된 Tesseract OCR 바이너리는 [Apache License 2.0](https://github.com/tesseract-ocr/tesseract/blob/main/LICENSE)을 따릅니다.
