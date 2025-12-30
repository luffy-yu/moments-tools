"""
Image Mosaic - Add mosaic/blur effects to images.
Supports drawing rectangles, multiple mosaic styles, live preview, and batch processing.
"""

import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from PIL import Image, ImageTk, ImageFilter
import cv2
import numpy as np
import os
import json
import re


CONFIG_FILE = "image_mosaic_config.json"


class NamingDialog:
    """Dialog for configuring output filename pattern with regex support."""

    def __init__(self, parent, sample_files, current_pattern=None, current_replacement=None, on_save_config=None):
        self.result = None
        self.sample_files = sample_files[:10]
        self.on_save_config = on_save_config

        self.dialog = tk.Toplevel(parent)
        self.dialog.title("Output Filename Configuration")
        self.dialog.geometry("700x600")
        self.dialog.minsize(600, 500)
        self.dialog.transient(parent)
        self.dialog.grab_set()

        self.pattern = current_pattern or r"(.+)"
        self.replacement = current_replacement or r"\1_mosaic"

        self.setup_ui()
        self.update_preview()

        self.dialog.update_idletasks()
        x = parent.winfo_x() + (parent.winfo_width() - self.dialog.winfo_width()) // 2
        y = parent.winfo_y() + (parent.winfo_height() - self.dialog.winfo_height()) // 2
        self.dialog.geometry(f"+{x}+{y}")

    def setup_ui(self):
        main_frame = ttk.Frame(self.dialog, padding="10")
        main_frame.pack(fill=tk.BOTH, expand=True)

        button_frame = ttk.Frame(main_frame)
        button_frame.pack(side=tk.BOTTOM, fill=tk.X, pady=(10, 0))

        ttk.Button(button_frame, text="Cancel", command=self.cancel).pack(side=tk.RIGHT, padx=5)
        ttk.Button(button_frame, text="Apply", command=self.apply).pack(side=tk.RIGHT, padx=5)
        ttk.Button(button_frame, text="Reset to Default", command=self.reset_default).pack(side=tk.LEFT, padx=5)

        self.error_var = tk.StringVar()
        self.error_label = ttk.Label(main_frame, textvariable=self.error_var, foreground="red")
        self.error_label.pack(side=tk.BOTTOM, fill=tk.X)

        instructions = ttk.LabelFrame(main_frame, text="Instructions", padding="10")
        instructions.pack(fill=tk.X, pady=(0, 10))

        help_text = (
            "Use regex to transform input filenames to output filenames.\n"
            "The pattern matches against the filename (without extension).\n"
            "The replacement defines the new filename (extension is preserved).\n\n"
            "Examples:\n"
            "  - Pattern: (.+)  Replacement: \\1_mosaic  ->  'image' becomes 'image_mosaic'\n"
            "  - Pattern: (.+)  Replacement: censored_\\1  ->  'image' becomes 'censored_image'"
        )
        ttk.Label(instructions, text=help_text, justify=tk.LEFT).pack(anchor=tk.W)

        pattern_frame = ttk.LabelFrame(main_frame, text="Regex Pattern (match against filename)", padding="10")
        pattern_frame.pack(fill=tk.X, pady=(0, 10))

        self.pattern_var = tk.StringVar(value=self.pattern)
        self.pattern_entry = ttk.Entry(pattern_frame, textvariable=self.pattern_var, font=("Consolas", 11))
        self.pattern_entry.pack(fill=tk.X)
        self.pattern_var.trace_add("write", lambda *_: self.update_preview())

        replacement_frame = ttk.LabelFrame(main_frame, text="Replacement Pattern (use \\1, \\2 for groups)", padding="10")
        replacement_frame.pack(fill=tk.X, pady=(0, 10))

        self.replacement_var = tk.StringVar(value=self.replacement)
        self.replacement_entry = ttk.Entry(replacement_frame, textvariable=self.replacement_var, font=("Consolas", 11))
        self.replacement_entry.pack(fill=tk.X)
        self.replacement_var.trace_add("write", lambda *_: self.update_preview())

        preview_frame = ttk.LabelFrame(main_frame, text="Preview", padding="10")
        preview_frame.pack(fill=tk.BOTH, expand=True, pady=(0, 10))

        columns = ("input", "output", "status")
        self.preview_tree = ttk.Treeview(preview_frame, columns=columns, show="headings", height=6)
        self.preview_tree.heading("input", text="Input Filename")
        self.preview_tree.heading("output", text="Output Filename")
        self.preview_tree.heading("status", text="Status")
        self.preview_tree.column("input", width=250)
        self.preview_tree.column("output", width=250)
        self.preview_tree.column("status", width=100)

        scrollbar = ttk.Scrollbar(preview_frame, orient=tk.VERTICAL, command=self.preview_tree.yview)
        self.preview_tree.configure(yscrollcommand=scrollbar.set)

        self.preview_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

    def update_preview(self):
        for item in self.preview_tree.get_children():
            self.preview_tree.delete(item)

        pattern = self.pattern_var.get()
        replacement = self.replacement_var.get()

        self.error_var.set("")

        try:
            regex = re.compile(pattern)
        except re.error as e:
            self.error_var.set(f"Invalid regex pattern: {e}")
            return

        for filename in self.sample_files:
            name, ext = os.path.splitext(filename)

            try:
                if regex.search(name):
                    new_name = regex.sub(replacement, name)
                    output = f"{new_name}{ext}"
                    status = "OK"
                else:
                    output = f"{name}_mosaic{ext}"
                    status = "No match (default)"
            except re.error as e:
                output = "Error"
                status = str(e)

            self.preview_tree.insert("", tk.END, values=(filename, output, status))

    def reset_default(self):
        self.pattern_var.set(r"(.+)")
        self.replacement_var.set(r"\1_mosaic")

    def apply(self):
        pattern = self.pattern_var.get()
        replacement = self.replacement_var.get()

        try:
            re.compile(pattern)
        except re.error as e:
            messagebox.showerror("Error", f"Invalid regex pattern: {e}")
            return

        self.result = {
            "pattern": pattern,
            "replacement": replacement
        }

        if self.on_save_config:
            self.on_save_config(pattern, replacement)

        self.dialog.destroy()

    def cancel(self):
        self.result = None
        self.dialog.destroy()

    def show(self):
        self.dialog.wait_window()
        return self.result


