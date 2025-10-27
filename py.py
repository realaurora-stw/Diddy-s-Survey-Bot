#!/usr/bin/env python3
# Survey Helper with Low-Level Keyboard Hook and Humanized Auto-Typer

import sys
import os
import threading
import io
import time
import random
from collections import deque
import ctypes
import ctypes.wintypes

# --- Third-party libraries ---
from dotenv import load_dotenv
import google.generativeai as genai
from PIL import Image
from pynput import mouse, keyboard

# --- Platform Check and Windows API Setup ---
if sys.platform != "win32":
    print("❌ FATAL ERROR: This script requires Windows to run.")
    sys.exit(1)

try:
    import mss
except ImportError:
    print("❌ FATAL ERROR: The 'mss' library is required for this script.")
    print("Please install it by running: pip install mss")
    sys.exit(1)

try:
    import win32gui
except ImportError:
    print("❌ FATAL ERROR: The 'pywin32' library is required for this script.")
    print("Please install it by running: pip install pywin32")
    sys.exit(1)

from PyQt6.QtWidgets import QApplication, QWidget, QLabel, QVBoxLayout
from PyQt6.QtGui import QColor, QPainter, QPen, QBrush, QGuiApplication
from PyQt6.QtCore import (
    Qt, QTimer, QPoint, QRect, QPropertyAnimation, QEasingCurve, pyqtProperty,
    pyqtSignal, pyqtSlot, QObject
)

# --- Windows API ctypes Definitions ---
user32 = ctypes.windll.user32
kernel32 = ctypes.windll.kernel32

# Structures and types for the LOW-LEVEL HOOK
LRESULT = ctypes.c_ssize_t
ULONG_PTR = ctypes.c_ulonglong if ctypes.sizeof(ctypes.c_void_p) == 8 else ctypes.c_uint

class KBDLLHOOKSTRUCT(ctypes.Structure):
    _fields_ = [
        ("vkCode",      ctypes.wintypes.DWORD),
        ("scanCode",    ctypes.wintypes.DWORD),
        ("flags",       ctypes.wintypes.DWORD),
        ("time",        ctypes.wintypes.DWORD),
        ("dwExtraInfo", ULONG_PTR),
    ]

# Constants for the HOOK
WH_KEYBOARD_LL = 13
WM_KEYDOWN = 0x0100
WM_KEYUP = 0x0101
WM_SYSKEYDOWN = 0x0104
WM_SYSKEYUP = 0x0105

# Virtual Key Codes
VK_SHIFT = 0x10
VK_LSHIFT, VK_RSHIFT = 0xA0, 0xA1
VK_LMENU, VK_RMENU, VK_MENU = 0xA4, 0xA5, 0x12  # Alt keys
VK_TAB = 0x09
VK_ESCAPE = 0x1B
VK_OEM_3 = 0xC0    # ` ~ (Backtick/Tilde on US keyboard)

# Hook prototypes
HOOKPROC = ctypes.WINFUNCTYPE(LRESULT, ctypes.c_int, ctypes.wintypes.WPARAM, ctypes.wintypes.LPARAM)
user32.SetWindowsHookExW.argtypes = [ctypes.c_int, HOOKPROC, ctypes.wintypes.HINSTANCE, ctypes.wintypes.DWORD]
user32.SetWindowsHookExW.restype = ctypes.c_void_p
user32.CallNextHookEx.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.wintypes.WPARAM, ctypes.wintypes.LPARAM]
user32.CallNextHookEx.restype = LRESULT
user32.UnhookWindowsHookEx.argtypes = [ctypes.c_void_p]
user32.UnhookWindowsHookEx.restype = ctypes.wintypes.BOOL

kernel32.GetModuleHandleW.restype = ctypes.wintypes.HMODULE
kernel32.GetModuleHandleW.argtypes = [ctypes.wintypes.LPCWSTR]

# Globals
hook_handle = None
_hook_proc_ref = None
pressed_keys = set()
pressed_lock = threading.Lock()
is_processing = False
snip_mode_active = False
alt_tab_cooldown_timer = None
abort_typing_flag = threading.Event()

# --- Configuration & Global State ---
print("Initializing script...")
load_dotenv()

