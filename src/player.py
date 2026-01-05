import os
import tkinter as tk
from tkinter import filedialog, messagebox, simpledialog
import pygame
import numpy as np
import time
import re
import threading
import json
from pathlib import Path
from pydub import AudioSegment
from PIL import Image, ImageTk
from mutagen.id3 import ID3, APIC
from io import BytesIO

# --- CONFIG ---
BG_MAIN = "#020202"
BG_CARD = "#0f0f0f"
ACCENT = "#00ff88"
TEXT_DIM = "#aaaaaa" 
COLORS = ["#3498db", "#e74c3c", "#f1c40f", "#9b59b6", "#2ecc71"]
BASE_DIR = Path(__file__).parent

class UltimatePlayer:
    def __init__(self, root):
        self.root = root
        self.root.title("StemQuina - v0.3 PRO MASTER")
        self.root.geometry("1400x900")
        self.root.configure(bg=BG_MAIN)

        pygame.mixer.pre_init(44100, -16, 2, 512)
        pygame.mixer.init()

        self.db_path = BASE_DIR / "database"
        
        # --- VARIABLES ---
        self.audio_segments = [None] * 5
        self.full_samples = [None] * 5 
        self.waveform_cache = [None] * 5 
        self.markers = []
        self.marker_labels = {} 
        self.marker_time_labels = {}
        self.lyrics_data = []
        self.current_track_name = ""
        self.current_lrc_idx = -1
        self.current_solo_idx = None
        self.pre_solo_mutes = [False] * 5 
        self.duration_ms = 0
        self.play_pos_ms = 0.0
        self.start_time_ref = 0 
        self.is_playing = False
        self.is_counting = False
        
        self.last_stop_click_time = 0
        self.is_lyrics_editing = False
        self.nudge_after_id = None 
        self.is_nudging = False
        
        self.loop_a = None
        self.loop_b = None
        
        self.playback_speed = tk.DoubleVar(value=1.0)
        self.master_vol = tk.DoubleVar(value=0.8)
        self.repeat_var = tk.BooleanVar(value=True)
        self.count_in_var = tk.BooleanVar(value=False)
        self.vols = [tk.DoubleVar(value=0.8) for _ in range(5)]
        self.mutes = [tk.BooleanVar(value=False) for _ in range(5)]
        self.track_names = [tk.StringVar(value="") for _ in range(5)]
        
        # STEM MAPPING
        self.track_frames = []
        self.track_mappings = [tk.StringVar(value="NONE") for _ in range(5)]
        self.stem_options = ["NONE"]
        self.option_menus = []

        self.eq_peaks = np.zeros(20) 

        self.setup_ui()
        self.refresh_list()
        
        self.root.bind_all("<space>", self.handle_space)
        self.root.bind_all("m", self.handle_marker_key)
        for i in range(1, 10):
            self.root.bind_all(str(i), lambda e, num=i: self.handle_number_key(num-1))
            self.root.bind_all(f"<KP_{i}>", lambda e, num=i: self.handle_number_key(num-1))
        
        self.root.bind("<Configure>", self.on_resize_event)
        self.root.after(200, lambda: self.root.focus_force())
        self.update_loop()

    def format_ms(self, ms):
        if ms is None: return "--:--.--"
        s = ms / 1000
        return f"{int(s//60):02}:{s%60:05.2f}"

    def is_typing(self):
        focused = self.root.focus_get()
        return isinstance(focused, (tk.Entry, tk.Text))

    def handle_space(self, event):
        if not self.is_typing(): self.toggle(); return "break"

    def handle_marker_key(self, event):
        if not self.is_typing(): self.add_marker()

    def handle_number_key(self, idx):
        if not self.is_typing(): self.jump_to_marker(idx)

    def start_nudge(self, func, *args):
        self.is_nudging = True; func(*args)
        self.nudge_after_id = self.root.after(400, lambda: self.repeat_nudge(func, *args))

    def repeat_nudge(self, func, *args):
        func(*args); self.nudge_after_id = self.root.after(50, lambda: self.repeat_nudge(func, *args))

    def stop_nudge(self, event=None):
        if self.nudge_after_id: self.root.after_cancel(self.nudge_after_id); self.nudge_after_id = None
        self.is_nudging = False; self.refresh_marker_ui() 

    def create_beep(self, freq=1000, duration_ms=70):
        sr = 44100; n = int(sr * (duration_ms / 1000.0)); t = np.linspace(0, duration_ms / 1000.0, n, False)
        wave = (np.sin(2 * np.pi * freq * t) * 10000).astype(np.int16)
        stereo = np.stack((wave, wave), axis=-1)
        return pygame.sndarray.make_sound(stereo)

    def setup_ui(self):
        # SIDEBAR
        self.side = tk.Frame(self.root, bg="#050505", width=180); self.side.pack(side=tk.LEFT, fill=tk.Y); self.side.pack_propagate(False)
        tk.Label(self.side, text="LIBRARY", fg=ACCENT, bg="#050505", font=("Arial", 10, "bold")).pack(pady=10)
        self.cover_canvas = tk.Canvas(self.side, bg="#000", width=110, height=110, highlightthickness=1, highlightbackground="#111"); self.cover_canvas.pack(pady=5)
        self.listbox = tk.Listbox(self.side, bg="#050505", fg="#888", borderwidth=0, selectbackground="#222", font=("Arial", 9))
        self.listbox.pack(fill=tk.BOTH, expand=True, padx=5, pady=10)
        self.listbox.bind("<<ListboxSelect>>", self.on_select)

        # MAIN
        self.main = tk.Frame(self.root, bg=BG_MAIN); self.main.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=15)
        tb = tk.Frame(self.main, bg=BG_MAIN); tb.pack(fill=tk.X, pady=10)
        tk.Label(tb, text="StemQuina", fg="white", bg=BG_MAIN, font=("Impact", 24)).pack(side=tk.LEFT)
        tk.Label(tb, text="v0.3", fg=ACCENT, bg=BG_MAIN, font=("Arial", 8, "bold")).pack(side=tk.LEFT, padx=5, pady=(10,0))
        
        ctrl = tk.Frame(tb, bg=BG_CARD, padx=15, pady=8); ctrl.pack(side=tk.RIGHT)
        tk.Checkbutton(ctrl, text="Count-IN", variable=self.count_in_var, bg=BG_CARD, fg="#888", selectcolor="#000", font=("Arial", 7, "bold")).pack(side=tk.LEFT, padx=5)
        tk.Scale(ctrl, from_=0, to=1, resolution=0.01, orient=tk.HORIZONTAL, variable=self.master_vol, bg=BG_CARD, length=80, showvalue=0, command=lambda v: self.update_all_mixes()).pack(side=tk.LEFT, padx=10)
        tk.Button(ctrl, text="-", command=lambda: self.change_speed(-0.1), bg="#222", fg="white", width=2, relief=tk.FLAT).pack(side=tk.LEFT)
        tk.Label(ctrl, textvariable=self.playback_speed, fg=ACCENT, bg=BG_CARD, width=4, font=("Consolas", 11, "bold")).pack(side=tk.LEFT)
        tk.Button(ctrl, text="+", command=lambda: self.change_speed(0.1), bg="#222", fg="white", width=2, relief=tk.FLAT).pack(side=tk.LEFT)

        # Timeline
        self.timeline_f = tk.Frame(self.main, bg=BG_MAIN); self.timeline_f.pack(fill=tk.X)
        tk.Frame(self.timeline_f, width=369, bg=BG_MAIN).pack(side=tk.LEFT)
        self.marker_canvas = tk.Canvas(self.timeline_f, height=25, bg=BG_MAIN, highlightthickness=0)
        self.marker_canvas.pack(side=tk.LEFT, fill=tk.X, expand=True)

        # TRACKS
        self.canvases, self.playheads, self.mini_scopes = [], [], []
        for i in range(5):
            f = tk.Frame(self.main, bg=BG_CARD, pady=1); f.pack(fill=tk.X, pady=1)
            self.track_frames.append(f)
            c = tk.Frame(f, bg=BG_CARD, width=300); c.pack(side=tk.LEFT, fill=tk.Y); c.pack_propagate(False)
            
            if i == 0:
                tk.Label(c, text="ORIGINAL TRACK", fg="#555", bg=BG_CARD, font=("Arial", 6, "bold"), width=15).pack(side=tk.TOP, anchor="w", padx=2)
            else:
                om = tk.OptionMenu(c, self.track_mappings[i], "NONE", command=lambda v, idx=i: self.on_stem_change(idx, v))
                om.config(bg="#111", fg=ACCENT, font=("Arial", 6), borderwidth=0, highlightthickness=0, width=18)
                om.pack(side=tk.TOP, anchor="w", padx=2); self.option_menus.append(om)

            tk.Entry(c, textvariable=self.track_names[i], bg=BG_CARD, fg=COLORS[i], font=("Arial", 8, "bold"), borderwidth=0, width=12).pack(side=tk.LEFT, padx=2)
            tk.Button(c, text="S", command=lambda idx=i: self.solo_track(idx), bg="#222", fg="orange", font=("Arial", 7, "bold"), width=2, relief=tk.FLAT).pack(side=tk.LEFT, padx=1)
            tk.Checkbutton(c, text="M", variable=self.mutes[i], command=lambda idx=i: self.update_mix(idx), bg="#222", fg="white", selectcolor="#e74c3c", indicatoron=False, width=2).pack(side=tk.LEFT, padx=1)
            tk.Scale(c, from_=0, to=1, resolution=0.01, orient=tk.HORIZONTAL, variable=self.vols[i], bg=BG_CARD, highlightthickness=0, showvalue=0, length=80, command=lambda v, idx=i: self.update_mix(idx)).pack(side=tk.LEFT, padx=5)
            
            ms = tk.Canvas(f, width=60, height=35, bg="#050505", highlightthickness=0, cursor="hand2")
            ms.pack(side=tk.LEFT, padx=2); ms.bind("<Button-1>", lambda e, idx=i: self.solo_track(idx))
            ms.bind("<Button-3>", lambda e, idx=i: self.toggle_mute(idx)); self.mini_scopes.append(ms)
            
            canv = tk.Canvas(f, height=35, bg="#000", highlightthickness=0)
            canv.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=5); self.canvases.append(canv)
            canv.bind("<Button-1>", self.on_click_wave); canv.bind("<Button-3>", self.set_loop_a); canv.bind("<Control-Button-3>", self.set_loop_b)
            self.playheads.append(canv.create_line(0, 0, 0, 35, fill="white", width=1))

        self.mark_frame = tk.Frame(self.main, bg=BG_CARD, height=40); self.mark_frame.pack(fill=tk.X, pady=2)
        self.mark_container = tk.Frame(self.mark_frame, bg=BG_CARD); self.mark_container.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        # Footer
        self.foot = tk.Frame(self.main, bg=BG_MAIN, pady=10); self.foot.pack(fill=tk.X)
        tk.Button(self.foot, text="|<<", command=lambda: self.play_from(0), bg="#1a1a1a", fg="white", width=4, relief=tk.FLAT).pack(side=tk.LEFT, padx=2)
        tk.Button(self.foot, text="-5s", command=lambda: self.seek(-5000), bg="#222", fg="white", width=5, relief=tk.FLAT).pack(side=tk.LEFT, padx=2)
        self.btn_play = tk.Button(self.foot, text=" ▶ PLAY ", command=self.toggle, bg=ACCENT, fg="black", font=("Arial", 10, "bold"), width=12, relief=tk.FLAT); self.btn_play.pack(side=tk.LEFT, padx=5)
        self.btn_stop = tk.Button(self.foot, text=" ■ STOP ", command=self.stop_logic, bg="#e74c3c", fg="white", font=("Arial", 10), width=12, relief=tk.FLAT); self.btn_stop.pack(side=tk.LEFT, padx=5)
        tk.Button(self.foot, text="+5s", command=lambda: self.seek(5000), bg="#222", fg="white", width=5, relief=tk.FLAT).pack(side=tk.LEFT, padx=2)
        
        tk.Frame(self.foot, width=15, bg=BG_MAIN).pack(side=tk.LEFT)
        tk.Label(self.foot, text="A:", fg="orange", bg=BG_MAIN, font=("Arial", 8, "bold")).pack(side=tk.LEFT)
        b_la_m = tk.Button(self.foot, text="<", bg="#222", fg="white", width=1, font=("Arial", 7), relief=tk.FLAT); b_la_m.pack(side=tk.LEFT)
        b_la_m.bind("<ButtonPress-1>", lambda e: self.start_nudge(self.nudge_loop, 'a', -20)); b_la_m.bind("<ButtonRelease-1>", self.stop_nudge)
        self.lbl_a = tk.Label(self.foot, text="--:--.--", fg="white", bg="#000", width=9, font=("Consolas", 10)); self.lbl_a.pack(side=tk.LEFT, padx=1)
        b_la_p = tk.Button(self.foot, text=">", bg="#222", fg="white", width=1, font=("Arial", 7), relief=tk.FLAT); b_la_p.pack(side=tk.LEFT)
        b_la_p.bind("<ButtonPress-1>", lambda e: self.start_nudge(self.nudge_loop, 'a', 20)); b_la_p.bind("<ButtonRelease-1>", self.stop_nudge)
        
        tk.Label(self.foot, text="B:", fg="orange", bg=BG_MAIN, font=("Arial", 8, "bold")).pack(side=tk.LEFT, padx=(8,0))
        b_lb_m = tk.Button(self.foot, text="<", bg="#222", fg="white", width=1, font=("Arial", 7), relief=tk.FLAT); b_lb_m.pack(side=tk.LEFT)
        b_lb_m.bind("<ButtonPress-1>", lambda e: self.start_nudge(self.nudge_loop, 'b', -20)); b_lb_m.bind("<ButtonRelease-1>", self.stop_nudge)
        self.lbl_b = tk.Label(self.foot, text="--:--.--", fg="white", bg="#000", width=9, font=("Consolas", 10)); self.lbl_b.pack(side=tk.LEFT, padx=1)
        b_lb_p = tk.Button(self.foot, text=">", bg="#222", fg="white", width=1, font=("Arial", 7), relief=tk.FLAT); b_lb_p.pack(side=tk.LEFT)
        b_lb_p.bind("<ButtonPress-1>", lambda e: self.start_nudge(self.nudge_loop, 'b', 20)); b_lb_p.bind("<ButtonRelease-1>", self.stop_nudge)
        
        tk.Button(self.foot, text="RESET AB", command=self.clear_loop, bg="#332222", fg="#aaa", font=("Arial", 7), relief=tk.FLAT).pack(side=tk.LEFT, padx=10)
        tk.Checkbutton(self.foot, text="REPEAT", variable=self.repeat_var, bg="#111", fg="white", selectcolor=ACCENT, indicatoron=False, padx=10, font=("Arial", 7, "bold")).pack(side=tk.LEFT, padx=5)
        self.time_label = tk.Label(self.foot, text="00:00 / 00:00 / -00:00", fg="white", bg=BG_MAIN, font=("Consolas", 13)); self.time_label.pack(side=tk.RIGHT)

        self.mid_panel = tk.Frame(self.main, bg="#050505", height=160); self.mid_panel.pack(fill=tk.BOTH, pady=5, expand=True)
        self.ly_synced_f = tk.Frame(self.mid_panel, bg="#050505"); self.ly_synced_f.place(relx=0, rely=0, relwidth=0.74, relheight=0.6)
        self.ly_prev = tk.Label(self.ly_synced_f, text="", fg="#222", bg="#050505", font=("Arial", 11)); self.ly_prev.place(relx=0.5, rely=0.15, anchor="center")
        self.ly_curr = tk.Label(self.ly_synced_f, text="READY", fg=ACCENT, bg="#050505", font=("Arial", 30, "bold"), wraplength=550); self.ly_curr.place(relx=0.5, rely=0.45, anchor="center")
        self.ly_next = tk.Label(self.ly_synced_f, text="", fg="#555", bg="#050505", font=("Arial", 18, "bold"), wraplength=500); self.ly_next.place(relx=0.5, rely=0.75, anchor="center")
        self.scope_canvas = tk.Canvas(self.mid_panel, bg="#050505", height=60, highlightthickness=0); self.scope_canvas.place(relx=0, rely=0.65, relwidth=0.74, relheight=0.35)
        
        self.ly_full_f = tk.Frame(self.mid_panel, bg="#080808"); self.ly_full_f.place(relx=0.75, rely=0, relwidth=0.25, relheight=1)
        self.ly_txt = tk.Text(self.ly_full_f, bg="#080808", fg=TEXT_DIM, font=("Arial", 11), borderwidth=0, wrap=tk.WORD, cursor="hand2", state=tk.DISABLED); self.ly_txt.pack(fill=tk.BOTH, expand=True, padx=8, pady=8)
        self.ly_txt.tag_configure("highlight", background="#1a3328"); self.ly_txt.bind("<Button-1>", self.on_lyrics_click)
        self.btn_edit_lyrics = tk.Button(self.ly_full_f, text="EDIT LYRICS", command=self.toggle_lyrics_edit, bg="#222", fg=ACCENT, font=("Arial", 8, "bold"), borderwidth=1, relief=tk.FLAT); self.btn_edit_lyrics.pack(fill=tk.X, padx=8, pady=(0,8))

        self.load_ovl = tk.Frame(self.root, bg="#000"); self.load_lbl = tk.Label(self.load_ovl, text="LOADING...", fg=ACCENT, bg="#000", font=("Impact", 40)); self.load_lbl.place(relx=0.5, rely=0.5, anchor="center")

    def on_click_wave(self, event):
        if self.duration_ms > 0:
            target = (event.x / event.widget.winfo_width()) * self.duration_ms; self.play_pos_ms = float(target)
            if self.is_playing: self.play_from(target, ignore_count_in=True)
            else: self.update_ui_elements(); self.draw_all_waves(); self.update_lyrics_display()
        self.root.focus_force()

    def on_select(self, event):
        idx = self.listbox.curselection()
        if not idx: return
        if self.is_lyrics_editing:
            res = messagebox.askyesnocancel("StemQuina Editor", "Chcete uložiť zmeny v Lyrics pred načítaním novej skladby?")
            if res is True: self.toggle_lyrics_edit() 
            elif res is False: self.force_close_editor()
            else: return 
        self.load_ovl.place(relx=0, rely=0, relwidth=1, relheight=1); self.load_ovl.lift(); self.root.update()
        name = self.listbox.get(idx); threading.Thread(target=self._load_thread, args=(name,), daemon=True).start()

    def force_close_editor(self):
        self.is_lyrics_editing = False; self.ly_synced_f.place_configure(relwidth=0.74); self.ly_full_f.place_configure(relwidth=0.25, relx=0.75)
        self.ly_txt.config(state=tk.DISABLED, bg="#080808", fg=TEXT_DIM); self.btn_edit_lyrics.config(text="EDIT LYRICS", bg="#222", fg=ACCENT)
        self.ly_txt.unbind("<Control-Key-t>"); self.ly_txt.unbind("<Control-Key-T>")

    def _load_thread(self, name):
        pygame.mixer.stop(); t_dir = self.db_path / name; stems_dir = t_dir / "stems"
        stems_found = sorted([f.name for f in stems_dir.glob("*.mp3")]) if stems_dir.exists() else []
        self.root.after(0, lambda: self._update_stem_menus(["NONE"] + stems_found))
        
        orig = next(t_dir.glob("*.mp3"), None); lrc = next(t_dir.glob("*.lrc"), Path("none"))
        meta_p = t_dir / "metadata.json"; saved_mappings = ["NONE"] * 5
        if meta_p.exists():
            with open(meta_p, "r", encoding="utf-8") as f:
                data = json.load(f); raw_paths = data.get("track_mappings", ["NONE"]*5)
                for i, rp in enumerate(raw_paths):
                    if rp != "NONE": saved_mappings[i] = Path(rp).name

        final_mappings = ["NONE"] * 5; final_mappings[0] = orig.name if orig else "NONE"
        available_stems = list(stems_found); keywords = ["drum", "bass", "other", "vocal"]
        
        for i in range(1, 5):
            if saved_mappings[i] != "NONE" and saved_mappings[i] in available_stems:
                final_mappings[i] = saved_mappings[i]; available_stems.remove(saved_mappings[i])
            else:
                kw = keywords[i-1]; found = next((s for s in available_stems if kw in s.lower()), None)
                if found: final_mappings[i] = found; available_stems.remove(found)

        for i in range(1, 5):
            if final_mappings[i] == "NONE" and available_stems: final_mappings[i] = available_stems.pop(0)

        new_audio = [None] * 5; new_waves = [None] * 5; new_full = [None] * 5; dur = 0
        paths = [orig] + [(stems_dir / f if f != "NONE" else None) for f in final_mappings[1:]]
        
        for i, p in enumerate(paths):
            if p and p.exists():
                seg = AudioSegment.from_file(str(p)).set_frame_rate(44100)
                new_audio[i] = seg; new_full[i] = np.array(seg.get_array_of_samples())
                if i == 0: dur = len(seg)
                smp = new_full[i]; step = max(1, len(smp)//3000); new_waves[i] = smp[::step].astype(float) / (np.max(np.abs(smp)) if len(smp)>0 else 1)
        
        self.root.after(0, lambda: self._finalize_load(name, new_audio, new_waves, new_full, dur, lrc, orig, final_mappings))

    def _update_stem_menus(self, options):
        self.stem_options = options
        for om, var in zip(self.option_menus, self.track_mappings[1:]):
            menu = om["menu"]; menu.delete(0, "end")
            for o in options: menu.add_command(label=o, command=tk._setit(var, o, lambda v, idx=self.option_menus.index(om)+1: self.on_stem_change(idx, v)))

    def _finalize_load(self, name, audio, waves, full, dur, lrc, orig, mappings):
        self.is_playing = False; pygame.mixer.stop(); self.play_pos_ms = 0.0; self.playback_speed.set(1.0); self.is_counting = False; self.count_in_var.set(False)
        self.loop_a = None; self.loop_b = None; self.btn_play.config(text=" ▶ PLAY ", bg=ACCENT)
        self.current_track_name = name; self.audio_segments = audio; self.waveform_cache = waves; self.full_samples = full; self.duration_ms = dur
        for i, m in enumerate(mappings): self.track_mappings[i].set(m)
        self.load_metadata(name); self.load_lyrics_data(lrc); self.save_metadata()
        if orig: self.load_cover(orig); self.draw_all_waves(); self.refresh_marker_ui(); self.update_ui_elements(); self.load_ovl.place_forget()
        self.root.focus_force()

    def on_stem_change(self, idx, filename):
        if filename == "NONE":
            self.audio_segments[idx] = None; self.waveform_cache[idx] = None; self.full_samples[idx] = None
            self.draw_all_waves(); self.save_metadata()
            if self.is_playing: self.play_from(self.play_pos_ms, ignore_count_in=True)
        else:
            threading.Thread(target=self._reload_single_stem, args=(idx, filename), daemon=True).start()

    def _reload_single_stem(self, idx, filename):
        p = self.db_path / self.current_track_name / "stems" / filename
        if p.exists():
            seg = AudioSegment.from_file(str(p)).set_frame_rate(44100)
            self.audio_segments[idx] = seg; self.full_samples[idx] = np.array(seg.get_array_of_samples())
            smp = self.full_samples[idx]; step = max(1, len(smp)//3000)
            self.waveform_cache[idx] = smp[::step].astype(float) / (np.max(np.abs(smp)) if len(smp)>0 else 1)
            self.root.after(0, self.draw_all_waves); self.root.after(0, lambda: self.update_mix(idx)); self.save_metadata()
            if self.is_playing: self.root.after(0, lambda: self.play_from(self.play_pos_ms, ignore_count_in=True))

    def toggle(self):
        if self.duration_ms > 0:
            if self.is_playing: self.is_playing = False; pygame.mixer.stop(); self.btn_play.config(text=" ▶ PLAY ", bg=ACCENT)
            elif not self.is_counting: self.play_from(self.play_pos_ms)

    def play_from(self, ms, ignore_count_in=False):
        pygame.mixer.stop(); ms = float(max(0, ms)); self.play_pos_ms = ms
        if not ignore_count_in and self.count_in_var.get():
            threading.Thread(target=self._run_count_in, args=(ms,), daemon=True).start()
        else: self._start_audio_logic(ms)

    def _run_count_in(self, target_ms):
        self.is_counting = True; clk = self.create_beep(1000, 70)
        for i in range(4):
            if not self.is_counting: return
            self.root.after(0, lambda x=4-i: self.ly_curr.config(text=f"COUNT: {x}", fg="orange"))
            clk.play(); time.sleep(0.6)
        self.is_counting = False; self.root.after(0, lambda: self._start_audio_logic(target_ms))

    def _start_audio_logic(self, ms):
        speed = self.playback_speed.get(); prep = []
        for i, seg in enumerate(self.audio_segments):
            if seg:
                shifted = seg._spawn(seg.raw_data, overrides={'frame_rate': int(seg.frame_rate * speed)}).set_frame_rate(44100)
                idx = int(ms / speed); prep.append((i, pygame.mixer.Sound(buffer=shifted[idx:].raw_data)))
        self.start_time_ref = time.time() - (ms / (1000.0 * speed))
        for idx, snd in prep: pygame.mixer.Channel(idx).play(snd); self.update_mix(idx)
        self.is_playing = True; self.btn_play.config(text=" ⏸ PAUSE ", bg="#ffcc00")

    def stop_logic(self):
        now = time.time(); self.play_pos_ms = 0.0 if now - self.last_stop_click_time < 0.5 else self.play_pos_ms
        self.is_playing = False; self.is_counting = False; pygame.mixer.stop()
        self.btn_play.config(text=" ▶ PLAY ", bg=ACCENT); self.last_stop_click_time = now
        self.update_ui_elements(); self.draw_all_waves()

    def change_speed(self, delta):
        new_speed = round(max(0.5, min(2.0, self.playback_speed.get() + delta)), 1); self.playback_speed.set(new_speed)
        if self.is_playing: self.play_from(self.play_pos_ms, ignore_count_in=True)

    def seek(self, ms_delta):
        target = max(0, min(self.duration_ms, self.play_pos_ms + ms_delta)); self.play_pos_ms = target
        if self.is_playing: self.play_from(target, ignore_count_in=True)
        else: self.update_ui_elements(); self.draw_all_waves(); self.update_lyrics_display()

    def nudge_loop(self, type, delta):
        if type == 'a' and self.loop_a is not None: self.loop_a = max(0, self.loop_a + delta)
        elif type == 'b' and self.loop_b is not None: self.loop_b = min(self.duration_ms, self.loop_b + delta)
        self.save_metadata(); self.draw_all_waves(); self.update_ui_elements()

    def nudge_marker(self, idx, delta):
        old_ms = self.markers[idx]; new_ms = max(0, min(self.duration_ms, old_ms + delta))
        if old_ms in self.marker_labels: self.marker_labels[new_ms] = self.marker_labels.pop(old_ms)
        self.markers[idx] = new_ms; self.save_metadata(); self.draw_all_waves()
        if idx in self.marker_time_labels: self.marker_time_labels[idx].config(text=self.format_ms(new_ms))

    def clear_loop(self): self.loop_a = None; self.loop_b = None; self.save_metadata(); self.draw_all_waves(); self.update_ui_elements()

    def set_loop_a(self, event):
        self.loop_a = (event.x / event.widget.winfo_width()) * self.duration_ms; self.save_metadata(); self.draw_all_waves(); self.update_ui_elements()

    def set_loop_b(self, event):
        self.loop_b = (event.x / event.widget.winfo_width()) * self.duration_ms; self.save_metadata(); self.draw_all_waves(); self.update_ui_elements()

    def update_loop(self):
        if self.is_playing:
            speed = self.playback_speed.get(); self.play_pos_ms = (time.time() - self.start_time_ref) * 1000.0 * speed
            if self.loop_a is not None and self.loop_b is not None:
                if self.loop_a <= self.play_pos_ms >= self.loop_b:
                    if self.play_pos_ms < self.loop_b + 200: self.play_from(self.loop_a, ignore_count_in=True)
            if self.play_pos_ms >= self.duration_ms:
                if self.repeat_var.get(): self.play_from(0, ignore_count_in=True)
                else: self.stop_logic(); self.play_pos_ms = 0.0; self.update_ui_elements(); self.draw_all_waves()
            self.update_ui_elements(); self.update_lyrics_display()
        self.draw_digital_eq(); self.draw_mini_scopes(); self.root.after(20, self.update_loop)

    def draw_digital_eq(self):
        self.scope_canvas.delete("all"); w_b, h_b = self.scope_canvas.winfo_width(), self.scope_canvas.winfo_height()
        if w_b < 10: return
        self.eq_peaks *= 0.92 
        if self.is_playing and self.full_samples[0] is not None:
            idx = int((self.play_pos_ms / 1000.0) * 44100); chunk = 2048
            if idx + chunk < len(self.full_samples[0]):
                fft_res = np.abs(np.fft.rfft(self.full_samples[0][idx : idx + chunk]))[:chunk//2]
                new_vals = [ (np.mean(b)**1.4) * 0.4 for b in np.array_split(np.log10(fft_res + 1), 20)]
                self.eq_peaks = np.maximum(self.eq_peaks, new_vals)
        bw = (w_b / 20) - 2
        for i, v in enumerate(self.eq_peaks):
            h = min(h_b, v * h_b * 0.4); self.scope_canvas.create_rectangle(i*(w_b/20)+1, h_b-h, i*(w_b/20)+1+bw, h_b, fill="#1a3328", outline="")

    def draw_mini_scopes(self):
        for i, ms in enumerate(self.mini_scopes):
            ms.delete("all"); w, h = 60, 35
            if self.waveform_cache[i] is not None and self.duration_ms > 0:
                idx = int((self.play_pos_ms / self.duration_ms) * len(self.waveform_cache[i]))
                chunk = self.waveform_cache[i][max(0, idx-20):idx+20]
                if len(chunk) > 1:
                    pts = []
                    for x, v in enumerate(chunk): pts.extend([x*(w/len(chunk)), h/2-(v*h/2*self.vols[i].get())])
                    ms.create_line(pts, fill=COLORS[i] if not self.mutes[i].get() else "#333", width=1)
            if self.current_solo_idx == i: ms.create_rectangle(1,1,w-1,h-1,outline="orange")

    def update_ui_elements(self):
        if self.duration_ms <= 0: return
        self.lbl_a.config(text=self.format_ms(self.loop_a)); self.lbl_b.config(text=self.format_ms(self.loop_b))
        for i, canv in enumerate(self.canvases):
            x = (self.play_pos_ms / self.duration_ms) * canv.winfo_width(); canv.coords(self.playheads[i], x, 0, x, 35)
        tw = self.marker_canvas.winfo_width()
        if tw > 1:
            tx = (self.play_pos_ms / self.duration_ms) * tw
            self.marker_canvas.delete("ph"); self.marker_canvas.create_line(tx, 0, tx, 25, fill="white", width=2, tags="ph")
        c, t = int(self.play_pos_ms//1000), int(self.duration_ms//1000); rem = max(0, t - c)
        self.time_label.config(text=f"{c//60:02}:{c%60:02} / {t//60:02}:{t%60:02} / -{rem//60:02}:{rem%60:02}")

    def draw_all_waves(self):
        w = self.canvases[0].winfo_width(); w = 800 if w < 10 else w; self.marker_canvas.delete("all")
        for i in range(5):
            canv = self.canvases[i]; canv.delete("all")
            if self.waveform_cache[i] is not None:
                idx = np.linspace(0, len(self.waveform_cache[i])-1, w).astype(int)
                coords = []; [coords.extend([x, 17-(v*15), x, 17+(v*15)]) for x, v in enumerate(self.waveform_cache[i][idx])]
                canv.create_line(coords, fill=COLORS[i], width=1)
            if self.loop_a: ax=(self.loop_a/self.duration_ms)*w if self.duration_ms > 0 else 0; canv.create_line(ax,0,ax,35,fill="orange",width=2)
            if self.loop_b: bx=(self.loop_b/self.duration_ms)*w if self.duration_ms > 0 else 0; canv.create_line(bx,0,bx,35,fill="orange",width=2)
            for m in self.markers: 
                mx=(m/self.duration_ms)*w if self.duration_ms > 0 else 0; canv.create_line(mx,0,mx,35,fill="#333",width=1)
            if self.duration_ms > 0:
                px=(self.play_pos_ms/self.duration_ms)*w; self.playheads[i]=canv.create_line(px,0,px,35,fill="white",width=1)
        
        if self.duration_ms > 0:
            for j, m in enumerate(self.markers):
                mx=(m/self.duration_ms)*w; txt=f" {j+1}: {self.marker_labels.get(m,'')} "; y=2 if j%2==0 else 12
                self.marker_canvas.create_text(mx+2, y, text=txt, fill=ACCENT, font=("Arial", 9, "bold"), anchor="nw"); self.marker_canvas.create_line(mx,0,mx,25,fill=ACCENT,width=1)

    def refresh_marker_ui(self):
        for w in self.mark_container.winfo_children(): w.destroy()
        self.marker_time_labels = {}
        for i, ms in enumerate(self.markers):
            f = tk.Frame(self.mark_container, bg=BG_CARD); f.pack(side=tk.LEFT, padx=3)
            b_m = tk.Button(f, text="-", bg="#222", fg="#888", width=1, font=("Arial", 8), relief=tk.FLAT); b_m.pack(side=tk.LEFT)
            b_m.bind("<ButtonPress-1>", lambda e, idx=i: self.start_nudge(self.nudge_marker, idx, -50)); b_m.bind("<ButtonRelease-1>", self.stop_nudge)
            inf = tk.Frame(f, bg=BG_CARD); inf.pack(side=tk.LEFT, padx=1)
            tk.Label(inf, text=f"{i+1}:", fg=ACCENT, bg=BG_CARD, font=("Arial", 9, "bold")).pack()
            self.marker_time_labels[i] = tk.Label(inf, text=self.format_ms(ms), fg="#555", bg=BG_CARD, font=("Arial", 7)); self.marker_time_labels[i].pack()
            e = tk.Entry(f, bg="#111", fg="#ccc", font=("Arial", 10), width=10, borderwidth=0); e.insert(0, self.marker_labels.get(ms, "")); e.pack(side=tk.LEFT, padx=2)
            e.bind("<Return>", lambda ev: self.root.focus_set()); e.bind("<FocusOut>", lambda ev, m=ms, ent=e: self.save_marker_text(m, ent))
            b_p = tk.Button(f, text="+", bg="#222", fg="#888", width=1, font=("Arial", 8), relief=tk.FLAT); b_p.pack(side=tk.LEFT)
            b_p.bind("<ButtonPress-1>", lambda e, idx=i: self.start_nudge(self.nudge_marker, idx, 50)); b_p.bind("<ButtonRelease-1>", self.stop_nudge)
            tk.Button(f, text="×", command=lambda m=ms: self.delete_marker(m), bg="#331111", fg="red", width=1, font=("Arial", 8, "bold"), relief=tk.FLAT).pack(side=tk.LEFT, padx=2)

    def on_lyrics_click(self, event):
        idx_str = self.ly_txt.index(f"@{event.x},{event.y}"); line_idx = int(idx_str.split(".")[0]) - 1
        if self.is_lyrics_editing:
            line_text = self.ly_txt.get(f"{line_idx+1}.0", f"{line_idx+1}.end"); match = re.search(r'\[(\d+):(\d+\.\d+)\]', line_text)
            if match:
                target = (int(match.group(1))*60 + float(match.group(2)))*1000; self.play_pos_ms = target
                if self.is_playing: self.play_from(target, ignore_count_in=True)
                else: self.update_ui_elements(); self.draw_all_waves(); self.update_lyrics_display()
            return
        if 0 <= line_idx < len(self.lyrics_data):
            target = float(self.lyrics_data[line_idx]['ms']); self.play_pos_ms = target
            if self.is_playing: self.play_from(target, ignore_count_in=True)
            else: self.update_ui_elements(); self.draw_all_waves(); self.update_lyrics_display()

    def toggle_lyrics_edit(self):
        if not self.current_track_name: return
        lrc_p = self.db_path / self.current_track_name / f"{self.current_track_name}.lrc"
        if not self.is_lyrics_editing:
            self.is_lyrics_editing = True; self.ly_synced_f.place_configure(relwidth=0.55); self.ly_full_f.place_configure(relwidth=0.44, relx=0.56)
            self.ly_txt.config(state=tk.NORMAL, bg="#000", fg="#fff", insertbackground="white"); self.btn_edit_lyrics.config(text="SAVE & CLOSE", bg=ACCENT, fg="#000")
            if lrc_p.exists(): self.ly_txt.delete('1.0', tk.END); self.ly_txt.insert('1.0', lrc_p.read_text(encoding='utf-8'))
            self.ly_txt.bind("<Control-Key-t>", self.lyrics_stamp); self.ly_txt.bind("<Control-Key-T>", self.lyrics_stamp); self.ly_txt.focus_set()
        else:
            content = self.ly_txt.get("1.0", tk.END).strip(); lrc_p.write_text(content, encoding="utf-8"); self.is_lyrics_editing = False
            self.ly_synced_f.place_configure(relwidth=0.74); self.ly_full_f.place_configure(relwidth=0.25, relx=0.75)
            self.ly_txt.config(state=tk.DISABLED, bg="#080808", fg=TEXT_DIM); self.btn_edit_lyrics.config(text="EDIT LYRICS", bg="#222", fg=ACCENT)
            self.ly_txt.unbind("<Control-Key-t>"); self.ly_txt.unbind("<Control-Key-T>"); self.load_lyrics_data(lrc_p)

    def lyrics_stamp(self, event=None):
        m, s = int(self.play_pos_ms//60000), (self.play_pos_ms%60000)/1000
        stamp = f"[{m:02}:{s:05.2f}]"; line_idx = self.ly_txt.index(tk.INSERT).split('.')[0]; line_text = self.ly_txt.get(f"{line_idx}.0", f"{line_idx}.end")
        if line_text.startswith("["):
            new_line = re.sub(r'\[.*?\]', stamp, line_text, count=1); self.ly_txt.delete(f"{line_idx}.0", f"{line_idx}.end"); self.ly_txt.insert(f"{line_idx}.0", new_line)
        else: self.ly_txt.insert(f"{line_idx}.0", stamp)
        self.ly_txt.mark_set("insert", f"{int(line_idx)+1}.0"); return "break"

    def load_metadata(self, name):
        p = self.db_path / name / "metadata.json"; self.markers = []; self.marker_labels = {}; self.loop_a = None; self.loop_b = None
        if p.exists():
            with open(p, "r", encoding="utf-8") as f:
                data = json.load(f); [self.track_names[i].set(v) for i,v in enumerate(data.get("track_names", [])) if i<5]
                [self.vols[i].set(v) for i,v in enumerate(data.get("volumes", [])) if i<5]; [self.mutes[i].set(v) for i,v in enumerate(data.get("mutes", [])) if i<5]
                for m in data.get("markers", []): self.markers.append(m["ms"]); self.marker_labels[m["ms"]] = m["label"]
                self.loop_a = data.get("loop_a"); self.loop_b = data.get("loop_b")
        self.update_all_mixes()

    def save_metadata(self):
        if not self.current_track_name: return
        song_rel = f".\\database\\{self.current_track_name}"
        mappings = []
        for i, m in enumerate(self.track_mappings):
            fname = m.get()
            if fname == "NONE": mappings.append("NONE")
            elif i == 0: mappings.append(f"{song_rel}\\{fname}")
            else: mappings.append(f"{song_rel}\\stems\\{fname}")
        d = {"track_names": [n.get() for n in self.track_names], "volumes": [v.get() for v in self.vols], "mutes": [m.get() for m in self.mutes], 
             "markers": [{"ms": ms, "label": self.marker_labels.get(ms, "")} for ms in self.markers], "loop_a": self.loop_a, "loop_b": self.loop_b,
             "track_mappings": mappings}
        with open(self.db_path/self.current_track_name/"metadata.json", "w", encoding="utf-8") as f: json.dump(d, f, indent=4)

    def load_lyrics_data(self, path):
        self.lyrics_data = []; [self.lyrics_data.append({'ms': (int(m.group(1))*60 + float(m.group(2)))*1000, 'text': m.group(3).strip()}) for line in path.read_text(encoding='utf-8').splitlines() if (m := re.search(r'\[(\d+):(\d+\.\d+)\](.*)', line))] if path.exists() else None
        self.ly_txt.config(state=tk.NORMAL); self.ly_txt.delete('1.0', tk.END); [self.ly_txt.insert(tk.END, l['text'] + "\n") for l in self.lyrics_data]
        if not self.is_lyrics_editing: self.ly_txt.config(state=tk.DISABLED)

    def update_lyrics_display(self):
        idx = -1; [idx := i for i, en in enumerate(self.lyrics_data) if self.play_pos_ms >= en['ms']]
        if idx != self.current_lrc_idx:
            self.current_lrc_idx = idx
            t = [self.lyrics_data[idx-1]['text'] if idx > 0 else "", self.lyrics_data[idx]['text'] if idx >= 0 else "READY", self.lyrics_data[idx+1]['text'] if idx < len(self.lyrics_data)-1 else ""]
            self.ly_prev.config(text=t[0]); self.ly_curr.config(text=t[1]); self.ly_next.config(text=t[2]); self.ly_txt.tag_remove("highlight", "1.0", tk.END)
            if idx >= 0: self.ly_txt.tag_add("highlight", f"{idx+1}.0", f"{idx+1}.end"); [self.ly_txt.see(f"{idx+1}.0") if not self.is_lyrics_editing else None]

    def update_mix(self, i): pygame.mixer.Channel(i).set_volume(float(0 if self.mutes[i].get() else self.vols[i].get() * self.master_vol.get()))
    def update_all_mixes(self): [self.update_mix(i) for i in range(5)]
    def solo_track(self, idx):
        if self.current_solo_idx == idx: [self.mutes[i].set(self.pre_solo_mutes[i]) for i in range(5)]; self.current_solo_idx = None
        else: self.pre_solo_mutes = [m.get() for m in self.mutes]; [self.mutes[i].set(i != idx) for i in range(5)]; self.current_solo_idx = idx
        self.update_all_mixes()
    def toggle_mute(self, idx): self.mutes[idx].set(not self.mutes[idx].get()); self.update_mix(idx); self.save_metadata()
    def jump_to_marker(self, idx):
        if 0 <= idx < len(self.markers): t=float(self.markers[idx]); self.play_pos_ms=t; self.play_from(t, ignore_count_in=True) if self.is_playing else self.update_ui_elements()
    def delete_marker(self, ms): self.markers.remove(ms); del self.marker_labels[ms]; self.save_metadata(); self.refresh_marker_ui(); self.draw_all_waves()
    def save_marker_text(self, ms, ent): self.marker_labels[ms] = ent.get(); self.save_metadata(); self.draw_all_waves(); self.root.focus_force()
    def refresh_list(self): self.listbox.delete(0, tk.END); [self.listbox.insert(tk.END, d.name) for d in sorted([x for x in self.db_path.iterdir() if x.is_dir()])] if self.db_path.exists() else None
    def load_cover(self, p):
        try:
            for tag in ID3(p).values():
                if isinstance(tag, APIC): 
                    img = Image.open(BytesIO(tag.data)).resize((110, 110)); ph = ImageTk.PhotoImage(img)
                    self.cover_canvas.create_image(55, 55, image=ph); self.cover_canvas.image = ph; return
        except: pass
        self.cover_canvas.delete("all")
    def on_resize_event(self, event): 
        if event.widget == self.root: self.root.after(150, self.draw_all_waves)
    def add_marker(self):
        if self.duration_ms > 0:
            ms = round(self.play_pos_ms, 0)
            if ms not in self.markers: self.markers.append(ms); self.markers.sort(); self.marker_labels[ms] = f"Part {len(self.markers)}"; self.save_metadata(); self.refresh_marker_ui(); self.draw_all_waves()

if __name__ == "__main__":
    root = tk.Tk(); app = UltimatePlayer(root); root.mainloop()