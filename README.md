# 🤖 Survey Helper Bot for Windows 11

A smart, human-like survey assistant that uses AI to **read**, **understand**, and **auto-type** answers into surveys – all with just mouse clicks and keyboard shortcuts!

Built for speed, stealth, and human realism. Powered by **Google Gemini** + **PyQt6** + **pynput** + **screenshot OCR**.

Use LEFT ALT + CLICK on any browser window to take a screenshot and send to the AI for it to solve.

---

## 🧠 Features

- ✂️ **Snipping Tool**: ALT+SHIFT → Drag to select a region → AI answers it!
- 🖱️ **Window Capture**: ALT + Left Click → Capture entire app window under cursor
- 🤖 **Auto-Typing**: Press ` (Backtick) → Auto-types the AI answer like a real person
- 🛑 **Abort Anytime**: Press ALT again to cancel loading or typing
- 🧠 **Context-Aware**: Remembers previous 25 answers to avoid repetition
- 🛠️ **Human-Like Typing**: Mistakes, pauses, natural typing speed

---

## ⚙️ Requirements

🪟 **Windows Only**

### 🧪 Python Packages

Install them with:

```bash
pip install -r requirements.txt
```

Or manually:

```bash
pip install python-dotenv google-generativeai pynput pillow mss pywin32 PyQt6
```

---

## 📁 Setup

### 1. Clone the Repo

```bash
git clone https://github.com/yourusername/survey-helper-bot.git
cd survey-helper-bot
```

### 2. Create `.env` File

Inside `.env`, add your [Google Gemini API Key](https://aistudio.google.com/app/apikey):

```env
GEMINI_API_KEY=your_api_key_here
```

(You can add multiple keys separated by commas)

### 3. Create `system.txt`

This file defines your AI's personality and prompt rules.

Example:

```
You are a helpful human survey participant who answers casually and naturally. Avoid repetition. Be concise unless the question needs elaboration.
```

---

## 🚀 Running the Bot

```bash
python py.py
```

Once running:

```
=============================================
  Survey Helper is running.
---------------------------------------------
  🖱️ ALT + Left Click: capture window under cursor.
  ✂️ ALT + SHIFT: enter snipping mode, then drag to select.
  ⌨️ ` (Backtick): Auto-type the text from the tooltip.
     (Typing will begin immediately)
  ❌ Press ALT during loading to abort request.
  ✋ Press ALT during typing to abort typing.
  ❎ ESC: cancel snipping mode.
  🔚 CTRL+C in this terminal to exit.
=============================================
```

---

## 🧪 How It Works

1. **Capture**: Snips or screenshots the UI element under cursor
2. **AI Request**: Sends image + context to Gemini API
3. **Tooltip**: Displays answer near your cursor
4. **Auto-Type**: Simulates human typing at ~170 WPM with random delays & errors

---

## 🕵️‍♂️ Notes

- Designed to be stealthy: no window captures unless you trigger it
- Will NOT run on non-Windows systems
- Requires `system.txt` and `.env` in the same directory
- Press `CTRL+C` to exit cleanly

---

## 🧠 Powered By

- 🤖 [Google Gemini](https://aistudio.google.com)
- 🧱 PyQt6 GUI
- 🖱️ `pynput` Keyboard & Mouse hooks
- 📸 `mss` for fast screenshots
- 🖼️ `Pillow` for image handling
- 💡 Context memory with answer history

---

## 🛡️ Disclaimer

This tool is for **educational purposes** only. Do not use it to violate terms of service or academic integrity policies.

---

## 💬 Questions?

Open an issue, or [email me](mailto:your@email.com)!

---

## ⭐️ Star if you like it!