try:
    with open("system.txt", "r", encoding='utf-8') as f:
        SYSTEM_PROMPT = f.read()
    print("✅ System prompt loaded successfully.")
except FileNotFoundError:
    print("❌ ERROR: 'system.txt' not found. Please create it in the same directory.")
    sys.exit(1)

API_KEY_STRING = os.getenv("GEMINI_API_KEY")
if not API_KEY_STRING:
    print("❌ ERROR: GEMINI_API_KEY not found in .env file.")
    sys.exit(1)

API_KEYS = [key.strip() for key in API_KEY_STRING.split(",") if key.strip()]
if not API_KEYS:
    print("❌ ERROR: No valid API keys found in GEMINI_API_KEY.")
    sys.exit(1)

print(f"📋 Loaded {len(API_KEYS)} API key(s).")
MODEL = None
current_api_index = 0
ai_response_history = deque(maxlen=25)

def configure_api():
    global MODEL, current_api_index
    if current_api_index >= len(API_KEYS):
        print("❌ ERROR: All API keys exhausted.")
        return False
    try:
        genai.configure(api_key=API_KEYS[current_api_index])
        MODEL = genai.GenerativeModel('gemini-flash-latest')
        print(f"✅ Gemini API configured successfully (using key {current_api_index + 1}/{len(API_KEYS)}).")
        return True
    except Exception as e:
        print(f"⚠️  API key {current_api_index + 1} failed: {e}")
        current_api_index += 1
        return configure_api()

if not configure_api():
    sys.exit(1)


# --- Auto-Typer Implementation (pynput) ---
keyboard_controller = keyboard.Controller()

def humanized_autotyper(text_to_type, base_wpm, finished_signal):
    abort_typing_flag.clear()
    print(f"\n🤖 Starting advanced auto-typer at ~{base_wpm} WPM...")
    print(f"  📝 Text to type: {text_to_type[:50]}..." if len(text_to_type) > 50 else f"  📝 Text to type: {text_to_type}")

    global is_processing
    is_processing = True

    WPM_FLUCTUATION = 25
    MISTAKE_PROBABILITY = 0.025
    
    qwerty_neighbors = {
        'a': 'qwsz', 'b': 'vghn', 'c': 'xdfv', 'd': 'serfcx', 'e': 'wsdfr', 'f': 'drtgvc',
        'g': 'ftyhbv', 'h': 'gyujnb', 'i': 'ujklo', 'j': 'huiknm', 'k': 'jiolm', 'l': 'kopm',
        'm': 'njk,', 'n': 'bhjm', 'o': 'iklp', 'p': 'ol', 'q': 'wa', 'r': 'edfgt', 's': 'awedxz',
        't': 'rfgyh', 'u': 'yhjki', 'v': 'cfgb', 'w': 'qasde', 'x': 'zsdc', 'y': 'tghju',
        'z': 'asx', '1': '2q', '2': '1qwa3', '3': '2we4', '4': '3er5', '5': '4rt6',
        '6': '5ty7', '7': '6yu8', '8': '7ui9', '9': '8io0', '0': '9op-'
    }

    print("  ⌨️  Typing now...")
    current_wpm = random.uniform(base_wpm - WPM_FLUCTUATION, base_wpm + WPM_FLUCTUATION)

    for i, char in enumerate(text_to_type):
        if abort_typing_flag.is_set():
            print("  - Typing aborted by user.")
            break

        if char.lower() in qwerty_neighbors and random.random() < MISTAKE_PROBABILITY:
            mistake = random.choice(qwerty_neighbors[char.lower()])
            keyboard_controller.press(mistake)
            keyboard_controller.release(mistake)
            time.sleep(random.uniform(0.09, 0.16))
            keyboard_controller.press(keyboard.Key.backspace)
            keyboard_controller.release(keyboard.Key.backspace)
            time.sleep(random.uniform(0.05, 0.1))

        if i % 10 == 0:
            current_wpm = random.uniform(base_wpm - WPM_FLUCTUATION, base_wpm + WPM_FLUCTUATION)
        
        chars_per_second = (current_wpm * 5) / 60.0
        base_delay = (1.0 / chars_per_second) * 1.3  # 30% slower
        delay = random.uniform(base_delay * 0.8, base_delay * 1.2)

        if char == ' ': delay *= 1.5
        elif char in ',;': delay *= 2.5
        elif char in '.!?\n': delay *= 4.0
        elif char.isupper() or not char.isalnum() and char not in ' \'': delay *= 1.8

        time.sleep(delay)

        if char == '\n':
            keyboard_controller.press(keyboard.Key.enter)
            keyboard_controller.release(keyboard.Key.enter)
        else:
            keyboard_controller.press(char)
            keyboard_controller.release(char)
            
    print(f"✅ Auto-typing complete (or aborted).")
    finished_signal.emit()

