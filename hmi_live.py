"""
hmi_live.py  -  laptop window for LIVE mode (P5)

Run:   python hmi_live.py
Needs: pip install pyserial pillow      (tkinter comes with Python)
Keep tsr_link.py and the "logos" folder in the same folder as this file.
The window opens maximized and everything grows with it (a small window is just cropped).

How to use:
  1. Choose the COM port (or "Demo (no board)") and press Connect.   SW15 on the board must be UP.
  2. "Open picture..." -> choose a png/jpg.
  3. "Send to board" for one picture, or "Send N times" to measure speed.
  4. Statistics on the right update after every answer.
     Resource and power numbers come from Vivado: type them in the boxes (they are saved).
"""
import csv
import json
import os
import queue
import threading
import time
import tkinter as tk
import tkinter.font as tkfont   # NEW
from tkinter import ttk, filedialog, messagebox

import tsr_link

HERE = os.path.dirname(os.path.abspath(__file__))
SETTINGS_FILE = os.path.join(HERE, "hmi_settings.json")

DEMO = "Demo (no board)"
SIGN_NAMES = ["Stop", "Yield", "No entry", "Priority road",
              "General caution", "Keep right", "Speed limit 30", "Speed limit 50"]

HEADER_BG = "white"   # CHANGED: PREVIEW_PIXEL and BAR_WIDTH were removed (sizes now come from the screen)

# Basys3 chip size (from the plan)
TOTALS = {"lut": 20800, "bram": 50, "dsp": 90}
# bytes on the cable for one picture: 259 sent + 32 received
BYTES_PER_PICTURE = 259 + 32
LINK_MAX_KBPS = 115.2 * 8 / 10        # 115200 baud, 10 line bits per byte -> 92.16 kbps of data

# numbers the user types in (from Vivado reports); they are saved in hmi_settings.json
DEFAULT_SETTINGS = {"lut": "", "bram": "", "dsp": "", "mac_units": "",
                    "macs_per_picture": "17248", "idle_w": "", "active_w": ""}


# ----------------------------------------------------------------------
# small formatting helpers
# ----------------------------------------------------------------------
def fmt_rate(kbps):
    return "%.2f Mbps" % (kbps / 1000) if kbps >= 1000 else "%.1f kbps" % kbps


def fmt_macs(per_second):
    if per_second >= 1e9:
        return "%.2f GMAC/s" % (per_second / 1e9)
    return "%.1f MMAC/s" % (per_second / 1e6)


