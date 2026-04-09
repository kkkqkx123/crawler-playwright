# py-crawler Project Context

## Project Overview

This is a Python crawler project based on **Playwright**, **lxml**, and **httpx**, primarily used for automating login processes, CAPTCHA recognition, and data extraction tasks across various websites. The project consists of multiple submodules, each targeting different types of CAPTCHAs and websites for automation.

## Tech Stack

- **Python 3.14+** (managed via `uv`)
- **Playwright** – Browser automation
- **httpx** – HTTP client
- **lxml** – HTML/XML parsing
- **OpenCV + NumPy** – Image processing (slider CAPTCHA recognition)
- **Pillow** – Image processing
- **OpenAI API** – Invoking Qwen-VL multimodal model for OCR and CAPTCHA recognition
- **python-dotenv** – Environment variable management

## Project Structure

```text
py-playwright/
├── character-recognition/     # Scripts for character recognition
│   └── crawler-bilibili2.py   # Bilibili CAPTCHA auto-login (Selenium + Qwen-VL)
├── simple-captcha/            # Simple CAPTCHA recognition
│   └── main.py                # OCR recognition of simple graphical CAPTCHAs using httpx + Qwen-VL
├── slider-captcha/            # Slider CAPTCHA handling
│   ├── main.py                # Douban slider CAPTCHA auto-login (Playwright + OpenCV)
│   ├── dangdang_slide.py      # Dangdang slider CAPTCHA handling
│   ├── jd_slide.py            # JD.com slider CAPTCHA handling
│   ├── workflow.md            # Login page element selector documentation
│   └── ref/                   # Reference materials
├── zip/                       # Compressed files directory (ignored by .gitignore)
├── pyproject.toml             # Project configuration (uv dependency management)
├── .env.example               # Environment variable example
├── environment.md             # Environment setup instructions
└── AGENTS.md                  # Project documentation
```

## Submodule Descriptions

### 1. simple-captcha
- **Functionality**: Use httpx and the Qwen-VL model to recognize simple graphical CAPTCHAs.
- **Target Website**: spiderbuf.cn
- **Workflow**:
  1. Access the target page and extract the CAPTCHA image URL
  2. Download the image and convert it to base64
  3. Invoke the Qwen3-VL model for OCR recognition
  4. Submit the login form

### 2. slider-captcha
- **Functionality**: Automatically solve slider CAPTCHAs using Playwright and OpenCV.
- **Target Websites**: Douban, Dangdang, JD.com
- **Core Classes**:
  - `FrameManager`: Manages multi-level iframes
  - `TencentSliderCaptcha`: Handles Tencent slider CAPTCHAs
- **Workflow**:
  1. Use OpenCV edge detection or template matching to identify the gap position
  2. Generate human-like drag trajectories
  3. Simulate mouse drag using Playwright

### 3. character-recognition
- **Functionality**: Recognize character-click CAPTCHAs (e.g., click specific Chinese characters).
- **Target Website**: Bilibili
- **Workflow**:
  1. Use Qwen-VL to identify required characters in the prompt
  2. The VL model returns center coordinates for each character
  3. Perform secondary validation on coordinates and simulate clicks

## Environment Setup

### Dependency Management
The project uses `uv` as the package manager:

```bash
# Activate virtual environment
.venv/Scripts/activate
```

## How to Run

```bash
# Activate virtual environment
.venv/Scripts/activate

# Run simple CAPTCHA recognition
cd simple-captcha && python main.py

# Run slider CAPTCHA
cd slider-captcha && python main.py

# Run Bilibili CAPTCHA recognition
cd character-recognition && python crawler-bilibili2.py
```