# --- PyQt Widgets and GUI ---
class FadingTooltip(QWidget):
    show_signal = pyqtSignal(str)
    answer_signal = pyqtSignal(str)
    typing_finished_signal = pyqtSignal()

    def __init__(self):
        super().__init__()
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint |
            Qt.WindowType.WindowStaysOnTopHint |
            Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.layout = QVBoxLayout(self)
        self.label = QLabel(self)
        self.label.setStyleSheet("color: white; font-size: 14px; padding: 10px; background-color: black; border-radius: 16px;")
        self.label.setWordWrap(True)
        self.layout.addWidget(self.label)
        self.layout.setContentsMargins(0, 0, 0, 0)

        self._opacity = 1.0
        self.fade_animation = QPropertyAnimation(self, b"windowOpacity")
        self.is_showing = False
        self.typing_thread = None
        
        self.is_aborted = False
        self.is_typing = False
        
        # MODIFICATION: Add timestamp for grace period logic
        self.show_timestamp = 0.0

        self.cursor_timer = QTimer(self)
        self.cursor_timer.timeout.connect(self.update_position)

        self.show_signal.connect(self._show_message_safe)
        self.answer_signal.connect(self.replace_loading_with_answer)
        self.typing_finished_signal.connect(self.fade_out)
        
    @pyqtProperty(float)
    def windowOpacity(self): return self._opacity
    @windowOpacity.setter
    def windowOpacity(self, opacity): self._opacity = opacity; self.setWindowOpacity(opacity)
    def paintEvent(self, event):
        painter = QPainter(self); painter.setRenderHint(QPainter.RenderHint.Antialiasing); painter.setBrush(QBrush(QColor(0, 0, 0, 255))); painter.setPen(QPen(Qt.PenStyle.NoPen)); painter.drawRoundedRect(self.rect(), 16.0, 16.0)
    def show_loading(self): self.show_signal.emit("...")
    def _show_message_safe(self, text):
        try:
            # MODIFICATION: Record the time when the tooltip is shown
            self.show_timestamp = time.time()
            
            self.fade_animation.stop();
            try: self.fade_animation.finished.disconnect()
            except TypeError: pass
            self.label.setText(text); self.adjustSize(); self.is_showing = True; self.update_position()
            if not self.isVisible(): self.show()
            if not self.cursor_timer.isActive(): self.cursor_timer.start(10)
            self.fade_animation.setDuration(300); self.fade_animation.setStartValue(0.0); self.fade_animation.setEndValue(1.0); self.fade_animation.setEasingCurve(QEasingCurve.Type.InOutQuad); self.fade_animation.start()
        except Exception as e: print(f"Error in _show_message_safe: {e}")

    def fade_out(self):
        if not self.is_showing: return
        try:
            self.is_typing = False
            self.cursor_timer.stop(); self.is_showing = False; self.fade_animation.stop(); self.fade_animation.setDuration(500); self.fade_animation.setStartValue(1.0); self.fade_animation.setEndValue(0.0); self.fade_animation.setEasingCurve(QEasingCurve.Type.InOutQuad)
            def on_finish():
                if self.isVisible(): self.hide()
                global is_processing; is_processing = False; print("\n✅ Ready for next input.")
            try: self.fade_animation.finished.disconnect()
            except TypeError: pass
            self.fade_animation.finished.connect(on_finish); self.fade_animation.start()
        except Exception as e:
            print(f"Error in fade_out: {e}"); global is_processing; is_processing = False

    def update_position(self):
        if self.is_showing:
            pos = mouse.Controller().position; cursor_pos = QPoint(pos[0], pos[1]); self.move(cursor_pos.x() - self.width() // 2, cursor_pos.y() - self.height() - 15)
    
    @pyqtSlot(str)
    def replace_loading_with_answer(self, answer_text):
        if self.is_aborted:
            print("  - AI response received, but request was aborted. Discarding.")
            return

        global is_processing
        try:
            self.fade_animation.stop();
            try: self.fade_animation.finished.disconnect()
            except TypeError: pass
            if not self.isVisible(): self.show()
            self.setWindowOpacity(1.0); self._opacity = 1.0; self.is_showing = True
            if not self.cursor_timer.isActive(): self.cursor_timer.start(10)
            self.label.setText(answer_text); self.adjustSize(); self.update_position()
            is_processing = False
            print(f"  - Tooltip ready. Press Alt to dismiss or ` to auto-type.")
        except Exception as e:
            print(f"Error in replace_loading_with_answer: {e}"); is_processing = False

    @pyqtSlot()
    def handle_alt_press(self):
        # MODIFICATION: Grace period logic to prevent instant-cancellation.
        # This check is only active during the "..." loading phase.
        if self.label.text() == "...":
            grace_period_seconds = 2.0
            elapsed = time.time() - self.show_timestamp
            if elapsed < grace_period_seconds:
                print(f"  - Alt pressed within loading grace period ({elapsed:.2f}s). Ignoring.")
                return

        # 1. Abort request during "..." loading phase (after grace period)
        if self.label.text() == "..." and is_processing:
            print("  - Alt pressed during AI request. Aborting.")
            self.is_aborted = True
            self.fade_out()
            return
        
        # 2. Abort active typing
        if self.is_typing:
            print("  - Alt pressed during typing. Sending abort signal.")
            abort_typing_flag.set()
            return

        # 3. Default: Dismiss a ready tooltip
        if self.is_showing and self.label.text() != "..." and not is_processing:
            print("  - Alt pressed while answer showing. Triggering fade out."); self.fade_out()

    @pyqtSlot()
    def start_autotyper(self):
        if self.is_showing and self.label.text() != "..." and not is_processing:
            text = self.label.text()
            self.is_typing = True
            self.typing_thread = threading.Thread(target=humanized_autotyper, args=(text, 170, self.typing_finished_signal), daemon=True)
            self.typing_thread.start()
        else:
            print("  - Ignoring auto-type request (tooltip not ready or already processing).")

class SnippingOverlay(QWidget):
    start_signal = pyqtSignal(); cancel_signal = pyqtSignal(); done_signal = pyqtSignal(object)
    def __init__(self):
        super().__init__(); self.setWindowFlags(Qt.WindowType.FramelessWindowHint|Qt.WindowType.WindowStaysOnTopHint|Qt.WindowType.Tool); self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True); self.setMouseTracking(True); self.setCursor(Qt.CursorShape.CrossCursor); self._opacity = 1.0; self.animation = QPropertyAnimation(self, b"windowOpacity"); self.animation.setEasingCurve(QEasingCurve.Type.InOutQuad); self.dragging = False; self.origin = QPoint(); self.current = QPoint(); self._pending_rect_global = None; self.start_signal.connect(self._start_on_gui); self.cancel_signal.connect(self._cancel_on_gui)
    def _virtual_geometry(self) -> QRect: return QGuiApplication.primaryScreen().virtualGeometry()
    @pyqtProperty(float)
    def windowOpacity(self): return self._opacity
    @windowOpacity.setter
    def windowOpacity(self, opacity): self._opacity = opacity; self.setWindowOpacity(opacity)
    def _start_on_gui(self):
        try:
            self.setGeometry(self._virtual_geometry()); self.setWindowOpacity(0.0); self.show(); self.raise_(); self.dragging = False; self.origin = QPoint(); self.current = QPoint(); self._pending_rect_global = None; self.animation.stop(); self.animation.setDuration(120); self.animation.setStartValue(0.0); self.animation.setEndValue(1.0); self.animation.start(); print("\n✂️  Snipping mode armed. Drag to select, ESC to cancel.")
        except Exception as e: print(f"Error starting overlay: {e}"); global snip_mode_active; snip_mode_active = False
    def _cancel_on_gui(self): self._fade_out(callback=None)
    def _fade_out(self, callback=None, duration=150):
        try:
            self.animation.stop(); self.animation.setDuration(duration); self.animation.setStartValue(self.windowOpacity); self.animation.setEndValue(0.0)
            def on_finish():
                self.hide(); self.dragging = False; global snip_mode_active; snip_mode_active = False
                if callable(callback): callback()
            try: self.animation.finished.disconnect()
            except TypeError: pass
            self.animation.finished.connect(on_finish); self.animation.start()
        except Exception as e: print(f"Error fading overlay: {e}"); self.hide(); global snip_mode_active; snip_mode_active = False;
    def paintEvent(self, event):
        painter = QPainter(self); painter.setRenderHint(QPainter.RenderHint.Antialiasing); painter.fillRect(self.rect(), QColor(32, 32, 32, 120))
        if self.dragging or (self.origin != self.current and not self.origin.isNull()):
            rect = QRect(self.origin, self.current).normalized();
            if rect.isValid(): painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_Clear); painter.fillRect(rect, Qt.GlobalColor.transparent); painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceOver); pen = QPen(QColor(255, 255, 255, 255), 2); painter.setPen(pen); painter.setBrush(Qt.BrushStyle.NoBrush); painter.drawRect(rect)
    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton: self.dragging = True; self.origin = event.pos(); self.current = event.pos(); self.update()
    def mouseMoveEvent(self, event):
        if self.dragging: self.current = event.pos(); self.update()
    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton and self.dragging:
            self.dragging = False; rect_local = QRect(self.origin, self.current).normalized()
            if rect_local.width() >= 3 and rect_local.height() >= 3:
                top_left_global = self.mapToGlobal(rect_local.topLeft()); self._pending_rect_global = QRect(top_left_global, rect_local.size())
                def fire_done():
                    if self._pending_rect_global is not None: self.done_signal.emit(self._pending_rect_global); self._pending_rect_global = None
                self._fade_out(callback=fire_done, duration=150)
            else: self._fade_out(callback=None, duration=120)

