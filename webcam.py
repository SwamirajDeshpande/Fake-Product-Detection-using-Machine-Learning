import tkinter as tk
from tkinter import ttk
import cv2
from PIL import Image, ImageTk
import re
import threading
import requests
from urllib.parse import urlparse, parse_qs
import time

# ------------- Config -------------
TRUSTED_DOMAINS = {
    "amazon.in", "amazon.com", "amazon.co.uk", "amazon.de", "amazon.ca",
    "amazon.ae", "amazon.com.au", "amazon.it", "amazon.es", "amazon.fr",
    "flipkart.com", "itunes.apple.com"
}
URL_SHORTENERS = {"amzn.to", "bit.ly", "tinyurl.com", "t.co", "goo.gl", "ow.ly", "is.gd", "cutt.ly", "shorturl.at"}
SUSPICIOUS_WORDS = {"replica", "firstcopy", "first-copy", "copy", "counterfeit", "fake", "mirror", "clone", "grade a"}
HTTP_TIMEOUT = 2.0   # seconds
COOLDOWN_AFTER_DETECT_MS = 1200  # avoid re-scoring the same code too fast

# ------------- Helpers -------------

def domain_of(url: str) -> str:
    try:
        netloc = urlparse(url).netloc.lower()
        if netloc.startswith("www."):
            netloc = netloc[4:]
        return netloc
    except Exception:
        return ""

def is_trusted_domain(dom: str) -> bool:
    # exact match OR subdomain of trusted (e.g., m.amazon.in)
    return dom in TRUSTED_DOMAINS or any(dom.endswith("." + td) for td in TRUSTED_DOMAINS)

def extract_amazon_asin(url: str):
    # Common Amazon ASIN patterns
    pats = [
        r"/dp/([A-Z0-9]{10})",
        r"/gp/product/([A-Z0-9]{10})",
        r"/product/([A-Z0-9]{10})",
    ]
    for p in pats:
        m = re.search(p, url, re.IGNORECASE)
        if m:
            return m.group(1).upper()
    # sometimes ASIN appears in query
    q = parse_qs(urlparse(url).query)
    for k in ("asin", "ASIN"):
        if k in q and len(q[k]) >= 1 and re.fullmatch(r"[A-Z0-9]{10}", q[k][0], re.IGNORECASE):
            return q[k][0].upper()
    return None

def extract_flipkart_pid(url: str):
    # Flipkart often has pid=... in query
    q = parse_qs(urlparse(url).query)
    if "pid" in q and q["pid"]:
        return q["pid"][0]
    # Many product URLs contain /p/itm... path segments (not a strict PID, but a product handle)
    if re.search(r"/p/itm", url):
        return "itm-path"
    return None

def resolve_url_if_shortened(url: str) -> str:
    dom = domain_of(url)
    # Only try to resolve if a shortener; keep short timeouts
    if dom in URL_SHORTENERS:
        try:
            r = requests.head(url, allow_redirects=True, timeout=HTTP_TIMEOUT)
            final = r.url
            return final
        except Exception:
            # fallback to GET (some providers block HEAD)
            try:
                r = requests.get(url, allow_redirects=True, timeout=HTTP_TIMEOUT, stream=True)
                final = r.url
                r.close()
                return final
            except Exception:
                return url
    return url

def http_reachable(url: str) -> bool:
    try:
        r = requests.head(url, allow_redirects=True, timeout=HTTP_TIMEOUT)
        if 200 <= r.status_code < 400:
            return True
        # Some sites block HEAD; try a light GET
        r = requests.get(url, allow_redirects=True, timeout=HTTP_TIMEOUT, stream=True)
        ok = 200 <= r.status_code < 400
        r.close()
        return ok
    except Exception:
        return False

def score_url(url: str):
    """
    Returns (label:str, score:int, reasons:list[str])
    """
    original_url = url.strip()
    reasons = []
    score = 50

    if not (original_url.startswith("http://") or original_url.startswith("https://")):
        reasons.append("URL missing http/https scheme.")
        return "Likely FAKE ❌", max(0, score - 30), reasons

    # Resolve shortener if needed
    resolved = resolve_url_if_shortened(original_url)
    if resolved != original_url:
        reasons.append(f"Short link resolved to: {resolved}")

    dom = domain_of(resolved)
    if is_trusted_domain(dom):
        score += 20
        reasons.append(f"Trusted domain detected: {dom}")
    else:
        score -= 25
        reasons.append(f"Untrusted domain: {dom or 'N/A'}")

    # Suspicious wording in URL
    lower_url = resolved.lower()
    if any(w in lower_url for w in SUSPICIOUS_WORDS):
        score -= 30
        reasons.append("Suspicious keywords found in URL.")
    else:
        reasons.append("No suspicious keywords in URL.")

    # Platform-specific ID sanity
    asin = None
    pid = None
    if "amazon." in dom:
        asin = extract_amazon_asin(resolved)
        if asin:
            score += 15
            reasons.append(f"Amazon ASIN found: {asin}")
        else:
            score -= 8
            reasons.append("No valid Amazon ASIN pattern found.")
    elif "flipkart." in dom:
        pid = extract_flipkart_pid(resolved)
        if pid:
            score += 12
            reasons.append("Flipkart product identifier pattern detected.")
        else:
            score -= 6
            reasons.append("No Flipkart product identifier found.")

    # Basic reachability
    reachable = http_reachable(resolved)
    if reachable:
        score += 10
        reasons.append("URL is reachable (HTTP 2xx/3xx).")
    else:
        score -= 10
        reasons.append("URL not reachable (blocked/404/timeout).")

    # Clamp and label
    score = max(0, min(100, score))
    if score >= 80:
        label = "Likely REAL ✅"
    elif score <= 40:
        label = "Likely FAKE ❌"
    else:
        label = "Uncertain ⚠️"

    return label, score, reasons, resolved

