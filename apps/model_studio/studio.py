"""Select training recipes and qualified Basys 3 deployments."""
import hashlib
import json
import os
from pathlib import Path
import queue
import shutil
import subprocess
import sys
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from uuid import uuid4

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
BUILD = ROOT / "build/model_studio"
PROFILES = json.loads((HERE / "profiles.json").read_text(encoding="utf-8"))


def sha256(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def stage_bitstream(model, bitstream, output):
    profile = PROFILES["deployment"][model]
    package = ROOT / profile["package"]
    seal = package / "checksums.json"
    if sha256(seal) != profile["seal_sha256"]:
        raise ValueError("Model package identity does not match the deployment profile.")
    for name, expected in json.loads(seal.read_text(encoding="utf-8")).items():
        if sha256(package / name) != expected:
            raise ValueError(f"Model package checksum mismatch: {name}")
    # Program a private copy so replacing the selected file cannot change the upload.
    output.mkdir(parents=True)
    staged = output / "model.bit"
    shutil.copyfile(bitstream, staged)
    if sha256(staged) != profile["bitstream_sha256"]:
        raise ValueError("Bitstream is not qualified for this model profile.")
    return staged


class Studio:
    def __init__(self, root):
        self.root = root
        self.messages = queue.Queue()
        self.buttons = []
        root.title("Road Sign CNN Model Studio")
        root.geometry("860x620")
        tabs = ttk.Notebook(root)
        tabs.pack(fill="x", padx=12, pady=12)
        training = ttk.Frame(tabs, padding=12)
        deploy = ttk.Frame(tabs, padding=12)
        tabs.add(training, text="Training")
        tabs.add(deploy, text="Program Basys 3")

        self.recipe = self.choose(training, "Training recipe", PROFILES["training"])
        self.dataset = self.path(training, "GTSRB dataset", filedialog.askdirectory)
        self.button(training, "Start training", self.train)
        ttk.Label(training, text="Each run has a separate output folder and validation results.").pack(anchor="w")

        self.model = self.choose(deploy, "Qualified deployment", PROFILES["deployment"])
        self.info = ttk.Label(deploy)
        self.info.pack(anchor="w")
        self.model.trace_add("write", self.show_profile)
        self.show_profile()
        self.bitstream = self.path(deploy, "Bitstream", lambda: filedialog.askopenfilename(
            filetypes=[("FPGA bitstream", "*.bit")]))
        self.bitstream.set(str(BUILD / "baseline/p2-doc-int-v2/top_basys3.bit"))
        self.vivado = self.path(deploy, "Vivado executable", filedialog.askopenfilename)
        self.vivado.set(shutil.which("vivado") or "")
        self.button(deploy, "Program selected model", self.program)
        self.log = tk.Text(root, wrap="word", state="disabled")
        self.log.pack(fill="both", expand=True, padx=12, pady=(0, 12))
        root.after(100, self.drain)

    def show_profile(self, *_):
        profile = PROFILES["deployment"][self.model.get()]
        self.info.config(text=f'{profile["interface"]} · RTL {profile["source"]}')

    def choose(self, parent, title, values):
        ttk.Label(parent, text=title).pack(anchor="w")
        value = tk.StringVar(value=next(iter(values)))
        ttk.Combobox(parent, values=list(values), textvariable=value, state="readonly").pack(fill="x")
        return value

    def path(self, parent, title, picker):
        ttk.Label(parent, text=title).pack(anchor="w")
        row = ttk.Frame(parent)
        row.pack(fill="x")
        value = tk.StringVar()
        ttk.Entry(row, textvariable=value).pack(side="left", fill="x", expand=True)

        def browse():
            selected = picker()
            if selected:
                value.set(selected)

        ttk.Button(row, text="Browse", command=browse).pack(side="right")
        return value

    def button(self, parent, title, action):
        button = ttk.Button(parent, text=title, command=action)
        button.pack(anchor="w", pady=8)
        self.buttons.append(button)

    def train(self):
        dataset = Path(self.dataset.get()).resolve()
        if not (dataset / "Train.csv").is_file():
            messagebox.showerror("Dataset", "Select the GTSRB directory containing Train.csv.")
            return
        profile = PROFILES["training"][self.recipe.get()]
        output = BUILD / "training" / uuid4().hex
        self.start(lambda: (
            [sys.executable, "-u", str(ROOT / profile["script"]), *profile["args"],
             "--dataset", str(dataset), "--output", str(output), "--epochs", str(profile["epochs"])],
            output.parent / f"{output.name}.log",
        ))

    def program(self):
        model = self.model.get()
        bitstream = Path(self.bitstream.get()).resolve()
        vivado = self.vivado.get().strip()
        if not bitstream.is_file() or not vivado:
            messagebox.showerror("Deployment", "Select a bitstream and the Vivado executable.")
            return
        output = BUILD / "deployment" / uuid4().hex

        def command():
            staged = stage_bitstream(model, bitstream, output)
            return [vivado, "-mode", "batch", "-nojournal", "-nolog",
                    "-source", str(HERE / "program_basys3.tcl"), "-tclargs", str(staged)], output / "program.log"

        self.start(command)

    def start(self, command):
        for button in self.buttons:
            button.config(state="disabled")

        def worker():
            try:
                argv, log = command()
                log.parent.mkdir(parents=True, exist_ok=True)
                self.messages.put(f"Log: {log}\n")
                with log.open("w", encoding="utf-8") as stream, subprocess.Popen(
                    argv, cwd=log.parent, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                    text=True, encoding="utf-8", errors="replace",
                    creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
                ) as process:
                    for line in process.stdout:
                        stream.write(line)
                        self.messages.put(line)
                    code = process.wait()
                self.messages.put(f"Finished (exit {code}).\n")
            except (OSError, ValueError) as error:
                self.messages.put(f"Failed: {error}\n")
            finally:
                self.messages.put(None)

        threading.Thread(target=worker, daemon=True).start()

    def drain(self):
        for _ in range(100):
            try:
                line = self.messages.get_nowait()
            except queue.Empty:
                break
            if line is None:
                for button in self.buttons:
                    button.config(state="normal")
            else:
                self.log.config(state="normal")
                self.log.insert("end", line)
                self.log.see("end")
                self.log.config(state="disabled")
        self.root.after(100, self.drain)


if __name__ == "__main__":
    window = tk.Tk()
    Studio(window)
    window.mainloop()