class MosaicRect:
    """Represents a rectangle with mosaic effect."""

    def __init__(self, x1, y1, x2, y2, style="pixelate", block_size=10):
        self.x1 = min(x1, x2)
        self.y1 = min(y1, y2)
        self.x2 = max(x1, x2)
        self.y2 = max(y1, y2)
        self.style = style  # "pixelate", "blur", "black", "white"
        self.block_size = block_size

    def to_dict(self):
        return {
            "x1": self.x1,
            "y1": self.y1,
            "x2": self.x2,
            "y2": self.y2,
            "style": self.style,
            "block_size": self.block_size
        }

    @classmethod
    def from_dict(cls, data):
        return cls(
            data["x1"], data["y1"], data["x2"], data["y2"],
            data.get("style", "pixelate"),
            data.get("block_size", 10)
        )

    def contains_point(self, x, y):
        return self.x1 <= x <= self.x2 and self.y1 <= y <= self.y2

    def get_bounds(self):
        return (self.x1, self.y1, self.x2, self.y2)


class ImageMosaic:
    def __init__(self, root):
        self.root = root
        self.root.title("Image Mosaic - Add Mosaic Effects")
        self.root.geometry("1400x900")

        self.original_image = None
        self.cv_image = None
        self.current_file = None
        self.image_path = None

        # Mosaic rectangles
        self.rects = []
        self.selected_rect_index = -1

        # Drawing state
        self.drawing = False
        self.draw_start = None
        self.temp_rect = None

        # Display scaling
        self.scale_factor = 1.0
        self.offset_x = 0
        self.offset_y = 0

        # Mosaic settings
        self.current_style = tk.StringVar(value="pixelate")
        self.current_block_size = tk.IntVar(value=10)

        # Naming pattern
        self.naming_pattern = r"(.+)"
        self.naming_replacement = r"\1_mosaic"

        # Debounce timer
        self._update_timer = None

        self.setup_ui()
        self.load_config()

    def setup_ui(self):
        main_frame = ttk.Frame(self.root, padding="10")
        main_frame.pack(fill=tk.BOTH, expand=True)

        # Top toolbar
        toolbar = ttk.Frame(main_frame)
        toolbar.pack(fill=tk.X, pady=(0, 10))

        ttk.Button(toolbar, text="Open Image", command=self.open_image).pack(side=tk.LEFT, padx=5)
        ttk.Button(toolbar, text="Save Image", command=self.save_image).pack(side=tk.LEFT, padx=5)
        ttk.Button(toolbar, text="Batch Process", command=self.batch_process).pack(side=tk.LEFT, padx=5)

        ttk.Separator(toolbar, orient=tk.VERTICAL).pack(side=tk.LEFT, fill=tk.Y, padx=10)

        ttk.Button(toolbar, text="Save Config", command=self.save_config).pack(side=tk.LEFT, padx=5)
        ttk.Button(toolbar, text="Load Config", command=self.load_config_dialog).pack(side=tk.LEFT, padx=5)

        # Settings panel (left side)
        settings_panel = ttk.Frame(main_frame, width=300)
        settings_panel.pack(side=tk.LEFT, fill=tk.Y, padx=(0, 10))
        settings_panel.pack_propagate(False)

        # Mosaic style settings
        style_frame = ttk.LabelFrame(settings_panel, text="Mosaic Style", padding="10")
        style_frame.pack(fill=tk.X, pady=(0, 10))

        ttk.Label(style_frame, text="Effect:").pack(anchor=tk.W)
        styles = [("Pixelate", "pixelate"), ("Blur", "blur"), ("Black", "black"), ("White", "white")]
        for text, value in styles:
            ttk.Radiobutton(style_frame, text=text, variable=self.current_style,
                           value=value, command=self.on_style_change).pack(anchor=tk.W)

        ttk.Separator(style_frame, orient=tk.HORIZONTAL).pack(fill=tk.X, pady=10)

        size_frame = ttk.Frame(style_frame)
        size_frame.pack(fill=tk.X)
        ttk.Label(size_frame, text="Block Size:").pack(side=tk.LEFT)
        ttk.Scale(size_frame, from_=5, to=50, variable=self.current_block_size,
                  orient=tk.HORIZONTAL, command=lambda _: self.on_style_change()).pack(side=tk.LEFT, fill=tk.X, expand=True, padx=5)
        ttk.Label(size_frame, textvariable=self.current_block_size, width=3).pack(side=tk.LEFT)

        # Instructions
        instr_frame = ttk.LabelFrame(settings_panel, text="Instructions", padding="10")
        instr_frame.pack(fill=tk.X, pady=(0, 10))

        instructions = (
            "- Click and drag to draw a rectangle\n"
            "- Click on a rectangle to select it\n"
            "- Change style/size for selected rect\n"
            "- Use Delete button to remove selected"
        )
        ttk.Label(instr_frame, text=instructions, justify=tk.LEFT).pack(anchor=tk.W)

        # Rectangle list label - pack first with side=BOTTOM
        self.rect_count_var = tk.StringVar(value="No rectangles")
        ttk.Label(settings_panel, textvariable=self.rect_count_var).pack(side=tk.BOTTOM, anchor=tk.W, pady=5)

        # Delete button - pack with side=BOTTOM before rect list
        btn_frame = ttk.Frame(settings_panel)
        btn_frame.pack(side=tk.BOTTOM, fill=tk.X, pady=(0, 5))
        ttk.Button(btn_frame, text="Delete Selected", command=self.delete_selected_rect).pack(side=tk.LEFT, padx=2)
        ttk.Button(btn_frame, text="Clear All", command=self.clear_all_rects).pack(side=tk.LEFT, padx=2)

        # Rectangle list
        rect_frame = ttk.LabelFrame(settings_panel, text="Rectangles", padding="10")
        rect_frame.pack(fill=tk.BOTH, expand=True)

        self.rect_listbox = tk.Listbox(rect_frame, font=("Consolas", 9))
        rect_scrollbar = ttk.Scrollbar(rect_frame, orient=tk.VERTICAL, command=self.rect_listbox.yview)
        self.rect_listbox.configure(yscrollcommand=rect_scrollbar.set)

        self.rect_listbox.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        rect_scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        self.rect_listbox.bind('<<ListboxSelect>>', self.on_rect_select)

        # Preview panel (right side)
        preview_frame = ttk.LabelFrame(main_frame, text="Preview", padding="5")
        preview_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        self.canvas = tk.Canvas(preview_frame, bg="#2d2d2d", cursor="crosshair")
        self.canvas.pack(fill=tk.BOTH, expand=True)

        # Bind mouse events
        self.canvas.bind("<ButtonPress-1>", self.on_mouse_down)
        self.canvas.bind("<B1-Motion>", self.on_mouse_drag)
        self.canvas.bind("<ButtonRelease-1>", self.on_mouse_up)

        self.preview_info = ttk.Label(preview_frame, text="No image loaded")
        self.preview_info.pack(pady=5)

        # Status bar
        self.status_var = tk.StringVar(value="Ready. Open an image to start.")
        status_bar = ttk.Label(preview_frame, textvariable=self.status_var, relief=tk.SUNKEN)
        status_bar.pack(fill=tk.X, pady=(5, 0))

        # Bind resize
        self.root.bind('<Configure>', self.on_resize)

    def get_config(self):
        return {
            "rects": [r.to_dict() for r in self.rects],
            "current_style": self.current_style.get(),
            "current_block_size": self.current_block_size.get(),
            "naming_pattern": self.naming_pattern,
            "naming_replacement": self.naming_replacement
        }

    def set_config(self, config):
        if "rects" in config:
            self.rects = [MosaicRect.from_dict(r) for r in config["rects"]]
            self.update_rect_list()
        if "current_style" in config:
            self.current_style.set(config["current_style"])
        if "current_block_size" in config:
            self.current_block_size.set(config["current_block_size"])
        if "naming_pattern" in config:
            self.naming_pattern = config["naming_pattern"]
        if "naming_replacement" in config:
            self.naming_replacement = config["naming_replacement"]

    def save_config(self):
        config = self.get_config()

        filetypes = [("JSON files", "*.json"), ("All files", "*.*")]
        path = filedialog.asksaveasfilename(
            initialfile=CONFIG_FILE,
            defaultextension=".json",
            filetypes=filetypes
        )

        if path:
            try:
                with open(path, 'w') as f:
                    json.dump(config, f, indent=2)
                self.status_var.set(f"Config saved: {path}")
                messagebox.showinfo("Success", f"Configuration saved to:\n{path}")
            except Exception as e:
                messagebox.showerror("Error", f"Failed to save config: {e}")

    def load_config(self):
        if os.path.exists(CONFIG_FILE):
            try:
                with open(CONFIG_FILE, 'r') as f:
                    config = json.load(f)
                self.set_config(config)
                self.status_var.set(f"Loaded config from {CONFIG_FILE}")
            except Exception:
                pass

    def load_config_dialog(self):
        filetypes = [("JSON files", "*.json"), ("All files", "*.*")]
        path = filedialog.askopenfilename(filetypes=filetypes)

        if path:
            try:
                with open(path, 'r') as f:
                    config = json.load(f)
                self.set_config(config)
                self.status_var.set(f"Config loaded: {path}")
                messagebox.showinfo("Success", f"Configuration loaded from:\n{path}")
                self.update_preview()
            except Exception as e:
                messagebox.showerror("Error", f"Failed to load config: {e}")

    def save_naming_config(self, pattern, replacement):
        self.naming_pattern = pattern
        self.naming_replacement = replacement

        config = {}
        if os.path.exists(CONFIG_FILE):
            try:
                with open(CONFIG_FILE, 'r') as f:
                    config = json.load(f)
            except Exception:
                pass

        config["naming_pattern"] = pattern
        config["naming_replacement"] = replacement

        try:
            with open(CONFIG_FILE, 'w') as f:
                json.dump(config, f, indent=2)
        except Exception as e:
            print(f"Failed to save naming config: {e}")

    def open_image(self):
        filetypes = [
            ("Image files", "*.png *.jpg *.jpeg *.gif *.bmp *.tiff *.webp"),
            ("All files", "*.*")
        ]
        path = filedialog.askopenfilename(filetypes=filetypes)
        if path:
            self.load_image(path)

    def load_image(self, path):
        try:
            self.image_path = path
            self.current_file = os.path.basename(path)
            self.cv_image = cv2.imread(path)
            if self.cv_image is None:
                raise ValueError("Failed to load image")

            rgb = cv2.cvtColor(self.cv_image, cv2.COLOR_BGR2RGB)
            self.original_image = Image.fromarray(rgb)

            self.status_var.set(f"Loaded: {self.current_file} ({self.original_image.width}x{self.original_image.height})")
            self.update_preview()
        except Exception as e:
            messagebox.showerror("Error", f"Failed to load image: {e}")

    def canvas_to_image_coords(self, canvas_x, canvas_y):
        """Convert canvas coordinates to image coordinates."""
        if self.scale_factor == 0:
            return 0, 0
        img_x = int((canvas_x - self.offset_x) / self.scale_factor)
        img_y = int((canvas_y - self.offset_y) / self.scale_factor)
        return img_x, img_y

    def image_to_canvas_coords(self, img_x, img_y):
        """Convert image coordinates to canvas coordinates."""
        canvas_x = img_x * self.scale_factor + self.offset_x
        canvas_y = img_y * self.scale_factor + self.offset_y
        return canvas_x, canvas_y

    def on_mouse_down(self, event):
        if self.original_image is None:
            return

        img_x, img_y = self.canvas_to_image_coords(event.x, event.y)

        # Check if clicking on existing rect
        for i, rect in enumerate(self.rects):
            if rect.contains_point(img_x, img_y):
                self.selected_rect_index = i
                self.rect_listbox.selection_clear(0, tk.END)
                self.rect_listbox.selection_set(i)
                self.rect_listbox.see(i)
                # Update style controls to match selected rect
                self.current_style.set(rect.style)
                self.current_block_size.set(rect.block_size)
                self.update_preview()
                return

        # Start drawing new rect
        self.drawing = True
        self.draw_start = (img_x, img_y)
        self.selected_rect_index = -1
        self.rect_listbox.selection_clear(0, tk.END)

    def on_mouse_drag(self, event):
        if not self.drawing or self.original_image is None:
            return

        img_x, img_y = self.canvas_to_image_coords(event.x, event.y)

        # Clamp to image bounds
        img_x = max(0, min(img_x, self.original_image.width))
        img_y = max(0, min(img_y, self.original_image.height))

        self.temp_rect = MosaicRect(
            self.draw_start[0], self.draw_start[1],
            img_x, img_y,
            self.current_style.get(),
            self.current_block_size.get()
        )
        self.update_preview()

    def on_mouse_up(self, event):
        if not self.drawing or self.original_image is None:
            self.drawing = False
            return

        self.drawing = False

        if self.temp_rect:
            # Only add if rect has some size
            width = abs(self.temp_rect.x2 - self.temp_rect.x1)
            height = abs(self.temp_rect.y2 - self.temp_rect.y1)
            if width > 5 and height > 5:
                self.rects.append(self.temp_rect)
                self.selected_rect_index = len(self.rects) - 1
                self.update_rect_list()
                self.rect_listbox.selection_clear(0, tk.END)
                self.rect_listbox.selection_set(self.selected_rect_index)

        self.temp_rect = None
        self.update_preview()

    def on_rect_select(self, event):
        selection = self.rect_listbox.curselection()
        if selection:
            self.selected_rect_index = selection[0]
            rect = self.rects[self.selected_rect_index]
            self.current_style.set(rect.style)
            self.current_block_size.set(rect.block_size)
            self.update_preview()

    def on_style_change(self):
        if 0 <= self.selected_rect_index < len(self.rects):
            self.rects[self.selected_rect_index].style = self.current_style.get()
            self.rects[self.selected_rect_index].block_size = self.current_block_size.get()
            self.update_rect_list()

        if self._update_timer is not None:
            self.root.after_cancel(self._update_timer)
        self._update_timer = self.root.after(100, self.update_preview)

    def delete_selected_rect(self):
        if 0 <= self.selected_rect_index < len(self.rects):
            del self.rects[self.selected_rect_index]
            self.selected_rect_index = -1
            self.update_rect_list()
            self.update_preview()

    def clear_all_rects(self):
        if self.rects:
            if messagebox.askyesno("Confirm", "Delete all rectangles?"):
                self.rects = []
                self.selected_rect_index = -1
                self.update_rect_list()
                self.update_preview()

    def update_rect_list(self):
        self.rect_listbox.delete(0, tk.END)
        for i, rect in enumerate(self.rects):
            text = f"{i+1}. ({rect.x1},{rect.y1})-({rect.x2},{rect.y2}) [{rect.style}]"
            self.rect_listbox.insert(tk.END, text)

        self.rect_count_var.set(f"{len(self.rects)} rectangle(s)")

    def apply_mosaic_to_image(self, pil_image, rects, warn_out_of_bounds=False):
        """Apply mosaic effects to image."""
        img = pil_image.copy()
        img_width, img_height = img.size
        warnings = []

        for i, rect in enumerate(rects):
            x1, y1, x2, y2 = rect.x1, rect.y1, rect.x2, rect.y2

            # Check bounds
            if x1 >= img_width or y1 >= img_height or x2 <= 0 or y2 <= 0:
                if warn_out_of_bounds:
                    warnings.append(f"Rect {i+1} is completely out of bounds, skipping")
                continue

            # Clamp to image bounds
            orig_bounds = (x1, y1, x2, y2)
            x1 = max(0, x1)
            y1 = max(0, y1)
            x2 = min(img_width, x2)
            y2 = min(img_height, y2)

            if (x1, y1, x2, y2) != orig_bounds and warn_out_of_bounds:
                warnings.append(f"Rect {i+1} partially out of bounds, clamped to image")

            if x2 <= x1 or y2 <= y1:
                continue

            # Extract region
            region = img.crop((x1, y1, x2, y2))

            # Apply effect
            if rect.style == "pixelate":
                # Pixelate: shrink then enlarge
                block = max(1, rect.block_size)
                small_size = (max(1, (x2 - x1) // block), max(1, (y2 - y1) // block))
                region = region.resize(small_size, Image.Resampling.NEAREST)
                region = region.resize((x2 - x1, y2 - y1), Image.Resampling.NEAREST)
            elif rect.style == "blur":
                # Gaussian blur
                blur_radius = rect.block_size
                region = region.filter(ImageFilter.GaussianBlur(radius=blur_radius))
            elif rect.style == "black":
                region = Image.new('RGB', (x2 - x1, y2 - y1), (0, 0, 0))
            elif rect.style == "white":
                region = Image.new('RGB', (x2 - x1, y2 - y1), (255, 255, 255))

            # Paste back
            img.paste(region, (x1, y1))

        return img, warnings

    def update_preview(self):
        if self.original_image is None:
            return

        self.canvas.update_idletasks()
        canvas_w = self.canvas.winfo_width()
        canvas_h = self.canvas.winfo_height()

        if canvas_w <= 1 or canvas_h <= 1:
            return

        # Apply mosaic to get preview
        all_rects = self.rects[:]
        if self.temp_rect:
            all_rects.append(self.temp_rect)

        preview_img, _ = self.apply_mosaic_to_image(self.original_image, all_rects)

        # Scale to fit canvas
        img_w, img_h = preview_img.size
        self.scale_factor = min(canvas_w / img_w, canvas_h / img_h, 1.0)
        new_w = max(1, int(img_w * self.scale_factor))
        new_h = max(1, int(img_h * self.scale_factor))

        self.offset_x = (canvas_w - new_w) // 2
        self.offset_y = (canvas_h - new_h) // 2

        display_img = preview_img.resize((new_w, new_h), Image.Resampling.LANCZOS)
        self.preview_photo = ImageTk.PhotoImage(display_img)

        self.canvas.delete("all")
        self.canvas.create_image(
            canvas_w // 2, canvas_h // 2,
            image=self.preview_photo, anchor=tk.CENTER
        )

        # Draw rectangle outlines
        for i, rect in enumerate(all_rects):
            cx1, cy1 = self.image_to_canvas_coords(rect.x1, rect.y1)
            cx2, cy2 = self.image_to_canvas_coords(rect.x2, rect.y2)

            color = "yellow" if i == self.selected_rect_index else "red"
            if rect == self.temp_rect:
                color = "lime"

            self.canvas.create_rectangle(cx1, cy1, cx2, cy2, outline=color, width=2)

        self.preview_info.config(text=f"Size: {img_w} x {img_h} | Rects: {len(self.rects)} | Scale: {self.scale_factor:.1%}")

    def on_resize(self, event):
        if self.original_image:
            if self._update_timer is not None:
                self.root.after_cancel(self._update_timer)
            self._update_timer = self.root.after(100, self.update_preview)

    def get_output_filename(self, input_filename):
        name, ext = os.path.splitext(input_filename)

        try:
            regex = re.compile(self.naming_pattern)
            if regex.search(name):
                new_name = regex.sub(self.naming_replacement, name)
                return f"{new_name}{ext}"
        except re.error:
            pass

        return f"{name}_mosaic{ext}"

    def save_image(self):
        if self.original_image is None:
            messagebox.showwarning("Warning", "No image loaded.")
            return

        if not self.rects:
            messagebox.showwarning("Warning", "No mosaic rectangles defined.")
            return

        filetypes = [
            ("PNG files", "*.png"),
            ("JPEG files", "*.jpg *.jpeg"),
            ("All files", "*.*")
        ]

        initial_name = self.get_output_filename(self.current_file) if self.current_file else "mosaic.png"

        path = filedialog.asksaveasfilename(
            initialfile=initial_name,
            defaultextension=".png",
            filetypes=filetypes
        )

        if path:
            try:
                result_img, warnings = self.apply_mosaic_to_image(self.original_image, self.rects, warn_out_of_bounds=True)

                if warnings:
                    for w in warnings:
                        print(f"Warning: {w}")

                if path.lower().endswith(('.jpg', '.jpeg')):
                    result_img = result_img.convert('RGB')

                result_img.save(path)
                self.status_var.set(f"Saved: {path}")
                messagebox.showinfo("Success", f"Image saved to:\n{path}")
            except Exception as e:
                messagebox.showerror("Error", f"Failed to save image: {e}")

    def batch_process(self):
        if not self.rects:
            messagebox.showwarning("Warning", "No mosaic rectangles defined.\n\nDraw rectangles on the preview image first.")
            return

        # Select input folder
        input_dir = filedialog.askdirectory(title="Select Input Folder")
        if not input_dir:
            return

        # Select output folder
        output_dir = filedialog.askdirectory(title="Select Output Folder")
        if not output_dir:
            return

        # Get image files
        image_extensions = {'.png', '.jpg', '.jpeg', '.gif', '.bmp', '.tiff', '.webp'}
        image_files = sorted([
            f for f in os.listdir(input_dir)
            if os.path.splitext(f)[1].lower() in image_extensions
        ])

        if not image_files:
            messagebox.showwarning("Warning", "No image files found in the selected folder.")
            return

        # Show naming dialog
        naming_dialog = NamingDialog(
            self.root,
            image_files,
            self.naming_pattern,
            self.naming_replacement,
            on_save_config=self.save_naming_config
        )
        result = naming_dialog.show()

        if result is None:
            return

        self.naming_pattern = result["pattern"]
        self.naming_replacement = result["replacement"]

        # Confirm
        rect_info = "\n".join([f"  {i+1}. ({r.x1},{r.y1})-({r.x2},{r.y2}) [{r.style}]" for i, r in enumerate(self.rects[:5])])
        if len(self.rects) > 5:
            rect_info += f"\n  ... and {len(self.rects) - 5} more"

        confirm = messagebox.askyesno(
            "Confirm Batch Processing",
            f"Found {len(image_files)} images.\n\n"
            f"Rectangles ({len(self.rects)}):\n{rect_info}\n\n"
            f"Naming: '{self.naming_pattern}' -> '{self.naming_replacement}'\n\n"
            f"Note: Rectangles use absolute positions.\n"
            f"Out-of-bounds rectangles will be skipped or clamped.\n\n"
            f"Continue?"
        )

        if not confirm:
            return

        success_count = 0
        error_count = 0
        warning_files = []

        for i, filename in enumerate(image_files):
            self.status_var.set(f"Processing {i+1}/{len(image_files)}: {filename}")
            self.root.update()

            try:
                input_path = os.path.join(input_dir, filename)
                cv_img = cv2.imread(input_path)
                if cv_img is None:
                    raise ValueError("Failed to load image")

                rgb = cv2.cvtColor(cv_img, cv2.COLOR_BGR2RGB)
                pil_img = Image.fromarray(rgb)

                result_img, warnings = self.apply_mosaic_to_image(pil_img, self.rects, warn_out_of_bounds=True)

                if warnings:
                    warning_files.append((filename, warnings))
                    for w in warnings:
                        print(f"Warning [{filename}]: {w}")

                output_filename = self.get_output_filename(filename)
                output_path = os.path.join(output_dir, output_filename)

                if output_path.lower().endswith(('.jpg', '.jpeg')):
                    result_img = result_img.convert('RGB')

                result_img.save(output_path)
                success_count += 1

            except Exception as e:
                print(f"Error processing {filename}: {e}")
                error_count += 1

        self.status_var.set(f"Batch complete: {success_count} processed, {error_count} errors")

        warning_msg = ""
        if warning_files:
            warning_msg = f"\n\n{len(warning_files)} file(s) had out-of-bounds warnings (see console)."

        messagebox.showinfo(
            "Batch Complete",
            f"Processed {success_count} image(s).\n"
            f"Errors: {error_count}{warning_msg}\n\n"
            f"Output folder: {output_dir}"
        )


def main():
    root = tk.Tk()
    app = ImageMosaic(root)
    root.mainloop()


if __name__ == "__main__":
    main()
