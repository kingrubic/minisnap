"""UI language. Vietnamese text in the code is the key; English comes from the table below
(windows/src/Strings.cs, plus Linux-specific entries). Text without an entry is shown unchanged;
the self-test fails if any L.t("…") literal in the package has no English entry.
"""

import os

from . import settings


class L:
    english = False

    @staticmethod
    def t(vi):
        if L.english:
            return EN.get(vi, vi)
        return vi

    @staticmethod
    def has(vi):
        return vi in EN

    @staticmethod
    def load():
        """MINISNAP_LANG=en|vi overrides; then the saved choice; then LANG (vi* = Vietnamese)."""
        over = os.environ.get("MINISNAP_LANG")
        if over:
            L.english = over == "en"
            return
        saved = settings.get("language")
        if saved in ("vi", "en"):
            L.english = saved == "en"
            return
        lang = ""
        for var in ("LANGUAGE", "LC_ALL", "LC_MESSAGES", "LANG"):
            lang = os.environ.get(var, "")
            if lang:
                break
        L.english = not lang.lower().startswith("vi")

    @staticmethod
    def set(english, persist=True):
        L.english = bool(english)
        if persist:
            settings.set("language", "en" if english else "vi")


EN = {
    # Launcher, menu, notifications
    "Chụp vùng / cửa sổ": "Capture region / window",
    "Chụp toàn màn hình": "Capture full screen",
    "Chụp vùng sau 3 giây": "Capture region after 3 seconds",
    "Chụp sau 3 giây": "Capture after 3 seconds",
    "Chọn cửa sổ": "Pick a window",
    "Hệ thống sẽ cho bạn chọn cửa sổ cần chụp, ảnh mở thẳng trong trình chỉnh sửa":
        "Your desktop lets you pick the window to capture; the image opens straight in the editor",
    "Chụp cuộn trang dài": "Scrolling capture",
    "Quay video màn hình": "Record screen video",
    "Dừng quay video": "Stop recording",
    "Quay video (bắt đầu / dừng)": "Record video (start / stop)",
    "Chụp và trích chữ (OCR)": "Capture and extract text (OCR)",
    "Thư viện ảnh & video": "Image & video library",
    "Mở thư viện ảnh & video": "Open image & video library",
    "Mở ảnh...": "Open image...",
    "Cài đặt phím tắt...": "Keyboard shortcuts...",
    "Phím tắt bàn phím…": "Keyboard shortcuts…",
    "Menu chính": "Main menu",
    "Thoát MiniSnap": "Exit MiniSnap",
    "MiniSnap đã sẵn sàng": "MiniSnap is ready",
    "Chụp ảnh, quay video màn hình và trích chữ": "Screenshots, screen recording and text extraction",
    "Mẹo: đặt phím tắt trong menu ☰ → Phím tắt bàn phím… để chụp nhanh từ bất cứ đâu.":
        "Tip: set up shortcuts in the ☰ menu → Keyboard shortcuts… to capture from anywhere.",
    "Sẽ chụp sau ": "Capturing in ",
    " giây...": " seconds...",
    "Quay video: chọn cửa sổ hoặc kéo chọn vùng cần quay (Enter = toàn màn hình)":
        "Record video: drag an area or click a screen (Enter = whole screen)",
    "Trích chữ: chọn vùng có chữ cần lấy": "Extract text: select the area containing the text",
    "Không quay được video:\n": "Could not record video:\n",
    "Đã lưu video": "Video saved",
    "Bấm vào đây để xem.": "Click here to see it.",
    "Không mở được ảnh:\n": "Could not open the image:\n",
    "Không lưu được cài đặt:\n": "Could not save the settings:\n",
    "MiniSnap - lỗi": "MiniSnap - error",
    "Chú thích tiếng Việt": "Sample annotation",

    # Screenshot portal
    "Không chụp được màn hình": "Couldn't take a screenshot",
    "MiniSnap chụp màn hình qua xdg-desktop-portal. Hãy kiểm tra gói xdg-desktop-portal và xdg-desktop-portal-gnome (hoặc -kde, -wlr) đã được cài, rồi thử lại.":
        "MiniSnap takes screenshots through xdg-desktop-portal. Make sure the xdg-desktop-portal and "
        "xdg-desktop-portal-gnome (or -kde, -wlr) packages are installed, then try again.",

    # Editor
    "Chọn": "Select",
    "Mũi tên": "Arrow",
    "Khung": "Box",
    "Elip": "Ellipse",
    "Đường": "Line",
    "Bút vẽ": "Pen",
    "Tô sáng": "Highlight",
    "Chữ": "Text",
    "Làm mờ": "Blur",
    "Đánh số": "Step",
    "Cắt ảnh": "Crop",
    "Trích chữ": "Extract text",
    "Thư viện": "Library",
    "Chụp mới": "New capture",
    "Sao chép": "Copy",
    "Lưu": "Save",
    "Lưu thành...": "Save as...",
    "✓ Đã chép": "✓ Copied",
    "✓ Đã lưu": "✓ Saved",
    "Chọn, kéo để di chuyển, Delete để xoá. Nháy đúp vào chữ để sửa":
        "Select, drag to move, Delete to remove. Double-click text to edit it",
    "Vẽ mũi tên (giữ Shift để thẳng góc 45°)": "Draw an arrow (hold Shift to snap to 45°)",
    "Vẽ khung chữ nhật (Shift: hình vuông)": "Draw a rectangle (Shift: square)",
    "Vẽ elip (Shift: hình tròn)": "Draw an ellipse (Shift: circle)",
    "Vẽ đường thẳng": "Draw a straight line",
    "Vẽ tự do": "Draw freehand",
    "Tô sáng một vùng (nên chọn màu vàng)": "Highlight an area (yellow works best)",
    "Bấm để gõ chữ. Enter để xong, Shift+Enter xuống dòng": "Click to type. Enter to finish, Shift+Enter for a new line",
    "Làm mờ thông tin nhạy cảm": "Blur sensitive information",
    "Bấm để đặt số bước 1, 2, 3...": "Click to place step numbers 1, 2, 3...",
    "Kéo chọn vùng muốn giữ lại": "Drag over the area to keep",
    "Nhận dạng chữ trong ảnh (OCR) và sao chép": "Recognize text in the image (OCR) and copy it",
    "Mở thư viện ảnh và video": "Open the image and video library",
    "Chụp ảnh mới": "Take a new capture",
    "Lưu thành file khác (Ctrl+Shift+S)": "Save to another file (Ctrl+Shift+S)",
    "Lưu ảnh (Ctrl+S)": "Save image (Ctrl+S)",
    "Sao chép ảnh vào clipboard để dán (Ctrl+C)": "Copy the image to the clipboard to paste (Ctrl+C)",
    "Màu:": "Color:",
    "Khác...": "More...",
    "Chọn màu khác": "Pick another color",
    "Độ dày:": "Size:",
    "Hoàn tác": "Undo",
    "Làm lại": "Redo",
    "Mở thư mục ảnh đã chụp": "Open the captures folder",
    "Thu nhỏ": "Zoom out",
    "Phóng to": "Zoom in",
    "Vừa": "Fit",
    "Vừa cửa sổ": "Fit to window",
    "Kích thước thật": "Actual size",
    "Kéo để vẽ • Shift: giữ thẳng/vuông • Ctrl+lăn chuột: phóng to • Ảnh đã tự lưu và sao chép vào clipboard":
        "Drag to draw • Shift: straight/square • Ctrl+wheel: zoom • Image auto-saved and copied to clipboard",
    "Ảnh chưa lưu": "Unsaved image",
    "Vùng cắt: ": "Crop: ",
    " px — thả chuột để cắt, Esc để huỷ": " px — release to crop, Esc to cancel",
    "Gõ chữ • Enter: xong • Shift+Enter: xuống dòng • Esc: huỷ": "Type • Enter: done • Shift+Enter: new line • Esc: cancel",
    "Đã sao chép ảnh vào clipboard — dán (Ctrl+V) vào Zalo, Word, email...":
        "Image copied — paste it (Ctrl+V) into chat, a document, email...",
    "Clipboard đang bận, hãy thử lại.": "The clipboard is busy, please try again.",
    "Không lưu được ảnh:\n": "Could not save the image:\n",
    "Đã lưu: ": "Saved: ",
    "Lưu các thay đổi vào ảnh?": "Save changes to the image?",
    "Không lưu": "Don't save",

    # Library
    "Thư viện — MiniSnap": "Library — MiniSnap",
    "Tất cả": "All",
    "Ảnh": "Images",
    "Video": "Videos",
    "Tìm:": "Search:",
    "Làm mới": "Refresh",
    "Thư mục ảnh": "Images folder",
    "Thư mục video": "Videos folder",
    "Mở": "Open",
    "Trích chữ (OCR)": "Extract text (OCR)",
    "Hiện trong thư mục": "Show in folder",
    "Xoá (vào Thùng rác)": "Delete (to Trash)",
    "Chuyển vào Thùng rác": "Move to Trash",
    "Chưa có ảnh hay video nào.\n": "No images or videos yet.\n",
    "Chưa có ảnh hay video nào.": "No images or videos yet.",
    "Dùng cửa sổ MiniSnap hoặc phím tắt bạn đã đặt để chụp.": "Use the MiniSnap window or your keyboard shortcuts to capture.",
    "Hôm nay": "Today",
    "Hôm qua": "Yesterday",
    "7 ngày qua": "Last 7 days",
    "Tháng này": "This month",
    "Cũ hơn": "Older",
    " ảnh • ": " images • ",
    " video   —   ": " videos   —   ",
    "Đã sao chép ": "Copied ",
    " vào clipboard": " to the clipboard",
    " mục": " items",
    "Không sao chép được: ": "Could not copy: ",
    "Chuyển ": "Move ",
    " vào Thùng rác?": " to the Trash?",
    "Không xoá được ": "Could not delete ",

    # OCR
    "Trích chữ (OCR) — MiniSnap": "Extract text (OCR) — MiniSnap",
    "Đang nhận dạng chữ...": "Recognizing text...",
    "Đóng": "Close",
    "Sao chép chữ": "Copy text",
    "✓ Đã sao chép": "✓ Copied",
    "Không nhận dạng được chữ: ": "Could not recognize text: ",
    "(Không tìm thấy chữ nào trong ảnh)": "(No text found in the image)",
    "Ngôn ngữ: ": "Language: ",
    "OCR thất bại: ": "OCR failed: ",
    "Chưa cài tesseract nên chưa trích chữ được.": "Text recognition needs tesseract, which is not installed.",
    "Cài bằng lệnh:": "Install it with:",
    "Tesseract chưa có dữ liệu ngôn ngữ nào.": "Tesseract has no language data installed.",
    "Muốn đọc tiếng Việt có dấu: sudo apt install tesseract-ocr-vie":
        "For Vietnamese text: sudo apt install tesseract-ocr-vie",

    # Scrolling capture, recording
    "Đang chuẩn bị chụp cuộn...": "Preparing scrolling capture...",
    "Dừng (Esc)": "Stop (Esc)",
    "Đang chụp cuộn... ": "Scrolling capture... ",
    " lần, cao ": " shots, height ",
    "Bắt đầu sau 3...": "Starting in 3...",
    "Bắt đầu sau ": "Starting in ",
    "Tạm dừng": "Pause",
    "Tiếp tục": "Resume",
    "Dừng": "Stop",
    "Đang lưu video...": "Saving video...",
    "Thiếu GStreamer. Hãy cài: sudo apt install gir1.2-gstreamer-1.0 gstreamer1.0-pipewire gstreamer1.0-plugins-ugly":
        "GStreamer is missing. Install it: sudo apt install gir1.2-gstreamer-1.0 gstreamer1.0-pipewire gstreamer1.0-plugins-ugly",
    "Thiếu gói gstreamer1.0-pipewire để quay màn hình.": "Screen recording needs the gstreamer1.0-pipewire package.",
    "Không tìm thấy bộ mã hoá video. Hãy cài: sudo apt install gstreamer1.0-plugins-ugly":
        "No video encoder found. Install one: sudo apt install gstreamer1.0-plugins-ugly",
    "Không bắt đầu quay được (GStreamer).": "Could not start recording (GStreamer).",

    # Keyboard shortcuts help
    "Phím tắt bàn phím — MiniSnap": "Keyboard shortcuts — MiniSnap",
    "Trên Linux, phím tắt toàn cục được đặt trong Cài đặt của hệ thống. Mỗi phím tắt chạy một lệnh MiniSnap; nếu MiniSnap đang chạy, lệnh được chuyển cho cửa sổ đang mở.":
        "On Linux, global shortcuts are set in the system Settings. Each shortcut runs a MiniSnap command; "
        "if MiniSnap is already running, the command is passed to it.",
    "1. Mở Cài đặt → Bàn phím → Xem và tuỳ chỉnh phím tắt → Phím tắt tự tạo.":
        "1. Open Settings → Keyboard → View and Customize Shortcuts → Custom Shortcuts.",
    "2. Bấm + (Thêm phím tắt), đặt tên, dán lệnh bên dưới vào ô Lệnh.":
        "2. Click + (Add Shortcut), enter a name and paste a command from below into Command.",
    "3. Bấm Đặt phím tắt… rồi nhấn tổ hợp phím, ví dụ Ctrl+Alt+C.":
        "3. Click Set Shortcut… and press the key combination, for example Ctrl+Alt+C.",
    "Lệnh": "Commands",
    "Gợi ý: ": "Suggested: ",
    "Phím Print Screen đang được GNOME dùng cho công cụ chụp màn hình của nó. Muốn dùng Print Screen cho MiniSnap, hãy bỏ phím đó ở mục Chụp màn hình trong Cài đặt → Bàn phím trước.":
        "GNOME uses the Print Screen key for its own screenshot tool. To use Print Screen for MiniSnap, "
        "first remove it under Screenshots in Settings → Keyboard.",
    "Mở Cài đặt bàn phím": "Open Keyboard Settings",

    # About
    "Giới thiệu MiniSnap...": "About MiniSnap...",
    "Giới thiệu MiniSnap": "About MiniSnap",
    "Đây là phần mềm chụp ảnh, quay phim màn hình miễn phí, mã nguồn mở dành cho mọi người.":
        "Free, open-source screenshot and screen recording software for everyone.",
    "Tác giả: ": "Author: ",
    "Liên hệ: ": "Contact: ",
    "Mã nguồn: ": "Source code: ",
    "Giấy phép MIT — miễn phí, mã nguồn mở": "MIT License — free and open source",
    "Mở trang GitHub": "Open on GitHub",
    "Quyền riêng tư: ": "Privacy: ",
    "MiniSnap không thu thập dữ liệu": "MiniSnap collects no data",

    # Updates
    "Kiểm tra cập nhật...": "Check for updates...",
    "Kiểm tra cập nhật": "Check for updates",
    "Cập nhật MiniSnap": "Update MiniSnap",
    "Đang kiểm tra cập nhật...": "Checking for updates...",
    "Phiên bản hiện tại: ": "Current version: ",
    "Không kiểm tra được cập nhật": "Couldn't check for updates",
    "\nHãy kiểm tra kết nối mạng rồi thử lại.": "\nCheck your internet connection and try again.",
    "Bạn đang dùng bản mới nhất": "You're up to date",
    "Chưa có bản phát hành nào trên GitHub. Phiên bản hiện tại: ": "No release has been published on GitHub yet. Current version: ",
    " — mới nhất trên GitHub: ": " — latest on GitHub: ",
    "Có phiên bản mới: ": "New version available: ",
    "Bạn đang dùng ": "You have ",
    ". Ảnh, video và cài đặt của bạn được giữ nguyên khi cập nhật.": ". Your captures and settings are kept when updating.",
    "\nHãy tải bản mới cho Linux trên trang GitHub.": "\nDownload the new Linux version from the GitHub page.",
    "Xem trên GitHub": "View on GitHub",
    "Để sau": "Later",
    "Có bản MiniSnap mới: ": "New MiniSnap version: ",
    "Tự kiểm tra cập nhật hằng ngày": "Check for updates daily",
    "Tự kiểm tra bản mới mỗi ngày (chỉ gửi một yêu cầu tới api.github.com — xem PRIVACY.md)":
        "Check for new versions daily (sends only one request to api.github.com — see PRIVACY.md)",

    # Post-selection mode bar
    "Chụp ảnh (Enter)": "Screenshot (Enter)",
    "Quay video (V)": "Record video (V)",
    "Chụp cuộn (S)": "Scrolling capture (S)",
    "Chụp cuộn sẽ có ở bản sau": "Scrolling capture comes in the next version",
    "Chọn lại (R)": "Reselect (R)",
    "Huỷ (Esc)": "Cancel (Esc)",
    "Rộng (px) — nhập rồi nhấn Enter": "Width (px) — type and press Enter",
    "Cao (px) — nhập rồi nhấn Enter": "Height (px) — type and press Enter",
    "Hỏi chụp ảnh / quay video / chụp cuộn sau khi chọn vùng": "Ask screenshot / video / scroll after selecting",

    # Generic
    "Huỷ": "Cancel",
    "Phiên bản ": "Version ",
}