class Hmi:
    def __init__(self, root):
        self.root = root
        root.title("Traffic-sign recogniser - live mode")
        root.configure(bg="#f0f0f0")
        root.columnconfigure(0, weight=1)      # the one column of the window stretches sideways   # NEW
        root.rowconfigure(3, weight=3)         # main area gets 3 parts of the free height ...   # CHANGED (log taller)
        root.rowconfigure(4, weight=1)         # ... the log gets 1 part (its height comes mostly from 'height=' below)   # CHANGED (log taller)
        self.setup_scaling()   # NEW
        self.maximize()   # NEW

        self.link = None                 # TsrLink once connected
        self.pixels = None               # 256 pixels of the chosen picture
        self.busy = False                # True while pictures are being sent
        self.stop_flag = False
        self.results = queue.Queue()     # the worker thread puts its answers here
        self.logo_images = []            # keep references, or the logos disappear

        # statistics
        self.history = []                # one dict per good answer
        self.sent = 0
        self.errors = 0
        self.last_run = "-"
        self.last_result = None          # (scores, winner) of the last answer, for redrawing the bars   # NEW

        self.stat = {}                   # name -> StringVar shown in the window
        self.setting = {}                # name -> StringVar typed by the user

        self.load_settings()
        self.build_header()
        self.build_connection_row()
        self.build_main_area()
        self.build_log()
        self.set_buttons()
        self.update_stats()
        self.check_results()

    # ------------------------------------------------------------------
    # window size
    # ------------------------------------------------------------------
    def setup_scaling(self):   # NEW
        """Pick sizes from the screen size: bigger screen -> bigger picture, logos and letters."""
        sw, sh = self.root.winfo_screenwidth(), self.root.winfo_screenheight()
        self.ui = max(1.0, min(sw / 1280, sh / 720, 2.0))      # 1.0 on a small screen, 1.5 on full HD
        self.fs = 1 + (self.ui - 1) * 0.7                      # letters grow a bit slower
        base = int(round(10 * self.fs))
        for name in ("TkDefaultFont", "TkTextFont", "TkMenuFont", "TkHeadingFont", "TkFixedFont"):
            tkfont.nametofont(name).configure(size=base)
        self.px = int(14 * self.ui)                            # one picture pixel = px x px on screen
        self.pad = int(2 * self.ui)                            # small gap between text lines

    def maximize(self):   # NEW
        try:
            self.root.state("zoomed")                          # Windows
        except tk.TclError:
            try:
                self.root.attributes("-zoomed", True)          # Linux
            except tk.TclError:
                pass

    # ------------------------------------------------------------------
    # settings file
    # ------------------------------------------------------------------
    def load_settings(self):
        values = dict(DEFAULT_SETTINGS)
        try:
            with open(SETTINGS_FILE) as f:
                values.update(json.load(f))
        except (OSError, ValueError):
            pass
        for key, value in values.items():
            self.setting[key] = tk.StringVar(value=value)

    def save_settings(self):
        try:
            with open(SETTINGS_FILE, "w") as f:
                json.dump({k: v.get() for k, v in self.setting.items()}, f, indent=2)
        except OSError:
            pass

    def number(self, key):
        """The number typed in box `key`, or None if empty / not a number."""
        try:
            return float(self.setting[key].get().replace(",", "."))
        except ValueError:
            return None

    def on_setting_change(self, *args):
        self.save_settings()
        self.update_stats()

    # ------------------------------------------------------------------
    # building the window
    # ------------------------------------------------------------------
    def load_logo(self, filename, height):
        try:
            from PIL import Image, ImageTk
            img = Image.open(os.path.join(HERE, "logos", filename))
            width = round(img.width * height / img.height)
            photo = ImageTk.PhotoImage(img.resize((width, height), Image.LANCZOS))
            self.logo_images.append(photo)
            return photo
        except Exception:
            return None                  # no logo file -> just leave it out

    def build_header(self):
        header = tk.Frame(self.root, bg=HEADER_BG)
        header.grid(row=0, column=0, sticky="ew")   # CHANGED: grid instead of pack
        header.columnconfigure(1, weight=1)

        itb = self.load_logo("itb.png", int(70 * self.ui))   # CHANGED: size from screen
        kcci = self.load_logo("kcci.png", int(50 * self.ui))   # CHANGED: size from screen
        if itb:
            tk.Label(header, image=itb, bg=HEADER_BG).grid(row=0, column=0, padx=14, pady=8)
        title = tk.Frame(header, bg=HEADER_BG)
        title.grid(row=0, column=1)
        tk.Label(title, text="Traffic-Sign Recognition on Basys3", bg=HEADER_BG,
                 font=("Arial", int(20 * self.fs), "bold")).pack()   # CHANGED: font from screen
        tk.Label(title, text="Live mode: picture from laptop, answer from FPGA", bg=HEADER_BG,
                 fg="#555555", font=("Arial", int(11 * self.fs))).pack()   # CHANGED: font from screen
        if kcci:
            tk.Label(header, image=kcci, bg=HEADER_BG).grid(row=0, column=2, padx=14, pady=8)
        tk.Frame(self.root, bg="#2e5aa8", height=3).grid(row=1, column=0, sticky="ew")   # blue line   # CHANGED: grid instead of pack

    def build_connection_row(self):
        row = ttk.Frame(self.root, padding=6)
        row.grid(row=2, column=0, sticky="ew")   # CHANGED: grid instead of pack
        ttk.Label(row, text="Port:").pack(side="left")
        self.port_box = ttk.Combobox(row, width=22, state="readonly")
        self.port_box.pack(side="left", padx=4)
        ttk.Button(row, text="Refresh", command=self.refresh_ports).pack(side="left")
        self.connect_btn = ttk.Button(row, text="Connect", command=self.toggle_connect)
        self.connect_btn.pack(side="left", padx=6)
        self.conn_label = ttk.Label(row, text="not connected", foreground="gray")
        self.conn_label.pack(side="left")
        self.refresh_ports()

    def build_main_area(self):
        main = ttk.Frame(self.root, padding=6)
        main.grid(row=3, column=0, sticky="nsew")   # CHANGED: grid, window can grow
        main.rowconfigure(0, weight=1)   # NEW
        main.columnconfigure(0, weight=0)          # picture panel keeps its size   # NEW
        main.columnconfigure(1, weight=1)          # answer and statistics share the rest   # NEW
        main.columnconfigure(2, weight=1)   # NEW
        self.build_picture_panel(main).grid(row=0, column=0, sticky="nsew", padx=4)   # CHANGED: sticky nsew
        self.build_answer_panel(main).grid(row=0, column=1, sticky="nsew", padx=4)   # CHANGED: sticky nsew
        stats = ttk.Frame(main)
        stats.grid(row=0, column=2, sticky="nsew", padx=4)   # CHANGED: sticky nsew
        stats.columnconfigure(0, weight=1)   # NEW
        for row, weight, build in ((0, 7, self.build_speed_panel),   # NEW (the 3 statistics panels share the height)
                                   (1, 6, self.build_resource_panel),
                                   (2, 3, self.build_power_panel)):
            stats.rowconfigure(row, weight=weight)   # NEW
            build(stats).grid(row=row, column=0, sticky="nsew", pady=4)   # NEW

    # ---- left: picture and buttons ----
    def build_picture_panel(self, parent):
        box = ttk.LabelFrame(parent, text="Picture sent (16 x 16 gray)", padding=6)
        size = 16 * self.px   # CHANGED: self.px instead of PREVIEW_PIXEL
        self.canvas = tk.Canvas(box, width=size, height=size, bg="#dddddd", highlightthickness=0)
        self.canvas.pack()

        self.open_btn = ttk.Button(box, text="Open picture...", command=self.open_picture)
        self.open_btn.pack(fill="x", pady=(self.pad * 2, 0), ipady=self.pad)   # CHANGED: taller buttons
        self.send_btn = ttk.Button(box, text="Send to board", command=lambda: self.start_run(1))
        self.send_btn.pack(fill="x", pady=(self.pad, 0), ipady=self.pad)   # CHANGED: taller buttons

        run = ttk.Frame(box)
        run.pack(fill="x", pady=(self.pad, 0))
        self.count_var = tk.StringVar(value="20")
        ttk.Spinbox(run, from_=2, to=1000, width=5, textvariable=self.count_var).pack(side="left")
        self.run_btn = ttk.Button(run, text="Send N times", command=self.send_many)
        self.run_btn.pack(side="left", fill="x", expand=True, padx=(4, 0), ipady=self.pad)   # CHANGED: taller buttons
        self.stop_btn = ttk.Button(box, text="Stop", command=self.stop)
        self.stop_btn.pack(fill="x", pady=(self.pad, 0), ipady=self.pad)   # CHANGED: taller buttons

        ttk.Separator(box).pack(fill="x", pady=self.pad * 2)
        ttk.Button(box, text="Reset statistics", command=self.reset_stats).pack(fill="x", ipady=self.pad)   # CHANGED: taller buttons
        ttk.Button(box, text="Export results (CSV)...", command=self.export_csv).pack(
            fill="x", pady=(self.pad, 0), ipady=self.pad)   # CHANGED: taller buttons
        return box

    # ---- middle: the answer ----
    def build_answer_panel(self, parent):
        box = ttk.LabelFrame(parent, text="Answer from board", padding=6)
        self.sign_label = tk.Label(box, text="-", font=("Arial", int(30 * self.fs), "bold"))   # CHANGED: font from screen, fills width
        self.sign_label.pack(fill="x", pady=(self.pad, 0))
        self.info_label = ttk.Label(box, text="class: -    status: -    time: -")
        self.info_label.pack(pady=(0, self.pad * 2))

        self.bars = []                   # one row per class: (bar canvas, value label)
        for k in range(8):
            line = ttk.Frame(box)
            line.pack(fill="both", expand=True, pady=1)         # rows share the free height   # CHANGED: rows share the free height
            ttk.Label(line, text="%d %s" % (k, tsr_link.CLASS_NAMES[k]), width=10).pack(side="left")
            bar = tk.Canvas(line, height=int(16 * self.ui), bg="white", highlightthickness=1,   # CHANGED: no fixed width
                            highlightbackground="#999999")
            bar.pack(side="left", fill="x", expand=True, padx=4)   # bar stretches sideways   # CHANGED: bar stretches sideways
            value = ttk.Label(line, text="", width=8)
            value.pack(side="left")
            self.bars.append((bar, value))
        self.bars[0][0].bind("<Configure>", self.draw_bars)      # window resized -> redraw   # NEW: redraw bars when window is resized
        return box

    # ---- right: statistics ----
    def stat_row(self, box, row, label, name):
        """One line: a label on the left, a value (StringVar) on the right."""
        self.stat[name] = tk.StringVar(value="-")
        ttk.Label(box, text=label).grid(row=row, column=0, sticky="w", padx=(0, 10), pady=self.pad)   # CHANGED: pady
        ttk.Label(box, textvariable=self.stat[name]).grid(row=row, column=1, sticky="w", pady=self.pad)

    def input_row(self, box, row, label, key, unit="", total_name=None):
        """One line with a box to type a number in (value from Vivado)."""
        ttk.Label(box, text=label).grid(row=row, column=0, sticky="w", padx=(0, 10), pady=self.pad)   # CHANGED: pady
        entry = ttk.Entry(box, width=9, textvariable=self.setting[key])
        entry.grid(row=row, column=1, sticky="w", pady=self.pad)
        ttk.Label(box, text=unit).grid(row=row, column=2, sticky="w", padx=4, pady=self.pad)
        if total_name:
            self.stat[total_name] = tk.StringVar(value="")
            ttk.Label(box, textvariable=self.stat[total_name]).grid(row=row, column=3, sticky="w",
                                                                    pady=self.pad)
        self.setting[key].trace_add("write", self.on_setting_change)

    def build_speed_panel(self, parent):
        box = ttk.LabelFrame(parent, text="Speed", padding=6)
        self.stat_row(box, 0, "Pictures", "pictures")
        self.stat_row(box, 1, "FPS (whole system)", "fps")
        self.stat_row(box, 2, "FPS (last 'Send N times')", "run_fps")
        self.stat_row(box, 3, "FPS (CNN alone)", "cnn_fps")
        self.stat_row(box, 4, "Bitrate (data on cable)", "bitrate")
        self.stat_row(box, 5, "CNN latency", "cnn_lat")
        self.stat_row(box, 6, "Round trip", "round_trip")
        return box

    def build_resource_panel(self, parent):
        box = ttk.LabelFrame(parent, text="Resource utilization", padding=6)
        self.input_row(box, 0, "LUT used", "lut", "of %d" % TOTALS["lut"], "lut_pct")
        self.input_row(box, 1, "BRAM used", "bram", "of %d" % TOTALS["bram"], "bram_pct")
        self.input_row(box, 2, "DSP used", "dsp", "of %d" % TOTALS["dsp"], "dsp_pct")
        self.input_row(box, 3, "MAC units in design", "mac_units")
        self.input_row(box, 4, "MACs per picture", "macs_per_picture")
        self.stat_row(box, 5, "MAC rate", "mac_rate")
        return box

    def build_power_panel(self, parent):
        box = ttk.LabelFrame(parent, text="Power", padding=6)
        self.input_row(box, 0, "Idle power", "idle_w", "W")
        self.input_row(box, 1, "Active power", "active_w", "W")
        self.stat_row(box, 2, "Energy per picture", "energy")
        return box

    def build_log(self):
        frame = ttk.LabelFrame(self.root, text="Log", padding=4)
        frame.grid(row=4, column=0, sticky="nsew", padx=6, pady=6)   # CHANGED: grid instead of pack
        self.log_box = tk.Text(frame, height=7, width=40, state="disabled")   # CHANGED (log taller: 7 lines)
        self.log_box.pack(fill="both", expand=True)

    # ------------------------------------------------------------------
    # small helpers
    # ------------------------------------------------------------------
    def log(self, text):
        self.log_box.config(state="normal")
        self.log_box.insert("end", time.strftime("%H:%M:%S  ") + text + "\n")
        self.log_box.see("end")
        self.log_box.config(state="disabled")

    def set_buttons(self):
        """Enable only the buttons that make sense right now."""
        connected = self.link is not None
        can_send = connected and self.pixels is not None and not self.busy
        state = lambda ok: "normal" if ok else "disabled"
        self.send_btn.config(state=state(can_send))
        self.run_btn.config(state=state(can_send))
        self.stop_btn.config(state=state(self.busy))
        self.open_btn.config(state=state(not self.busy))
        self.connect_btn.config(text="Disconnect" if connected else "Connect",
                                state=state(not self.busy))

    def refresh_ports(self):
        ports = [DEMO]
        try:
            from serial.tools import list_ports
            ports += [p.device for p in list_ports.comports()]
        except ImportError:
            pass
        self.port_box["values"] = ports
        if not self.port_box.get():
            self.port_box.set(ports[-1])        # last one = most likely the board

    # ------------------------------------------------------------------
    # buttons
    # ------------------------------------------------------------------
    def toggle_connect(self):
        if self.link is not None:                       # disconnect
            self.link.close()
            self.link = None
            self.conn_label.config(text="not connected", foreground="gray")
            self.log("disconnected")
        else:                                           # connect
            port = self.port_box.get()
            try:
                if port == DEMO:
                    self.link = tsr_link.TsrLink(tsr_link.FakeBoard(delay=0.03))
                else:
                    self.link = tsr_link.TsrLink(port)
            except Exception as e:
                messagebox.showerror("Cannot open port", str(e))
                return
            self.conn_label.config(text="connected to " + port, foreground="green")
            self.log("connected to " + port)
        self.set_buttons()

    def open_picture(self):
        path = filedialog.askopenfilename(
            title="Choose a picture",
            filetypes=[("Pictures", "*.png *.jpg *.jpeg *.bmp"), ("All files", "*.*")])
        if not path:
            return
        try:
            self.pixels = tsr_link.load_picture(path)       # 256 numbers, 0..255
        except Exception as e:
            messagebox.showerror("Cannot open picture", str(e))
            return
        self.draw_preview()
        self.log("picture: " + path.replace("\\", "/").split("/")[-1])
        self.set_buttons()

    def draw_preview(self):
        self.canvas.delete("all")
        for i, value in enumerate(self.pixels):
            x, y = (i % 16) * self.px, (i // 16) * self.px   # CHANGED: self.px
            color = "#%02x%02x%02x" % (value, value, value)
            self.canvas.create_rectangle(x, y, x + self.px, y + self.px, fill=color, outline=color)   # CHANGED: self.px

    def send_many(self):
        try:
            count = max(2, int(self.count_var.get()))
        except ValueError:
            messagebox.showerror("Send N times", "N must be a whole number")
            return
        self.start_run(count)

    def stop(self):
        self.stop_flag = True

    def reset_stats(self):
        self.history = []
        self.sent = 0
        self.errors = 0
        self.last_run = "-"
        self.update_stats()
        self.log("statistics reset")

    def export_csv(self):
        if not self.history:
            messagebox.showinfo("Export", "No results yet.")
            return
        path = filedialog.asksaveasfilename(defaultextension=".csv", filetypes=[("CSV", "*.csv")])
        if not path:
            return
        with open(path, "w", newline="") as f:
            w = csv.writer(f)
            w.writerow(["no", "time", "class", "sign", "cnn_cycles", "cnn_us", "round_trip_ms"])
            for n, h in enumerate(self.history, 1):
                w.writerow([n, h["time"], h["class"], SIGN_NAMES[h["class"]],
                            h["cycles"], "%.2f" % h["us"], "%.1f" % h["rt_ms"]])
        self.log("saved %d results to %s" % (len(self.history), path))

    # ------------------------------------------------------------------
    # sending (in a background thread, so the window does not freeze)
    # ------------------------------------------------------------------
    def start_run(self, count):
        self.busy = True
        self.stop_flag = False
        self.run_count = count
        self.set_buttons()
        if count == 1:
            self.log("sending 259 bytes...")
        else:
            self.log("sending the picture %d times..." % count)
        threading.Thread(target=self.run_worker, args=(count,), daemon=True).start()

    def run_worker(self, count):
        run_start = time.time()
        done = 0
        for _ in range(count):
            if self.stop_flag:
                break
            start = time.time()
            try:
                result, error = self.link.classify(self.pixels), None
            except Exception as e:
                result, error = None, e
            round_trip_ms = (time.time() - start) * 1000
            self.results.put(("answer", result, error, round_trip_ms))
            done += 1
            if error is not None:
                break                                   # stop at the first problem
        self.results.put(("run_done", done, time.time() - run_start))

    def check_results(self):
        """Runs every 50 ms in the window thread: handle everything the worker has sent."""
        try:
            while True:
                message = self.results.get_nowait()
                if message[0] == "answer":
                    self.handle_answer(*message[1:])
                else:
                    self.handle_run_done(*message[1:])
        except queue.Empty:
            pass
        self.root.after(50, self.check_results)

    def handle_answer(self, result, error, round_trip_ms):
        self.sent += 1
        if error is not None:
            self.errors += 1
            self.show_error(str(error))
        elif result["status"] != 0:
            self.errors += 1
            self.show_error("board says: " + result["status_text"])
        else:
            self.history.append({"time": time.strftime("%H:%M:%S"), "class": result["class"],
                                 "cycles": result["cycles"], "us": result["time_us"],
                                 "rt_ms": round_trip_ms})
            self.show_result(result)
            if self.run_count == 1:
                self.log("answer: %s (class %d), CNN %.1f us, round trip %.0f ms" %
                         (SIGN_NAMES[result["class"]], result["class"], result["time_us"],
                          round_trip_ms))
        self.update_stats()

    def handle_run_done(self, done, seconds):
        self.busy = False
        self.set_buttons()
        if self.run_count > 1 and done > 1 and seconds > 0:
            fps = done / seconds
            self.last_run = "%.1f   (%d pictures in %.2f s)" % (fps, done, seconds)
            self.log("run finished: %d pictures in %.2f s = %.1f FPS" % (done, seconds, fps))
            self.update_stats()

    # ------------------------------------------------------------------
    # showing the answer
    # ------------------------------------------------------------------
    def show_error(self, text):
        self.sign_label.config(text="ERROR", fg="red")
        self.info_label.config(text=text)
        self.log("error: " + text)

    def show_result(self, r):
        self.sign_label.config(text=SIGN_NAMES[r["class"]], fg="black")
        self.info_label.config(text="class: %d    status: OK    CNN time: %.1f us" %
                               (r["class"], r["time_us"]))
        self.last_result = (r["scores"], r["class"])   # NEW
        self.draw_bars()   # NEW

    def draw_bars(self, event=None):   # NEW (bars are now drawn here, as wide as the window)
        """Draw the 8 score bars as wide as the window allows."""
        if self.last_result is None:
            return
        scores, winner = self.last_result
        low, high = min(scores), max(scores)
        span = (high - low) or 1                        # avoid dividing by zero
        for k, (bar, value) in enumerate(self.bars):
            width, height = max(bar.winfo_width() - 2, 10), max(bar.winfo_height(), 10)
            length = int(width * (scores[k] - low) / span)
            bar.delete("all")
            bar.create_rectangle(0, 0, length, height, outline="",
                                 fill="#2e8b57" if k == winner else "#9db7d5")
            value.config(text=str(scores[k]))

    # ------------------------------------------------------------------
    # statistics
    # ------------------------------------------------------------------
    def update_stats(self):
        s = self.stat
        h = self.history
        s["pictures"].set("sent %d     ok %d     errors %d" % (self.sent, len(h), self.errors))
        s["run_fps"].set(self.last_run)

        # ---- speed ----
        if h:
            cnn_us = [x["us"] for x in h]
            rt_ms = [x["rt_ms"] for x in h]
            avg_us = sum(cnn_us) / len(cnn_us)
            avg_rt = max(sum(rt_ms) / len(rt_ms), 0.001)

            s["fps"].set("%.1f   (1 / average round trip)" % (1000 / avg_rt))
            s["cnn_fps"].set("%.0f   (1 / average CNN latency)" % (1e6 / max(avg_us, 0.001)))
            kbps = BYTES_PER_PICTURE * 8 / avg_rt                   # bits per ms = kbit/s
            s["bitrate"].set("%s   (cable limit %s)" % (fmt_rate(kbps), fmt_rate(LINK_MAX_KBPS)))
            s["cnn_lat"].set("last %.1f   avg %.1f   min %.1f   max %.1f  us" %
                             (cnn_us[-1], avg_us, min(cnn_us), max(cnn_us)))
            s["round_trip"].set("last %.0f   avg %.0f   min %.0f   max %.0f  ms" %
                                (rt_ms[-1], avg_rt, min(rt_ms), max(rt_ms)))
        else:
            avg_us = None
            for name in ("fps", "cnn_fps", "bitrate", "cnn_lat", "round_trip"):
                s[name].set("-")

        # ---- resources: percent of the chip ----
        for key in ("lut", "bram", "dsp"):
            used = self.number(key)
            s[key + "_pct"].set("" if used is None else "= %.1f %%" % (100 * used / TOTALS[key]))

        # ---- MAC rate: MACs per picture / CNN time ----
        macs = self.number("macs_per_picture")
        s["mac_rate"].set(fmt_macs(macs * 1e6 / avg_us) if macs and avg_us else "-")

        # ---- energy: active power x CNN time ----
        active = self.number("active_w")
        if active is not None and avg_us:
            s["energy"].set("%.4f mJ   (active power x CNN latency)" % (active * avg_us / 1000))
        else:
            s["energy"].set("-")


def main():
    root = tk.Tk()
    Hmi(root)
    root.mainloop()


if __name__ == "__main__":
    main()