# --- Business Logic ---
def capture_window_at_cursor(x, y):
    try:
        hwnd = win32gui.WindowFromPoint((x, y));
        if not hwnd or not win32gui.IsWindowVisible(hwnd): return None
        left, top, right, bottom = win32gui.GetWindowRect(hwnd); width, height = right - left, bottom - top
        if width <= 0 or height <= 0: return None
        with mss.mss() as sct: return Image.frombytes('RGB', sct.grab({"top": top, "left": left, "width": width, "height": height}).size, sct.grab({"top": top, "left": left, "width": width, "height": height}).rgb)
    except Exception as e: print(f"  - ❌ ERROR during mss capture: {e}"); return None
def capture_region(rect_global: QRect):
    try:
        with mss.mss() as sct: return Image.frombytes('RGB', sct.grab({"left": rect_global.left(), "top": rect_global.top(), "width": rect_global.width(), "height": rect_global.height()}).size, sct.grab({"left": rect_global.left(), "top": rect_global.top(), "width": rect_global.width(), "height": rect_global.height()}).rgb)
    except Exception as e: print(f"  - ❌ ERROR during region capture: {e}"); return None
def call_gemini_with_image(pil_image: Image.Image) -> str:
    global MODEL, current_api_index; attempts = 0
    while attempts < len(API_KEYS):
        try:
            prompt_parts = [SYSTEM_PROMPT]
            if ai_response_history: prompt_parts.append(f"---\n**FOR YOUR REFERENCE ONLY**: Below are the last 25 answers you provided for this survey. This is to help you avoid repetition and maintain context. Answer like a real human being who have provided the following answers. Base your next answers based on your previous answers. Do not repeat these answers unless it is absolutely necessary for the current question.\n\n" + "\n".join(f"{i+1}. {ans}" for i, ans in enumerate(ai_response_history)) + "\n---")
            prompt_parts.append(pil_image); response = MODEL.generate_content(prompt_parts); ai_answer = (response.text or "").strip()
            if not ai_answer: ai_answer = "❌ Empty response from AI."
            else: ai_response_history.append(ai_answer)
            return ai_answer
        except Exception as e:
            attempts += 1; print(f"  - ❌ ERROR from API key {current_api_index + 1}: {e}")
            if attempts < len(API_KEYS): current_api_index = (current_api_index + 1) % len(API_KEYS); print(f"  - 🔄 Switching to API key {current_api_index + 1}..."); configure_api()
            else: return "❌ All API keys failed."
    return "❌ API Error: Unable to process request."

