"""
Image Clipper - Interactive GUI for cropping images using horizontal line detection.
Uses OpenCV to detect horizontal lines and allows selecting two lines to clip between.
Supports batch processing with adaptive line selection.
"""

import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from PIL import Image, ImageTk
import cv2
import numpy as np
import os
import json
import re


CONFIG_FILE = "image_clipper_config.json"


class NamingDialog:
    """Dialog for configuring output filename pattern with regex support."""

    def __init__(self, parent, sample_files, current_pattern=None, current_replacement=None, on_save_config=None):
        self.result = None
        self.sample_files = sample_files[:10]  # Limit preview samples
        self.on_save_config = on_save_config  # Callback to save config

        self.dialog = tk.Toplevel(parent)
        self.dialog.title("Output Filename Configuration")
        self.dialog.geometry("700x600")
        self.dialog.minsize(600, 500)  # Set minimum size to ensure buttons are visible
        self.dialog.transient(parent)
        self.dialog.grab_set()

        # Default patterns
        self.pattern = current_pattern or r"(.+)"
        self.replacement = current_replacement or r"\1_cropped"

        self.setup_ui()
        self.update_preview()

        # Center the dialog
        self.dialog.update_idletasks()
        x = parent.winfo_x() + (parent.winfo_width() - self.dialog.winfo_width()) // 2
        y = parent.winfo_y() + (parent.winfo_height() - self.dialog.winfo_height()) // 2
        self.dialog.geometry(f"+{x}+{y}")

    def setup_ui(self):
        main_frame = ttk.Frame(self.dialog, padding="10")
        main_frame.pack(fill=tk.BOTH, expand=True)

        # Buttons at bottom - pack first with side=BOTTOM to ensure they're always visible
        button_frame = ttk.Frame(main_frame)
        button_frame.pack(side=tk.BOTTOM, fill=tk.X, pady=(10, 0))

        ttk.Button(button_frame, text="Cancel", command=self.cancel).pack(side=tk.RIGHT, padx=5)
        ttk.Button(button_frame, text="Apply", command=self.apply).pack(side=tk.RIGHT, padx=5)
        ttk.Button(button_frame, text="Reset to Default", command=self.reset_default).pack(side=tk.LEFT, padx=5)

        # Error message - pack before preview so it stays visible
        self.error_var = tk.StringVar()
        self.error_label = ttk.Label(main_frame, textvariable=self.error_var, foreground="red")
        self.error_label.pack(side=tk.BOTTOM, fill=tk.X)

        # Instructions
        instructions = ttk.LabelFrame(main_frame, text="Instructions", padding="10")
        instructions.pack(fill=tk.X, pady=(0, 10))

        help_text = (
            "Use regex to transform input filenames to output filenames.\n"
            "The pattern matches against the filename (without extension).\n"
            "The replacement defines the new filename (extension is preserved).\n\n"
            "Examples:\n"
            "  • Pattern: (.+)  Replacement: \\1_cropped  →  'image' becomes 'image_cropped'\n"
            "  • Pattern: (.+)_\\d+  Replacement: \\1  →  'photo_001' becomes 'photo'\n"
            "  • Pattern: IMG_(\\d+)  Replacement: photo_\\1  →  'IMG_001' becomes 'photo_001'\n"
            "  • Pattern: (.+)  Replacement: cropped_\\1  →  'image' becomes 'cropped_image'"
        )
        ttk.Label(instructions, text=help_text, justify=tk.LEFT).pack(anchor=tk.W)

        # Pattern input
        pattern_frame = ttk.LabelFrame(main_frame, text="Regex Pattern (match against filename)", padding="10")
        pattern_frame.pack(fill=tk.X, pady=(0, 10))

        self.pattern_var = tk.StringVar(value=self.pattern)
        self.pattern_entry = ttk.Entry(pattern_frame, textvariable=self.pattern_var, font=("Consolas", 11))
        self.pattern_entry.pack(fill=tk.X)
        self.pattern_var.trace_add("write", lambda *_: self.update_preview())

        # Replacement input
        replacement_frame = ttk.LabelFrame(main_frame, text="Replacement Pattern (use \\1, \\2 for groups)", padding="10")
        replacement_frame.pack(fill=tk.X, pady=(0, 10))

        self.replacement_var = tk.StringVar(value=self.replacement)
        self.replacement_entry = ttk.Entry(replacement_frame, textvariable=self.replacement_var, font=("Consolas", 11))
        self.replacement_entry.pack(fill=tk.X)
        self.replacement_var.trace_add("write", lambda *_: self.update_preview())

        # Preview - pack last so it takes remaining space and shrinks first if needed
        preview_frame = ttk.LabelFrame(main_frame, text="Preview", padding="10")
        preview_frame.pack(fill=tk.BOTH, expand=True, pady=(0, 10))

        # Create treeview for preview
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
        """Update the preview based on current pattern and replacement."""
        # Clear existing items
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
                    output = f"{name}_cropped{ext}"
                    status = "No match (default)"
            except re.error as e:
                output = "Error"
                status = str(e)

            self.preview_tree.insert("", tk.END, values=(filename, output, status))

    def reset_default(self):
        """Reset to default pattern."""
        self.pattern_var.set(r"(.+)")
        self.replacement_var.set(r"\1_cropped")

    def apply(self):
        """Apply the configuration and save to config file."""
        pattern = self.pattern_var.get()
        replacement = self.replacement_var.get()

        # Validate
        try:
            re.compile(pattern)
        except re.error as e:
            messagebox.showerror("Error", f"Invalid regex pattern: {e}")
            return

        self.result = {
            "pattern": pattern,
            "replacement": replacement
        }

        # Save config via callback
        if self.on_save_config:
            self.on_save_config(pattern, replacement)

        self.dialog.destroy()

    def cancel(self):
        """Cancel the dialog."""
        self.result = None
        self.dialog.destroy()

    def show(self):
        """Show the dialog and wait for result."""
        self.dialog.wait_window()
        return self.result