# ------------- Tkinter + Webcam -------------

class QRAuthApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Product QR Detector (Amazon/Flipkart)")
        self.root.geometry("900x640")
        self.root.configure(bg="#f7f7f7")

        title = tk.Label(root, text="📷 Product QR Detector", font=("Segoe UI", 18, "bold"), bg="#f7f7f7")
        title.pack(pady=8)

        self.video_lbl = tk.Label(root, bg="#000000", width=800, height=450)
        self.video_lbl.pack(pady=6)

        info_frame = tk.Frame(root, bg="#f7f7f7")
        info_frame.pack(fill="x", padx=16, pady=6)

        self.last_qr_var = tk.StringVar(value="Last QR: (waiting…)")
        self.pred_var = tk.StringVar(value="Prediction: —")
        self.score_var = tk.StringVar(value="Score: —")

        tk.Label(info_frame, textvariable=self.last_qr_var, font=("Segoe UI", 10), bg="#f7f7f7", anchor="w").grid(row=0, column=0, sticky="w")
        tk.Label(info_frame, textvariable=self.pred_var, font=("Segoe UI", 12, "bold"), bg="#f7f7f7", anchor="w").grid(row=1, column=0, sticky="w", pady=(4,0))
        tk.Label(info_frame, textvariable=self.score_var, font=("Segoe UI", 10), bg="#f7f7f7", anchor="w").grid(row=2, column=0, sticky="w")

        self.reason_lbl = tk.Label(root, text="Reasons:\n—", justify="left", anchor="w", bg="#ffffff",
                                   font=("Segoe UI", 10), bd=1, relief="solid")
        self.reason_lbl.pack(fill="both", padx=16, pady=8)

        ctrl = tk.Frame(root, bg="#f7f7f7")
        ctrl.pack(pady=6)
        ttk.Button(ctrl, text="Reset", command=self.reset_scan).grid(row=0, column=0, padx=6)
        ttk.Button(ctrl, text="Quit", command=self.on_close).grid(row=0, column=1, padx=6)

        # Camera
        self.cap = cv2.VideoCapture(0)
        self.detector = cv2.QRCodeDetector()

        # Internal state
        self.processing = False
        self.last_value = None
        self.last_when = 0

        # Clean close
        self.root.protocol("WM_DELETE_WINDOW", self.on_close)

        self.update_frame()

    def reset_scan(self):
        self.last_value = None
        self.last_qr_var.set("Last QR: (waiting…)")
        self.pred_var.set("Prediction: —")
        self.score_var.set("Score: —")
        self.reason_lbl.config(text="Reasons:\n—")

    def on_close(self):
        try:
            if self.cap and self.cap.isOpened():
                self.cap.release()
        except Exception:
            pass
        self.root.destroy()

    def update_frame(self):
        ret, frame = self.cap.read()
        if ret:
            # Flip for selfie view (optional)
            frame = cv2.flip(frame, 1)

            # Detect & decode
            data, bbox, _ = self.detector.detectAndDecode(frame)

            # Draw box if found
            if bbox is not None and len(bbox) > 0:
                pts = bbox.astype(int).reshape(-1, 2)
                for i in range(len(pts)):
                    cv2.line(frame, tuple(pts[i]), tuple(pts[(i + 1) % len(pts)]), (0, 255, 0), 2)

            # If new QR data appears and we aren't already processing
            now = time.time()
            if data and (data != self.last_value) and (not self.processing) and (now - self.last_when > COOLDOWN_AFTER_DETECT_MS/1000.0):
                self.last_value = data
                self.last_when = now
                self.last_qr_var.set(f"Last QR: {data[:90]}{'...' if len(data)>90 else ''}")
                # Process in a short worker thread to avoid blocking the UI
                threading.Thread(target=self.process_qr, args=(data,), daemon=True).start()

            # Convert to Tk image
            frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            img = Image.fromarray(frame_rgb)
            imgtk = ImageTk.PhotoImage(image=img)
            self.video_lbl.imgtk = imgtk
            self.video_lbl.configure(image=imgtk)

        self.root.after(16, self.update_frame)  # ~60fps

    def process_qr(self, data: str):
        self.processing = True
        try:
            label, score, reasons, resolved = score_url(data)
            self.pred_var.set(f"Prediction: {label}")
            self.score_var.set(f"Score: {score}/100")
            # Color hint in label text
            if "FAKE" in label:
                color = "#c62828"
            elif "REAL" in label:
                color = "#2e7d32"
            else:
                color = "#f9a825"
            self.pred_var.set(f"Prediction: {label}")
            reasons_text = "Reasons:\n" + "\n".join([f"• {r}" for r in reasons])
            reasons_text += f"\nResolved URL: {resolved}"
            self.reason_lbl.config(text=reasons_text, fg=color)
        finally:
            self.processing = False


if __name__ == "__main__":
    root = tk.Tk()
    style = ttk.Style(root)
    try:
        style.theme_use("clam")
    except Exception:
        pass
    app = QRAuthApp(root)
    root.mainloop()