# --- Event Handlers (Slots) ---
def process_window_request(x, y):
    tooltip.is_aborted = False
    tooltip.show_loading(); screenshot = capture_window_at_cursor(x, y)
    if not screenshot: tooltip.answer_signal.emit("❌ Capture failed.")
    else: tooltip.answer_signal.emit(call_gemini_with_image(screenshot))
def process_region_request(rect_global: QRect):
    tooltip.is_aborted = False
    tooltip.show_loading(); screenshot = capture_region(rect_global)
    if not screenshot: tooltip.answer_signal.emit("❌ Capture failed.")
    else: tooltip.answer_signal.emit(call_gemini_with_image(screenshot))

# --- Hook Implementation ---
class GlobalEmitter(QObject):
    alt_pressed = pyqtSignal(); shift_pressed = pyqtSignal(); escape_pressed = pyqtSignal(); backtick_pressed = pyqtSignal()
    alt_released = pyqtSignal(); shift_released = pyqtSignal()
global_emitter = GlobalEmitter()

def _low_level_keyboard_proc(nCode, wParam, lParam):
    try:
        if nCode >= 0:
            k = ctypes.cast(lParam, ctypes.POINTER(KBDLLHOOKSTRUCT)).contents
            vk = int(k.vkCode)
            injected = (k.flags & 0x10) != 0

            if not injected:
                is_down = wParam in (WM_KEYDOWN, WM_SYSKEYDOWN)
                
                if vk in (VK_LMENU, VK_RMENU, VK_MENU): global_emitter.alt_pressed.emit() if is_down else global_emitter.alt_released.emit()
                elif vk in (VK_LSHIFT, VK_RSHIFT, VK_SHIFT): global_emitter.shift_pressed.emit() if is_down else global_emitter.shift_released.emit()
                elif vk == VK_ESCAPE and is_down: global_emitter.escape_pressed.emit()
                elif vk == VK_OEM_3 and is_down:
                    global_emitter.backtick_pressed.emit()
                    return 1 # Block the key from other apps

                with pressed_lock:
                    if is_down: pressed_keys.add(vk)
                    else: pressed_keys.discard(vk)

    except Exception as e:
        print(f"Error in hook: {e}")
    return user32.CallNextHookEx(hook_handle, nCode, wParam, lParam)