class ImageClipper:
    def __init__(self, root):
        self.root = root
        self.root.title("Image Clipper - Horizontal Line Cropper")
        self.root.geometry("1400x900")

        self.original_image = None  # PIL Image
        self.cv_image = None  # OpenCV image (BGR)
        self.cropped_image = None
        self.image_path = None

        # Detected lines (y coordinates)
        self.detected_lines = []
        self.selected_lines = []  # Two selected line indices

        # Selected line indices for batch processing (1-based, e.g., Line 1, Line 2)
        self.selected_line_numbers = []  # Stores [1, 2] meaning "use 1st and 2nd detected lines"

        # Display scaling
        self.display_scale = 1.0
        self.display_offset = (0, 0)

        # Line detection parameters
        self.min_line_length_ratio = tk.DoubleVar(value=0.5)
        self.canny_threshold1 = tk.IntVar(value=50)
        self.canny_threshold2 = tk.IntVar(value=150)
        self.hough_threshold = tk.IntVar(value=100)

        # Debounce timer for real-time updates
        self._update_timer = None

        # Naming pattern for batch processing
        self.naming_pattern = r"(.+)"
        self.naming_replacement = r"\1_cropped"

        self.setup_ui()
        self.load_config()

    def setup_ui(self):
        # Main container
        main_frame = ttk.Frame(self.root, padding="10")
        main_frame.pack(fill=tk.BOTH, expand=True)

        # Top toolbar
        toolbar = ttk.Frame(main_frame)
        toolbar.pack(fill=tk.X, pady=(0, 10))

        ttk.Button(toolbar, text="Open Image", command=self.open_image).pack(side=tk.LEFT, padx=5)
        ttk.Button(toolbar, text="Clear Selection", command=self.clear_selection).pack(side=tk.LEFT, padx=5)
        ttk.Button(toolbar, text="Crop", command=self.crop_image).pack(side=tk.LEFT, padx=5)
        ttk.Button(toolbar, text="Save Cropped", command=self.save_image).pack(side=tk.LEFT, padx=5)

        ttk.Separator(toolbar, orient=tk.VERTICAL).pack(side=tk.LEFT, fill=tk.Y, padx=10)

        ttk.Button(toolbar, text="Batch Process", command=self.batch_process).pack(side=tk.LEFT, padx=5)

        ttk.Separator(toolbar, orient=tk.VERTICAL).pack(side=tk.LEFT, fill=tk.Y, padx=10)

        ttk.Button(toolbar, text="Save Config", command=self.save_config).pack(side=tk.LEFT, padx=5)
        ttk.Button(toolbar, text="Load Config", command=self.load_config_dialog).pack(side=tk.LEFT, padx=5)

        # Settings frame
        settings_frame = ttk.LabelFrame(main_frame, text="Line Detection Settings", padding="10")
        settings_frame.pack(fill=tk.X, pady=(0, 10))

        # Min line length ratio
        row1 = ttk.Frame(settings_frame)
        row1.pack(fill=tk.X, pady=2)
        ttk.Label(row1, text="Min Line Length (%):").pack(side=tk.LEFT)
        ttk.Scale(row1, from_=0.1, to=1.0, variable=self.min_line_length_ratio,
                  orient=tk.HORIZONTAL, command=self.on_param_change).pack(side=tk.LEFT, fill=tk.X, expand=True, padx=10)
        ttk.Label(row1, textvariable=self.min_line_length_ratio, width=5).pack(side=tk.LEFT)

        # Canny thresholds
        row2 = ttk.Frame(settings_frame)
        row2.pack(fill=tk.X, pady=2)
        ttk.Label(row2, text="Canny Low:").pack(side=tk.LEFT)
        ttk.Scale(row2, from_=0, to=255, variable=self.canny_threshold1,
                  orient=tk.HORIZONTAL, command=self.on_param_change).pack(side=tk.LEFT, fill=tk.X, expand=True, padx=5)
        ttk.Label(row2, textvariable=self.canny_threshold1, width=5).pack(side=tk.LEFT)

        ttk.Label(row2, text="High:").pack(side=tk.LEFT, padx=(20, 0))
        ttk.Scale(row2, from_=0, to=255, variable=self.canny_threshold2,
                  orient=tk.HORIZONTAL, command=self.on_param_change).pack(side=tk.LEFT, fill=tk.X, expand=True, padx=5)
        ttk.Label(row2, textvariable=self.canny_threshold2, width=5).pack(side=tk.LEFT)

        # Hough threshold
        row3 = ttk.Frame(settings_frame)
        row3.pack(fill=tk.X, pady=2)
        ttk.Label(row3, text="Hough Threshold:").pack(side=tk.LEFT)
        ttk.Scale(row3, from_=20, to=300, variable=self.hough_threshold,
                  orient=tk.HORIZONTAL, command=self.on_param_change).pack(side=tk.LEFT, fill=tk.X, expand=True, padx=10)
        ttk.Label(row3, textvariable=self.hough_threshold, width=5).pack(side=tk.LEFT)

        # Batch selection info
        row4 = ttk.Frame(settings_frame)
        row4.pack(fill=tk.X, pady=5)
        ttk.Label(row4, text="Batch Selection:").pack(side=tk.LEFT)
        self.batch_selection_var = tk.StringVar(value="Not set - select 2 lines first")
        ttk.Label(row4, textvariable=self.batch_selection_var, foreground="blue").pack(side=tk.LEFT, padx=10)

        # Image display area
        display_frame = ttk.Frame(main_frame)
        display_frame.pack(fill=tk.BOTH, expand=True)

        # Original image panel with lines
        original_frame = ttk.LabelFrame(display_frame, text="Original Image (Click to select lines)", padding="5")
        original_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(0, 5))

        self.original_canvas = tk.Canvas(original_frame, bg="#2d2d2d")
        self.original_canvas.pack(fill=tk.BOTH, expand=True)
        self.original_canvas.bind("<Button-1>", self.on_canvas_click)

        self.original_info = ttk.Label(original_frame, text="No image loaded")
        self.original_info.pack(pady=5)

        # Cropped image panel
        cropped_frame = ttk.LabelFrame(display_frame, text="Cropped Preview", padding="5")
        cropped_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(5, 0))

        self.cropped_canvas = tk.Canvas(cropped_frame, bg="#2d2d2d")
        self.cropped_canvas.pack(fill=tk.BOTH, expand=True)

        self.cropped_info = ttk.Label(cropped_frame, text="No preview available")
        self.cropped_info.pack(pady=5)

        # Line list panel
        lines_frame = ttk.LabelFrame(display_frame, text="Detected Lines", padding="5")
        lines_frame.pack(side=tk.RIGHT, fill=tk.Y, padx=(5, 0))

        self.lines_listbox = tk.Listbox(lines_frame, width=20, selectmode=tk.MULTIPLE)
        self.lines_listbox.pack(fill=tk.BOTH, expand=True)
        self.lines_listbox.bind("<<ListboxSelect>>", self.on_listbox_select)

        ttk.Button(lines_frame, text="Use Selected", command=self.use_selected_lines).pack(pady=5)

        # Status bar
        self.status_var = tk.StringVar(value="Ready. Open an image and detect lines.")
        status_bar = ttk.Label(main_frame, textvariable=self.status_var, relief=tk.SUNKEN)
        status_bar.pack(fill=tk.X, pady=(10, 0))

        # Bind resize event
        self.root.bind('<Configure>', self.on_resize)

    def get_config(self):
        """Get current configuration as dictionary."""
        return {
            "min_line_length_ratio": self.min_line_length_ratio.get(),
            "canny_threshold1": self.canny_threshold1.get(),
            "canny_threshold2": self.canny_threshold2.get(),
            "hough_threshold": self.hough_threshold.get(),
            "selected_line_numbers": self.selected_line_numbers,
            "naming_pattern": self.naming_pattern,
            "naming_replacement": self.naming_replacement
        }

    def set_config(self, config):
        """Apply configuration from dictionary."""
        if "min_line_length_ratio" in config:
            self.min_line_length_ratio.set(config["min_line_length_ratio"])
        if "canny_threshold1" in config:
            self.canny_threshold1.set(config["canny_threshold1"])
        if "canny_threshold2" in config:
            self.canny_threshold2.set(config["canny_threshold2"])
        if "hough_threshold" in config:
            self.hough_threshold.set(config["hough_threshold"])
        if "selected_line_numbers" in config:
            self.selected_line_numbers = config["selected_line_numbers"]
            self.update_batch_selection_display()
        if "naming_pattern" in config:
            self.naming_pattern = config["naming_pattern"]
        if "naming_replacement" in config:
            self.naming_replacement = config["naming_replacement"]

    def save_config(self):
        """Save current configuration to file."""
        if len(self.selected_lines) != 2:
            messagebox.showwarning("Warning", "Please select exactly 2 lines before saving config.\n\n"
                                   "The line numbers (e.g., Line 1 and Line 3) will be saved for batch processing.")
            return

        # Update selected_line_numbers from current selection (convert to 1-based)
        self.selected_line_numbers = sorted([idx + 1 for idx in self.selected_lines])
        self.update_batch_selection_display()

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
                messagebox.showinfo("Success", f"Configuration saved to:\n{path}\n\n"
                                    f"Line selection: Line {self.selected_line_numbers[0]} and Line {self.selected_line_numbers[1]}")
            except Exception as e:
                messagebox.showerror("Error", f"Failed to save config: {e}")

    def load_config(self):
        """Load configuration from default file if exists."""
        if os.path.exists(CONFIG_FILE):
            try:
                with open(CONFIG_FILE, 'r') as f:
                    config = json.load(f)
                self.set_config(config)
                self.status_var.set(f"Loaded config from {CONFIG_FILE}")
            except Exception:
                pass  # Silently ignore errors on auto-load

    def load_config_dialog(self):
        """Load configuration from user-selected file."""
        filetypes = [("JSON files", "*.json"), ("All files", "*.*")]
        path = filedialog.askopenfilename(filetypes=filetypes)

        if path:
            try:
                with open(path, 'r') as f:
                    config = json.load(f)
                self.set_config(config)

                # Re-detect lines with new parameters if image is loaded
                if self.cv_image is not None:
                    self.detect_lines()
                    # Apply saved line selection
                    self.apply_line_numbers_selection()

                self.status_var.set(f"Config loaded: {path}")
                messagebox.showinfo("Success", f"Configuration loaded from:\n{path}")
            except Exception as e:
                messagebox.showerror("Error", f"Failed to load config: {e}")

    def update_batch_selection_display(self):
        """Update the batch selection display label."""
        if len(self.selected_line_numbers) == 2:
            self.batch_selection_var.set(f"Line {self.selected_line_numbers[0]} and Line {self.selected_line_numbers[1]}")
        else:
            self.batch_selection_var.set("Not set - select 2 lines first")

    def apply_line_numbers_selection(self):
        """Apply saved line numbers to current detected lines."""
        if len(self.selected_line_numbers) == 2 and len(self.detected_lines) >= max(self.selected_line_numbers):
            # Convert 1-based to 0-based indices
            self.selected_lines = [n - 1 for n in self.selected_line_numbers]
            self.display_original()
            self.update_preview()

    def open_image(self):
        filetypes = [
            ("Image files", "*.png *.jpg *.jpeg *.gif *.bmp *.tiff *.webp"),
            ("All files", "*.*")
        ]
        path = filedialog.askopenfilename(filetypes=filetypes)
        if path:
            self.load_image(path)

    def load_image(self, path):
        """Load an image from path."""
        try:
            self.image_path = path
            # Load with OpenCV
            self.cv_image = cv2.imread(path)
            if self.cv_image is None:
                raise ValueError("Failed to load image")

            # Convert to PIL for display
            rgb_image = cv2.cvtColor(self.cv_image, cv2.COLOR_BGR2RGB)
            self.original_image = Image.fromarray(rgb_image)

            self.detected_lines = []
            self.selected_lines = []
            self.cropped_image = None

            self.lines_listbox.delete(0, tk.END)
            self.status_var.set(f"Loaded: {os.path.basename(path)}")

            # Auto-detect lines on load
            self.detect_lines()

            # Apply saved line numbers if available
            self.apply_line_numbers_selection()

            self.cropped_canvas.delete("all")
            self.cropped_info.config(text="No preview available")
        except Exception as e:
            messagebox.showerror("Error", f"Failed to open image: {e}")

    def on_param_change(self, _=None):
        """Handle parameter change with debouncing for real-time preview."""
        if self.cv_image is None:
            return

        # Cancel previous timer if exists
        if self._update_timer is not None:
            self.root.after_cancel(self._update_timer)

        # Set new timer (100ms debounce)
        self._update_timer = self.root.after(100, self.detect_lines)

    def detect_lines(self):
        """Detect horizontal lines using OpenCV Hough Line Transform."""
        if self.cv_image is None:
            return

        try:
            # Convert to grayscale
            gray = cv2.cvtColor(self.cv_image, cv2.COLOR_BGR2GRAY)

            # Apply Gaussian blur
            blurred = cv2.GaussianBlur(gray, (5, 5), 0)

            # Edge detection
            edges = cv2.Canny(blurred,
                              self.canny_threshold1.get(),
                              self.canny_threshold2.get())

            # Detect lines using Hough Transform
            height, width = self.cv_image.shape[:2]
            min_line_length = int(width * self.min_line_length_ratio.get())

            lines = cv2.HoughLinesP(edges,
                                    rho=1,
                                    theta=np.pi / 180,
                                    threshold=self.hough_threshold.get(),
                                    minLineLength=min_line_length,
                                    maxLineGap=10)

            # Filter horizontal lines (angle close to 0 degrees)
            horizontal_lines = []
            if lines is not None:
                for line in lines:
                    x1, y1, x2, y2 = line[0]
                    # Check if line is horizontal (small angle)
                    angle = abs(np.arctan2(y2 - y1, x2 - x1) * 180 / np.pi)
                    if angle < 5 or angle > 175:  # Nearly horizontal
                        # Store the average y coordinate
                        y_avg = (y1 + y2) // 2
                        horizontal_lines.append(y_avg)

            # Remove duplicate/close lines (within 10 pixels)
            horizontal_lines = sorted(set(horizontal_lines))
            merged_lines = []
            for y in horizontal_lines:
                if not merged_lines or abs(y - merged_lines[-1]) > 10:
                    merged_lines.append(y)

            # Try to preserve selected lines by finding closest matches in new detection
            old_selected_y = [self.detected_lines[i] for i in self.selected_lines if i < len(self.detected_lines)]

            self.detected_lines = merged_lines

            # Remap selected lines to new indices
            new_selected = []
            for old_y in old_selected_y:
                # Find closest line in new detection
                best_idx = -1
                best_dist = float('inf')
                for i, new_y in enumerate(self.detected_lines):
                    dist = abs(new_y - old_y)
                    if dist < best_dist and dist < 20:  # Within 20 pixels tolerance
                        best_dist = dist
                        best_idx = i
                if best_idx >= 0 and best_idx not in new_selected:
                    new_selected.append(best_idx)

            self.selected_lines = new_selected

            # Update listbox
            self.lines_listbox.delete(0, tk.END)
            for i, y in enumerate(self.detected_lines):
                self.lines_listbox.insert(tk.END, f"Line {i + 1}: y = {y}")

            self.status_var.set(f"Detected {len(self.detected_lines)} horizontal lines. Click on two lines to select crop region.")
            self.display_original()

            # Update crop preview if we still have 2 selected lines
            if len(self.selected_lines) == 2:
                self.update_preview()

        except Exception as e:
            messagebox.showerror("Error", f"Failed to detect lines: {e}")

    def detect_lines_for_image(self, cv_img):
        """Detect horizontal lines for a given OpenCV image (used in batch processing)."""
        try:
            gray = cv2.cvtColor(cv_img, cv2.COLOR_BGR2GRAY)
            blurred = cv2.GaussianBlur(gray, (5, 5), 0)
            edges = cv2.Canny(blurred,
                              self.canny_threshold1.get(),
                              self.canny_threshold2.get())

            height, width = cv_img.shape[:2]
            min_line_length = int(width * self.min_line_length_ratio.get())

            lines = cv2.HoughLinesP(edges,
                                    rho=1,
                                    theta=np.pi / 180,
                                    threshold=self.hough_threshold.get(),
                                    minLineLength=min_line_length,
                                    maxLineGap=10)

            horizontal_lines = []
            if lines is not None:
                for line in lines:
                    x1, y1, x2, y2 = line[0]
                    angle = abs(np.arctan2(y2 - y1, x2 - x1) * 180 / np.pi)
                    if angle < 5 or angle > 175:
                        y_avg = (y1 + y2) // 2
                        horizontal_lines.append(y_avg)

            horizontal_lines = sorted(set(horizontal_lines))
            merged_lines = []
            for y in horizontal_lines:
                if not merged_lines or abs(y - merged_lines[-1]) > 10:
                    merged_lines.append(y)

            return merged_lines
        except Exception:
            return []

    def display_original(self):
        """Display the original image with detected lines."""
        if self.original_image is None:
            return

        self.original_canvas.update_idletasks()
        canvas_w = self.original_canvas.winfo_width()
        canvas_h = self.original_canvas.winfo_height()

        if canvas_w <= 1 or canvas_h <= 1:
            return

        img_w, img_h = self.original_image.size

        # Calculate scale to fit
        self.display_scale = min(canvas_w / img_w, canvas_h / img_h, 1.0)
        new_w = max(1, int(img_w * self.display_scale))
        new_h = max(1, int(img_h * self.display_scale))

        # Calculate offset to center image
        self.display_offset = ((canvas_w - new_w) // 2, (canvas_h - new_h) // 2)

        # Resize image
        display_img = self.original_image.resize((new_w, new_h), Image.Resampling.LANCZOS)
        self.original_photo = ImageTk.PhotoImage(display_img)

        self.original_canvas.delete("all")
        self.original_canvas.create_image(
            self.display_offset[0], self.display_offset[1],
            image=self.original_photo, anchor=tk.NW
        )

        # Draw detected lines
        for i, y in enumerate(self.detected_lines):
            scaled_y = int(y * self.display_scale) + self.display_offset[1]
            color = "#00ff00"  # Green for unselected
            width = 1

            if i in self.selected_lines:
                color = "#ff0000"  # Red for selected
                width = 3

            self.original_canvas.create_line(
                self.display_offset[0], scaled_y,
                self.display_offset[0] + new_w, scaled_y,
                fill=color, width=width, tags=f"line_{i}"
            )

            # Draw line label
            self.original_canvas.create_text(
                self.display_offset[0] + 5, scaled_y - 5,
                text=f"L{i + 1}", fill=color, anchor=tk.SW, font=("Arial", 8)
            )

        w, h = self.original_image.size
        self.original_info.config(text=f"Size: {w} x {h} | Lines: {len(self.detected_lines)} | Selected: {len(self.selected_lines)}")

    def on_canvas_click(self, event):
        """Handle click on canvas to select a line."""
        if not self.detected_lines:
            return

        # Convert click position to image coordinates
        img_y = (event.y - self.display_offset[1]) / self.display_scale

        # Find closest line
        min_dist = float('inf')
        closest_idx = -1
        for i, y in enumerate(self.detected_lines):
            dist = abs(y - img_y)
            if dist < min_dist:
                min_dist = dist
                closest_idx = i

        # Only select if click is close enough (within 20 pixels in image space)
        if min_dist < 20 and closest_idx >= 0:
            if closest_idx in self.selected_lines:
                self.selected_lines.remove(closest_idx)
            else:
                if len(self.selected_lines) >= 2:
                    self.selected_lines.pop(0)  # Remove oldest selection
                self.selected_lines.append(closest_idx)

            # Update selected_line_numbers for batch processing (1-based)
            if len(self.selected_lines) == 2:
                self.selected_line_numbers = sorted([idx + 1 for idx in self.selected_lines])
                self.update_batch_selection_display()

            self.display_original()
            self.update_preview()

    def on_listbox_select(self, event):
        """Handle listbox selection."""
        pass  # Selection is applied when "Use Selected" is clicked

    def use_selected_lines(self):
        """Use lines selected in listbox."""
        selection = self.lines_listbox.curselection()
        if len(selection) != 2:
            messagebox.showwarning("Warning", "Please select exactly 2 lines from the list.")
            return

        self.selected_lines = list(selection)
        # Update selected_line_numbers for batch processing (1-based)
        self.selected_line_numbers = sorted([idx + 1 for idx in self.selected_lines])
        self.update_batch_selection_display()

        self.display_original()
        self.update_preview()

    def clear_selection(self):
        """Clear line selection."""
        self.selected_lines = []
        self.cropped_image = None
        self.display_original()
        self.cropped_canvas.delete("all")
        self.cropped_info.config(text="No preview available")
        self.status_var.set("Selection cleared.")

    def update_preview(self):
        """Update the cropped preview based on selected lines."""
        if len(self.selected_lines) != 2:
            return

        try:
            y1 = self.detected_lines[self.selected_lines[0]]
            y2 = self.detected_lines[self.selected_lines[1]]

            # Ensure y1 < y2
            if y1 > y2:
                y1, y2 = y2, y1

            # Crop the image
            self.cropped_image = self.original_image.crop((0, y1, self.original_image.width, y2))
            self.display_cropped()

            orig_w, orig_h = self.original_image.size
            crop_w, crop_h = self.cropped_image.size
            self.status_var.set(
                f"Preview: Cropping from y={y1} to y={y2} | "
                f"Original: {orig_w}x{orig_h} → Cropped: {crop_w}x{crop_h}"
            )

        except Exception as e:
            self.status_var.set(f"Error: {e}")

    def crop_image(self):
        """Perform the crop with selected lines."""
        if len(self.selected_lines) != 2:
            messagebox.showwarning("Warning", "Please select exactly 2 lines to define the crop region.")
            return

        self.update_preview()
        if self.cropped_image:
            messagebox.showinfo("Success", "Image cropped successfully! Click 'Save Cropped' to save.")

    def display_cropped(self):
        """Display the cropped image on canvas."""
        if self.cropped_image is None:
            return

        self.cropped_canvas.update_idletasks()
        canvas_w = self.cropped_canvas.winfo_width()
        canvas_h = self.cropped_canvas.winfo_height()

        if canvas_w <= 1 or canvas_h <= 1:
            return

        img_w, img_h = self.cropped_image.size

        # Calculate scale to fit
        scale = min(canvas_w / img_w, canvas_h / img_h, 1.0)
        new_w = max(1, int(img_w * scale))
        new_h = max(1, int(img_h * scale))

        display_img = self.cropped_image.resize((new_w, new_h), Image.Resampling.LANCZOS)
        self.cropped_photo = ImageTk.PhotoImage(display_img)

        self.cropped_canvas.delete("all")
        self.cropped_canvas.create_image(
            canvas_w // 2, canvas_h // 2,
            image=self.cropped_photo, anchor=tk.CENTER
        )

        w, h = self.cropped_image.size
        self.cropped_info.config(text=f"Size: {w} x {h} pixels")

    def on_resize(self, event):
        """Handle window resize."""
        if self.original_image:
            self.display_original()
        if self.cropped_image:
            self.display_cropped()

    def save_image(self):
        """Save the cropped image."""
        if self.cropped_image is None:
            messagebox.showwarning("Warning", "No cropped image to save. Select two lines and crop first.")
            return

        # Suggest filename
        if self.image_path:
            base, ext = os.path.splitext(self.image_path)
            suggested = f"{base}_cropped{ext}"
        else:
            suggested = "cropped_image.png"

        filetypes = [
            ("PNG files", "*.png"),
            ("JPEG files", "*.jpg *.jpeg"),
            ("All files", "*.*")
        ]

        path = filedialog.asksaveasfilename(
            initialfile=os.path.basename(suggested),
            defaultextension=".png",
            filetypes=filetypes
        )

        if path:
            try:
                # Convert to RGB if saving as JPEG
                if path.lower().endswith(('.jpg', '.jpeg')):
                    save_img = self.cropped_image.convert('RGB')
                else:
                    save_img = self.cropped_image

                save_img.save(path)
                self.status_var.set(f"Saved: {path}")
                messagebox.showinfo("Success", f"Image saved to:\n{path}")
            except Exception as e:
                messagebox.showerror("Error", f"Failed to save image: {e}")

    def get_output_filename(self, input_filename):
        """Generate output filename using regex pattern."""
        name, ext = os.path.splitext(input_filename)

        try:
            regex = re.compile(self.naming_pattern)
            if regex.search(name):
                new_name = regex.sub(self.naming_replacement, name)
                return f"{new_name}{ext}"
        except re.error:
            pass

        # Fallback to default
        return f"{name}_cropped{ext}"

    def save_naming_config(self, pattern, replacement):
        """Save naming pattern to config file."""
        self.naming_pattern = pattern
        self.naming_replacement = replacement

        # Load existing config or create new
        config = {}
        if os.path.exists(CONFIG_FILE):
            try:
                with open(CONFIG_FILE, 'r') as f:
                    config = json.load(f)
            except Exception:
                pass

        # Update naming fields
        config["naming_pattern"] = pattern
        config["naming_replacement"] = replacement

        # Save config
        try:
            with open(CONFIG_FILE, 'w') as f:
                json.dump(config, f, indent=2)
        except Exception as e:
            print(f"Failed to save naming config: {e}")

    def batch_process(self):
        """Batch process images from a folder using adaptive line selection."""
        if len(self.selected_line_numbers) != 2:
            messagebox.showwarning(
                "Warning",
                "Please select exactly 2 lines first.\n\n"
                "The line numbers (e.g., Line 1 and Line 2) will be used to crop all images.\n"
                "Each image will be analyzed independently, and the same line numbers will be selected."
            )
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

        # Show naming dialog with save callback
        naming_dialog = NamingDialog(
            self.root,
            image_files,
            self.naming_pattern,
            self.naming_replacement,
            on_save_config=self.save_naming_config
        )
        result = naming_dialog.show()

        if result is None:
            return  # User cancelled

        # Update naming pattern (already saved by dialog)
        self.naming_pattern = result["pattern"]
        self.naming_replacement = result["replacement"]

        line_num1, line_num2 = self.selected_line_numbers

        # Confirm
        confirm_result = messagebox.askyesno(
            "Confirm Batch Processing",
            f"Found {len(image_files)} images.\n\n"
            f"Each image will be processed with current parameters:\n"
            f"  - Min Line Length: {self.min_line_length_ratio.get():.2f}\n"
            f"  - Canny: {self.canny_threshold1.get()} / {self.canny_threshold2.get()}\n"
            f"  - Hough: {self.hough_threshold.get()}\n\n"
            f"Line selection: Line {line_num1} and Line {line_num2}\n"
            f"(Adaptive: actual y-values will vary per image)\n\n"
            f"Naming: '{self.naming_pattern}' → '{self.naming_replacement}'\n\n"
            f"Continue?"
        )

        if not confirm_result:
            return

        success_count = 0
        skip_count = 0
        error_count = 0
        skipped_files = []

        for i, filename in enumerate(image_files):
            self.status_var.set(f"Processing {i + 1}/{len(image_files)}: {filename}")
            self.root.update()

            input_path = os.path.join(input_dir, filename)

            try:
                cv_img = cv2.imread(input_path)
                if cv_img is None:
                    raise ValueError("Failed to load image")

                # Detect lines for this image
                detected = self.detect_lines_for_image(cv_img)

                # Check if we have enough lines
                if len(detected) < max(line_num1, line_num2):
                    skipped_files.append(f"{filename} (only {len(detected)} lines detected)")
                    skip_count += 1
                    continue

                # Get y coordinates for selected line numbers (1-based to 0-based)
                y1 = detected[line_num1 - 1]
                y2 = detected[line_num2 - 1]

                if y1 > y2:
                    y1, y2 = y2, y1

                # Crop
                rgb_img = cv2.cvtColor(cv_img, cv2.COLOR_BGR2RGB)
                pil_img = Image.fromarray(rgb_img)
                cropped = pil_img.crop((0, y1, pil_img.width, y2))

                # Generate output filename using regex pattern
                output_filename = self.get_output_filename(filename)
                output_path = os.path.join(output_dir, output_filename)

                if output_path.lower().endswith(('.jpg', '.jpeg')):
                    cropped = cropped.convert('RGB')

                cropped.save(output_path)
                success_count += 1

            except Exception as e:
                skipped_files.append(f"{filename} (error: {str(e)})")
                error_count += 1

        # Show results
        result_msg = (
            f"Batch processing complete!\n\n"
            f"  Success: {success_count}\n"
            f"  Skipped: {skip_count}\n"
            f"  Errors: {error_count}\n\n"
            f"Output directory:\n{output_dir}"
        )

        if skipped_files:
            result_msg += f"\n\nSkipped files:\n" + "\n".join(skipped_files[:10])
            if len(skipped_files) > 10:
                result_msg += f"\n... and {len(skipped_files) - 10} more"

        self.status_var.set(f"Batch complete: {success_count} success, {skip_count} skipped, {error_count} errors")
        messagebox.showinfo("Batch Processing Complete", result_msg)


def main():
    root = tk.Tk()
    app = ImageClipper(root)
    root.mainloop()


if __name__ == "__main__":
    main()
