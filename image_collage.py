"""
Image Collage - Create collages from cropped images.
Supports configurable layout, alignment, ordering, and background color.
"""

import tkinter as tk
from tkinter import ttk, filedialog, messagebox, colorchooser
from PIL import Image, ImageTk
import os
import json
import re


CONFIG_FILE = "image_collage_config.json"


class ImageCollage:
    def __init__(self, root):
        self.root = root
        self.root.title("Image Collage Creator")
        self.root.geometry("1400x900")

        # Image data
        self.input_dir = None
        self.image_files = []  # Original file list
        self.sorted_files = []  # Sorted/filtered file list
        self.images = []  # Loaded PIL images
        self.collage_image = None

        # Layout settings
        self.cols = tk.IntVar(value=3)
        self.rows = tk.IntVar(value=3)
        self.spacing = tk.IntVar(value=10)
        self.padding = tk.IntVar(value=20)

        # Alignment: "top" or "bottom" for each row
        self.row_alignment = tk.StringVar(value="top")  # Default alignment for all rows

        # Order: "Z" (left-to-right, top-to-bottom) or "S" (snake/boustrophedon)
        self.order_mode = tk.StringVar(value="Z")

        # Background color (RGB)
        self.bg_color = (255, 255, 255)
        self.bg_color_var = tk.StringVar(value="#FFFFFF")

        # Regex pattern for filtering and sorting
        self.filename_pattern = tk.StringVar(value=r"(.+)")
        self.sort_group = tk.IntVar(value=0)  # Which capture group to use for sorting

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

        ttk.Button(toolbar, text="Select Folder", command=self.select_folder).pack(side=tk.LEFT, padx=5)
        ttk.Button(toolbar, text="Refresh Collage", command=lambda: self.generate_collage(show_warning=True)).pack(side=tk.LEFT, padx=5)
        ttk.Button(toolbar, text="Save Collage", command=self.save_collage).pack(side=tk.LEFT, padx=5)
        ttk.Button(toolbar, text="Batch Process", command=self.batch_process).pack(side=tk.LEFT, padx=5)

        ttk.Separator(toolbar, orient=tk.VERTICAL).pack(side=tk.LEFT, fill=tk.Y, padx=10)

        ttk.Button(toolbar, text="Save Config", command=self.save_config).pack(side=tk.LEFT, padx=5)
        ttk.Button(toolbar, text="Load Config", command=self.load_config_dialog).pack(side=tk.LEFT, padx=5)

        # Settings panel (left side)
        settings_panel = ttk.Frame(main_frame, width=350)
        settings_panel.pack(side=tk.LEFT, fill=tk.Y, padx=(0, 10))
        settings_panel.pack_propagate(False)

        # Regex settings
        regex_frame = ttk.LabelFrame(settings_panel, text="Filename Pattern", padding="10")
        regex_frame.pack(fill=tk.X, pady=(0, 10))

        ttk.Label(regex_frame, text="Regex Pattern:").pack(anchor=tk.W)
        pattern_entry = ttk.Entry(regex_frame, textvariable=self.filename_pattern, font=("Consolas", 10))
        pattern_entry.pack(fill=tk.X, pady=(0, 5))

        sort_frame = ttk.Frame(regex_frame)
        sort_frame.pack(fill=tk.X)
        ttk.Label(sort_frame, text="Sort by group:").pack(side=tk.LEFT)
        ttk.Spinbox(sort_frame, from_=0, to=9, width=5, textvariable=self.sort_group).pack(side=tk.LEFT, padx=5)
        ttk.Button(sort_frame, text="Apply & Sort", command=self.apply_pattern).pack(side=tk.RIGHT)

        ttk.Label(regex_frame, text="(Group 0 = entire match, 1+ = capture groups)",
                  font=("Arial", 8), foreground="gray").pack(anchor=tk.W)

        # Layout settings
        layout_frame = ttk.LabelFrame(settings_panel, text="Layout", padding="10")
        layout_frame.pack(fill=tk.X, pady=(0, 10))

        grid_frame = ttk.Frame(layout_frame)
        grid_frame.pack(fill=tk.X, pady=5)

        ttk.Label(grid_frame, text="Columns:").pack(side=tk.LEFT)
        ttk.Spinbox(grid_frame, from_=1, to=20, width=5, textvariable=self.cols,
                    command=self.on_layout_change).pack(side=tk.LEFT, padx=5)
        ttk.Label(grid_frame, text="Rows:").pack(side=tk.LEFT, padx=(20, 0))
        ttk.Spinbox(grid_frame, from_=1, to=20, width=5, textvariable=self.rows,
                    command=self.on_layout_change).pack(side=tk.LEFT, padx=5)

        spacing_frame = ttk.Frame(layout_frame)
        spacing_frame.pack(fill=tk.X, pady=5)

        ttk.Label(spacing_frame, text="Spacing:").pack(side=tk.LEFT)
        ttk.Scale(spacing_frame, from_=0, to=50, variable=self.spacing,
                  orient=tk.HORIZONTAL, command=lambda _: self.on_layout_change()).pack(side=tk.LEFT, fill=tk.X, expand=True, padx=5)
        ttk.Label(spacing_frame, textvariable=self.spacing, width=3).pack(side=tk.LEFT)

        padding_frame = ttk.Frame(layout_frame)
        padding_frame.pack(fill=tk.X, pady=5)

        ttk.Label(padding_frame, text="Padding:").pack(side=tk.LEFT)
        ttk.Scale(padding_frame, from_=0, to=100, variable=self.padding,
                  orient=tk.HORIZONTAL, command=lambda _: self.on_layout_change()).pack(side=tk.LEFT, fill=tk.X, expand=True, padx=5)
        ttk.Label(padding_frame, textvariable=self.padding, width=3).pack(side=tk.LEFT)

        # Order settings
        order_frame = ttk.LabelFrame(settings_panel, text="Order", padding="10")
        order_frame.pack(fill=tk.X, pady=(0, 10))

        ttk.Label(order_frame, text="Fill order:").pack(anchor=tk.W)
        order_options = ttk.Frame(order_frame)
        order_options.pack(fill=tk.X, pady=5)

        ttk.Radiobutton(order_options, text="Z (→↓→)", variable=self.order_mode,
                        value="Z", command=self.on_layout_change).pack(side=tk.LEFT, padx=10)
        ttk.Radiobutton(order_options, text="S (→↓←↓→)", variable=self.order_mode,
                        value="S", command=self.on_layout_change).pack(side=tk.LEFT, padx=10)

        # Visual representation
        order_visual = ttk.Label(order_frame, text="Z: 1→2→3\n   4→5→6\n   7→8→9",
                                 font=("Consolas", 9), foreground="gray")
        order_visual.pack(anchor=tk.W, pady=5)
        self.order_visual_label = order_visual

        # Alignment settings
        align_frame = ttk.LabelFrame(settings_panel, text="Row Alignment", padding="10")
        align_frame.pack(fill=tk.X, pady=(0, 10))

        ttk.Label(align_frame, text="Vertical alignment:").pack(anchor=tk.W)
        align_options = ttk.Frame(align_frame)
        align_options.pack(fill=tk.X, pady=5)

        ttk.Radiobutton(align_options, text="Top", variable=self.row_alignment,
                        value="top", command=self.on_layout_change).pack(side=tk.LEFT, padx=10)
        ttk.Radiobutton(align_options, text="Bottom", variable=self.row_alignment,
                        value="bottom", command=self.on_layout_change).pack(side=tk.LEFT, padx=10)
        ttk.Radiobutton(align_options, text="Center", variable=self.row_alignment,
                        value="center", command=self.on_layout_change).pack(side=tk.LEFT, padx=10)

        # Background color
        bg_frame = ttk.LabelFrame(settings_panel, text="Background", padding="10")
        bg_frame.pack(fill=tk.X, pady=(0, 10))

        color_row = ttk.Frame(bg_frame)
        color_row.pack(fill=tk.X)

        ttk.Label(color_row, text="Color:").pack(side=tk.LEFT)
        self.color_preview = tk.Canvas(color_row, width=30, height=20, bg=self.bg_color_var.get(),
                                        highlightthickness=1, highlightbackground="gray")
        self.color_preview.pack(side=tk.LEFT, padx=5)
        ttk.Entry(color_row, textvariable=self.bg_color_var, width=10).pack(side=tk.LEFT, padx=5)
        ttk.Button(color_row, text="Pick", command=self.pick_color).pack(side=tk.LEFT, padx=5)

        # Bind color entry change
        self.bg_color_var.trace_add("write", self.on_color_change)

        # Files count label - pack first with side=BOTTOM to ensure visibility
        self.files_count_var = tk.StringVar(value="No files loaded")
        ttk.Label(settings_panel, textvariable=self.files_count_var).pack(side=tk.BOTTOM, anchor=tk.W, pady=5)

        # File list - pack after count label so it takes remaining space
        files_frame = ttk.LabelFrame(settings_panel, text="Files (sorted)", padding="10")
        files_frame.pack(fill=tk.BOTH, expand=True)

        self.files_listbox = tk.Listbox(files_frame, font=("Consolas", 9))
        files_scrollbar = ttk.Scrollbar(files_frame, orient=tk.VERTICAL, command=self.files_listbox.yview)
        self.files_listbox.configure(yscrollcommand=files_scrollbar.set)

        self.files_listbox.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        files_scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        # Preview panel (right side)
        preview_frame = ttk.LabelFrame(main_frame, text="Preview", padding="5")
        preview_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        self.preview_canvas = tk.Canvas(preview_frame, bg="#2d2d2d")
        self.preview_canvas.pack(fill=tk.BOTH, expand=True)

        self.preview_info = ttk.Label(preview_frame, text="No collage generated")
        self.preview_info.pack(pady=5)

        # Status bar (inside preview panel, at the bottom)
        self.status_var = tk.StringVar(value="Ready. Select a folder with images.")
        status_bar = ttk.Label(preview_frame, textvariable=self.status_var, relief=tk.SUNKEN)
        status_bar.pack(fill=tk.X, pady=(5, 0))

        # Bind resize
        self.root.bind('<Configure>', self.on_resize)

    def get_config(self):
        """Get current configuration as dictionary."""
        return {
            "cols": self.cols.get(),
            "rows": self.rows.get(),
            "spacing": self.spacing.get(),
            "padding": self.padding.get(),
            "row_alignment": self.row_alignment.get(),
            "order_mode": self.order_mode.get(),
            "bg_color": self.bg_color_var.get(),
            "filename_pattern": self.filename_pattern.get(),
            "sort_group": self.sort_group.get()
        }

    def set_config(self, config):
        """Apply configuration from dictionary."""
        if "cols" in config:
            self.cols.set(config["cols"])
        if "rows" in config:
            self.rows.set(config["rows"])
        if "spacing" in config:
            self.spacing.set(config["spacing"])
        if "padding" in config:
            self.padding.set(config["padding"])
        if "row_alignment" in config:
            self.row_alignment.set(config["row_alignment"])
        if "order_mode" in config:
            self.order_mode.set(config["order_mode"])
        if "bg_color" in config:
            self.bg_color_var.set(config["bg_color"])
            self.update_bg_color_from_hex(config["bg_color"])
        if "filename_pattern" in config:
            self.filename_pattern.set(config["filename_pattern"])
        if "sort_group" in config:
            self.sort_group.set(config["sort_group"])

    def save_config(self):
        """Save configuration to file."""
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
        """Load configuration from default file if exists."""
        if os.path.exists(CONFIG_FILE):
            try:
                with open(CONFIG_FILE, 'r') as f:
                    config = json.load(f)
                self.set_config(config)
                self.status_var.set(f"Loaded config from {CONFIG_FILE}")
            except Exception:
                pass

    def load_config_dialog(self):
        """Load configuration from user-selected file."""
        filetypes = [("JSON files", "*.json"), ("All files", "*.*")]
        path = filedialog.askopenfilename(filetypes=filetypes)

        if path:
            try:
                with open(path, 'r') as f:
                    config = json.load(f)
                self.set_config(config)
                self.status_var.set(f"Config loaded: {path}")
                messagebox.showinfo("Success", f"Configuration loaded from:\n{path}")

                # Re-apply pattern if files are loaded
                if self.image_files:
                    self.apply_pattern()
            except Exception as e:
                messagebox.showerror("Error", f"Failed to load config: {e}")

    def select_folder(self):
        """Select input folder containing images."""
        folder = filedialog.askdirectory(title="Select Folder with Images")
        if folder:
            self.input_dir = folder
            self.load_images_from_folder()

    def load_images_from_folder(self):
        """Load image files from the selected folder."""
        if not self.input_dir:
            return

        image_extensions = {'.png', '.jpg', '.jpeg', '.gif', '.bmp', '.tiff', '.webp'}
        self.image_files = sorted([
            f for f in os.listdir(self.input_dir)
            if os.path.splitext(f)[1].lower() in image_extensions
        ])

        if not self.image_files:
            messagebox.showwarning("Warning", "No image files found in the selected folder.")
            return

        self.status_var.set(f"Loaded {len(self.image_files)} images from {self.input_dir}")
        self.apply_pattern()

    def apply_pattern(self):
        """Apply regex pattern to filter and sort files."""
        if not self.image_files:
            return

        pattern = self.filename_pattern.get()
        sort_group = self.sort_group.get()

        try:
            regex = re.compile(pattern)
        except re.error as e:
            messagebox.showerror("Error", f"Invalid regex pattern: {e}")
            return

        # Filter and sort files
        file_data = []
        for filename in self.image_files:
            name, _ = os.path.splitext(filename)
            match = regex.search(name)
            if match:
                try:
                    if sort_group == 0:
                        sort_key = match.group(0)
                    else:
                        sort_key = match.group(sort_group) if sort_group <= len(match.groups()) else match.group(0)
                    file_data.append((filename, sort_key))
                except IndexError:
                    file_data.append((filename, name))
            else:
                file_data.append((filename, name))

        # Natural sort: split key into text/number chunks for proper ordering
        def natural_sort_key(item):
            key = item[1]
            # Split the key into chunks of digits and non-digits
            chunks = re.split(r'(\d+)', key)
            # Convert digit chunks to integers for numeric comparison
            result = []
            for chunk in chunks:
                if chunk.isdigit():
                    result.append((0, int(chunk)))  # Numbers sort first, by value
                else:
                    result.append((1, chunk.lower()))  # Text sorts second, case-insensitive
            return result

        file_data.sort(key=natural_sort_key)
        self.sorted_files = [f[0] for f in file_data]

        # Update listbox
        self.files_listbox.delete(0, tk.END)
        for i, filename in enumerate(self.sorted_files):
            self.files_listbox.insert(tk.END, f"{i+1}. {filename}")

        self.files_count_var.set(f"{len(self.sorted_files)} files matched")
        self.update_order_visual()

        # Load images
        self.load_images()

    def load_images(self):
        """Load PIL images from sorted file list."""
        self.images = []
        for filename in self.sorted_files:
            path = os.path.join(self.input_dir, filename)
            try:
                img = Image.open(path)
                if img.mode != 'RGBA':
                    img = img.convert('RGBA')
                self.images.append(img)
            except Exception as e:
                print(f"Failed to load {filename}: {e}")

        self.status_var.set(f"Loaded {len(self.images)} images")

        # Auto-generate collage preview
        if self.images:
            self.generate_collage()

    def update_order_visual(self):
        """Update the order visualization label."""
        cols = self.cols.get()
        rows = self.rows.get()
        mode = self.order_mode.get()

        lines = []
        num = 1
        for row in range(min(rows, 3)):
            if mode == "Z":
                line = "→".join([str(num + i) for i in range(min(cols, 3))])
            else:  # S mode
                if row % 2 == 0:
                    line = "→".join([str(num + i) for i in range(min(cols, 3))])
                else:
                    line = "←".join([str(num + min(cols, 3) - 1 - i) for i in range(min(cols, 3))])
            lines.append(f"   {line}")
            num += cols

        if rows > 3:
            lines.append("   ...")

        visual = "\n".join(lines)
        self.order_visual_label.config(text=f"{mode}:\n{visual}")

    def get_image_order(self):
        """Get the order of images based on layout and order mode."""
        cols = self.cols.get()
        rows = self.rows.get()
        mode = self.order_mode.get()
        total = cols * rows

        order = []
        for row in range(rows):
            if mode == "Z":
                row_order = list(range(row * cols, min((row + 1) * cols, total)))
            else:  # S mode
                if row % 2 == 0:
                    row_order = list(range(row * cols, min((row + 1) * cols, total)))
                else:
                    row_order = list(range(min((row + 1) * cols, total) - 1, row * cols - 1, -1))
            order.extend(row_order)

        return order

    def pick_color(self):
        """Open color picker dialog."""
        color = colorchooser.askcolor(color=self.bg_color_var.get(), title="Choose Background Color")
        if color[1]:
            self.bg_color_var.set(color[1])
            self.bg_color = tuple(int(c) for c in color[0])
            self.on_layout_change()

    def on_color_change(self, *args):
        """Handle color entry change."""
        hex_color = self.bg_color_var.get()
        self.update_bg_color_from_hex(hex_color)

    def update_bg_color_from_hex(self, hex_color):
        """Update background color from hex string."""
        try:
            if hex_color.startswith('#') and len(hex_color) == 7:
                r = int(hex_color[1:3], 16)
                g = int(hex_color[3:5], 16)
                b = int(hex_color[5:7], 16)
                self.bg_color = (r, g, b)
                self.color_preview.config(bg=hex_color)
        except ValueError:
            pass

    def on_layout_change(self):
        """Handle layout parameter change with debouncing."""
        self.update_order_visual()

        if not self.images:
            return

        if self._update_timer is not None:
            self.root.after_cancel(self._update_timer)

        self._update_timer = self.root.after(200, self.generate_collage)

    def generate_collage(self, show_warning=False):
        """Generate the collage image."""
        if not self.images:
            if show_warning:
                messagebox.showwarning("Warning", "No images loaded. Select a folder first.")
            return

        cols = self.cols.get()
        rows = self.rows.get()
        spacing = self.spacing.get()
        padding = self.padding.get()
        alignment = self.row_alignment.get()

        # Get image order
        order = self.get_image_order()

        # Limit to available images
        num_images = min(len(self.images), cols * rows)

        # Calculate dimensions
        # All images assumed to have same width, but different heights
        if not self.images:
            return

        img_width = self.images[0].width

        # Calculate row heights (max height in each row)
        row_heights = []
        for row in range(rows):
            row_max_height = 0
            for col in range(cols):
                idx = row * cols + col
                if idx < num_images:
                    img_idx = order[idx] if order[idx] < len(self.images) else 0
                    if img_idx < len(self.images):
                        row_max_height = max(row_max_height, self.images[img_idx].height)
            row_heights.append(row_max_height)

        # Calculate total dimensions
        total_width = cols * img_width + (cols - 1) * spacing + 2 * padding
        total_height = sum(row_heights) + (rows - 1) * spacing + 2 * padding

        # Create collage canvas
        collage = Image.new('RGB', (total_width, total_height), self.bg_color)

        # Place images
        y_offset = padding
        for row in range(rows):
            x_offset = padding
            row_height = row_heights[row]

            for col in range(cols):
                idx = row * cols + col
                if idx < num_images:
                    img_idx = order[idx]
                    if img_idx < len(self.images):
                        img = self.images[img_idx]

                        # Calculate vertical position based on alignment
                        if alignment == "top":
                            y_pos = y_offset
                        elif alignment == "bottom":
                            y_pos = y_offset + row_height - img.height
                        else:  # center
                            y_pos = y_offset + (row_height - img.height) // 2

                        # Convert RGBA to RGB for pasting
                        if img.mode == 'RGBA':
                            # Create a background and paste with alpha
                            bg = Image.new('RGB', img.size, self.bg_color)
                            bg.paste(img, mask=img.split()[3])
                            collage.paste(bg, (x_offset, y_pos))
                        else:
                            collage.paste(img, (x_offset, y_pos))

                x_offset += img_width + spacing

            y_offset += row_height + spacing

        self.collage_image = collage
        self.display_preview()
        self.status_var.set(f"Collage generated: {total_width}x{total_height} pixels")

    def display_preview(self):
        """Display collage preview on canvas."""
        if self.collage_image is None:
            return

        self.preview_canvas.update_idletasks()
        canvas_w = self.preview_canvas.winfo_width()
        canvas_h = self.preview_canvas.winfo_height()

        if canvas_w <= 1 or canvas_h <= 1:
            return

        img_w, img_h = self.collage_image.size

        # Scale to fit
        scale = min(canvas_w / img_w, canvas_h / img_h, 1.0)
        new_w = max(1, int(img_w * scale))
        new_h = max(1, int(img_h * scale))

        display_img = self.collage_image.resize((new_w, new_h), Image.Resampling.LANCZOS)
        self.preview_photo = ImageTk.PhotoImage(display_img)

        self.preview_canvas.delete("all")
        self.preview_canvas.create_image(
            canvas_w // 2, canvas_h // 2,
            image=self.preview_photo, anchor=tk.CENTER
        )

        self.preview_info.config(text=f"Size: {img_w} x {img_h} pixels | Scale: {scale:.1%}")

    def on_resize(self, event):
        """Handle window resize."""
        if self.collage_image:
            if self._update_timer is not None:
                self.root.after_cancel(self._update_timer)
            self._update_timer = self.root.after(100, self.display_preview)

    def save_collage(self):
        """Save the collage image."""
        if self.collage_image is None:
            messagebox.showwarning("Warning", "No collage to save. Generate a collage first.")
            return

        filetypes = [
            ("PNG files", "*.png"),
            ("JPEG files", "*.jpg *.jpeg"),
            ("All files", "*.*")
        ]

        path = filedialog.asksaveasfilename(
            initialfile="collage.png",
            defaultextension=".png",
            filetypes=filetypes
        )

        if path:
            try:
                if path.lower().endswith(('.jpg', '.jpeg')):
                    save_img = self.collage_image.convert('RGB')
                else:
                    save_img = self.collage_image

                save_img.save(path)
                self.status_var.set(f"Saved: {path}")
                messagebox.showinfo("Success", f"Collage saved to:\n{path}")
            except Exception as e:
                messagebox.showerror("Error", f"Failed to save collage: {e}")

    def generate_collage_from_images(self, images):
        """Generate a collage from a specific list of images."""
        if not images:
            return None

        cols = self.cols.get()
        rows = self.rows.get()
        spacing = self.spacing.get()
        padding = self.padding.get()
        alignment = self.row_alignment.get()

        # Get image order
        order = self.get_image_order()

        # Limit to available images
        num_images = min(len(images), cols * rows)

        img_width = images[0].width

        # Calculate row heights (max height in each row)
        row_heights = []
        for row in range(rows):
            row_max_height = 0
            for col in range(cols):
                idx = row * cols + col
                if idx < num_images:
                    img_idx = order[idx] if order[idx] < len(images) else 0
                    if img_idx < len(images):
                        row_max_height = max(row_max_height, images[img_idx].height)
            row_heights.append(row_max_height if row_max_height > 0 else 0)

        # Filter out zero-height rows (incomplete last batch)
        active_rows = sum(1 for h in row_heights if h > 0)
        row_heights = row_heights[:active_rows]

        # Calculate total dimensions
        total_width = cols * img_width + (cols - 1) * spacing + 2 * padding
        total_height = sum(row_heights) + (len(row_heights) - 1) * spacing + 2 * padding if row_heights else 2 * padding

        # Create collage canvas
        collage = Image.new('RGB', (total_width, total_height), self.bg_color)

        # Place images
        y_offset = padding
        for row in range(len(row_heights)):
            x_offset = padding
            row_height = row_heights[row]

            for col in range(cols):
                idx = row * cols + col
                if idx < num_images:
                    img_idx = order[idx]
                    if img_idx < len(images):
                        img = images[img_idx]

                        # Calculate vertical position based on alignment
                        if alignment == "top":
                            y_pos = y_offset
                        elif alignment == "bottom":
                            y_pos = y_offset + row_height - img.height
                        else:  # center
                            y_pos = y_offset + (row_height - img.height) // 2

                        # Convert RGBA to RGB for pasting
                        if img.mode == 'RGBA':
                            bg = Image.new('RGB', img.size, self.bg_color)
                            bg.paste(img, mask=img.split()[3])
                            collage.paste(bg, (x_offset, y_pos))
                        else:
                            collage.paste(img, (x_offset, y_pos))

                x_offset += img_width + spacing

            y_offset += row_height + spacing

        return collage

    def batch_process(self):
        """Batch process all images, creating multiple collages based on grid size."""
        if not self.images:
            messagebox.showwarning("Warning", "No images loaded. Select a folder first.")
            return

        cols = self.cols.get()
        rows = self.rows.get()
        images_per_collage = cols * rows

        total_images = len(self.images)
        num_collages = (total_images + images_per_collage - 1) // images_per_collage  # Ceiling division

        # Select output folder
        output_dir = filedialog.askdirectory(title="Select Output Folder for Collages")
        if not output_dir:
            return

        # Confirm
        confirm = messagebox.askyesno(
            "Confirm Batch Processing",
            f"Found {total_images} images.\n\n"
            f"Layout: {cols} x {rows} = {images_per_collage} images per collage\n"
            f"Will create {num_collages} collage(s).\n\n"
            f"Output folder: {output_dir}\n\n"
            f"Continue?"
        )

        if not confirm:
            return

        success_count = 0
        error_count = 0

        for batch_idx in range(num_collages):
            start_idx = batch_idx * images_per_collage
            end_idx = min(start_idx + images_per_collage, total_images)
            batch_images = self.images[start_idx:end_idx]

            self.status_var.set(f"Processing batch {batch_idx + 1}/{num_collages}...")
            self.root.update()

            try:
                collage = self.generate_collage_from_images(batch_images)
                if collage:
                    output_filename = f"collage_{batch_idx + 1:03d}.png"
                    output_path = os.path.join(output_dir, output_filename)
                    collage.save(output_path)
                    success_count += 1
            except Exception as e:
                print(f"Failed to create collage {batch_idx + 1}: {e}")
                error_count += 1

        self.status_var.set(f"Batch complete: {success_count} collages created, {error_count} errors")
        messagebox.showinfo(
            "Batch Complete",
            f"Created {success_count} collage(s).\n"
            f"Errors: {error_count}\n\n"
            f"Output folder: {output_dir}"
        )


def main():
    root = tk.Tk()
    app = ImageCollage(root)
    root.mainloop()


if __name__ == "__main__":
    main()