def install_keyboard_hook():
    global hook_handle, _hook_proc_ref
    _hook_proc_ref = HOOKPROC(_low_level_keyboard_proc)
    h_instance = kernel32.GetModuleHandleW(None)
    hook_handle = user32.SetWindowsHookExW(WH_KEYBOARD_LL, _hook_proc_ref, h_instance, 0)
    if not hook_handle:
        raise ctypes.WinError()
def uninstall_keyboard_hook():
    if hook_handle: user32.UnhookWindowsHookEx(hook_handle)

# --- Main Application Logic ---
class AppController(QObject):
    def __init__(self, tooltip_widget, snip_widget):
        super().__init__()
        self.tooltip = tooltip_widget
        self.snipping_overlay = snip_widget
        self.is_alt_pressed = False
        self.is_shift_pressed = False
        self.alt_function_disabled = False

    @pyqtSlot()
    def on_alt_pressed(self): self.is_alt_pressed = True; self.tooltip.handle_alt_press(); self.check_modifiers()
    @pyqtSlot()
    def on_alt_released(self): self.is_alt_pressed = False; self.check_modifiers()
    @pyqtSlot()
    def on_shift_pressed(self): self.is_shift_pressed = True; self.check_modifiers()
    @pyqtSlot()
    def on_shift_released(self): self.is_shift_pressed = False; self.check_modifiers()
    @pyqtSlot()
    def on_escape_pressed(self):
        if snip_mode_active: print("  - Snipping cancelled (ESC)."); self.snipping_overlay.cancel_signal.emit()

    def check_modifiers(self):
        with pressed_lock:
            is_tab_pressed = VK_TAB in pressed_keys
            if self.is_alt_pressed and is_tab_pressed:
                self.disable_alt_functions_temporarily()
                return
        if self.alt_function_disabled: return
        
        global snip_mode_active
        if self.is_alt_pressed and self.is_shift_pressed and not is_processing and not snip_mode_active:
            snip_mode_active = True
            self.snipping_overlay.start_signal.emit()

    def on_click(self, x, y, button, pressed):
        if snip_mode_active or self.alt_function_disabled: return
        global is_processing
        if self.is_alt_pressed and not self.is_shift_pressed and button == mouse.Button.left and pressed:
            if not is_processing:
                is_processing = True
                print("\n💡 ALT + Left Click detected! Starting window capture...")
                threading.Thread(target=process_window_request, args=(x, y), daemon=True).start()
            else: print("  - Ignoring click, a request is already in progress.")

    def disable_alt_functions_temporarily(self):
        global alt_tab_cooldown_timer
        if not self.alt_function_disabled:
            print("  - Alt+Tab detected. Alt functions disabled.")
            self.alt_function_disabled = True
            if alt_tab_cooldown_timer and alt_tab_cooldown_timer.is_alive(): alt_tab_cooldown_timer.cancel()
            alt_tab_cooldown_timer = threading.Timer(0.8, self.enable_alt_functions)
            alt_tab_cooldown_timer.start()
    
    def enable_alt_functions(self):
        self.alt_function_disabled = False
        print("  - Alt functions re-enabled after cooldown.")

if __name__ == "__main__":
    app = QApplication(sys.argv)
    tooltip = FadingTooltip()
    snipping_overlay = SnippingOverlay()
    controller = AppController(tooltip, snipping_overlay)

    global_emitter.alt_pressed.connect(controller.on_alt_pressed)
    global_emitter.alt_released.connect(controller.on_alt_released)
    global_emitter.shift_pressed.connect(controller.on_shift_pressed)
    global_emitter.shift_released.connect(controller.on_shift_released)
    global_emitter.escape_pressed.connect(controller.on_escape_pressed)
    global_emitter.backtick_pressed.connect(tooltip.start_autotyper)

    def on_snip_done(rect_global):
        global is_processing
        if not is_processing:
            is_processing = True
            print(f"\n📐 Snip selected: {rect_global.width()}x{rect_global.height()} at {rect_global.topLeft().x()},{rect_global.topLeft().y()}")
            threading.Thread(target=process_region_request, args=(rect_global,), daemon=True).start()
        else: print("  - Ignoring snip complete, a request is already in progress.")
    snipping_overlay.done_signal.connect(on_snip_done)
    
    mouse_listener = mouse.Listener(on_click=controller.on_click)
    
    try:
        install_keyboard_hook()
        mouse_listener.start()

        print("\n=============================================")
        print("  Survey Helper is running.")
        print("---------------------------------------------")
        print("  ALT + Left Click: capture window under cursor.")
        print("  ALT + SHIFT: enter snipping mode, then drag to select.")
        print("  ` (Backtick): Auto-type the text from the tooltip.")
        print("    (Typing will begin immediately)")
        print("  Press ALT while tooltip is visible to dismiss it.")
        print("  Press ALT while loading ('...') to abort the request.")
        print("  Press ALT while typing to abort the typing.")
        print("  ESC: cancel snipping mode.")
        print("  Press CTRL+C in this terminal to exit.")
        print("=============================================")

        sys.exit(app.exec())
        
    except KeyboardInterrupt:
        print("\nCTRL+C detected. Shutting down...")
    except ctypes.WinError as e:
        print(f"\n❌ FATAL ERROR: Could not install keyboard hook: {e}")
    finally:
        mouse_listener.stop()
        uninstall_keyboard_hook()
        print("Hooks removed. Exiting.")
        os._exit(0)