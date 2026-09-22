"""유튜브 검색 결과 목록.

행을 위젯이 아니라 캔버스 하나 위의 도형·글자·이미지로 그린다.
위젯으로 만들면 한 행에 창(윈도 핸들)이 열 개 가까이 생겨 100행이면 천 개가 넘고,
창 크기를 바꿀 때마다 Tk 가 그 창들을 전부 다시 배치해 1초 가까이 멈췄다.
캔버스 항목은 창이 아니라서 스크롤은 좌표 이동뿐이고, 창 크기 조정 때는
오른쪽에 붙은 항목의 x 좌표와 제목 줄바꿈만 다시 계산하면 된다.

결과는 받는 대로 뒤에 이어 붙이고, 조금씩 나눠 그린다.
이미 대기열에 있는 곡은 흐리게 표시하고 체크를 막는다.
"""
import ssl
import threading
import tkinter as tk
import tkinter.font as tkfont
import urllib.request
import webbrowser
from concurrent.futures import ThreadPoolExecutor
from io import BytesIO

import customtkinter as ctk
from PIL import Image, ImageOps, ImageTk

from ..formatting import SEARCH_INITIAL_TEXT, display_text
from ..theme import (
    C_ASH, C_BG, C_GRAPHITE, C_PEARL, C_STEEL, C_SURFACE_DEEP,
    C_TEXT, C_TEXT_DIM, C_TEXT_MUTED, FONT_FAMILY, FONT_ITEM,
)

THUMB_SIZE = (96, 54)     # 16:9. 유튜브 썸네일 비율과 같아야 찌그러지지 않는다
CHECK_SIZE = 18
ROW_HEIGHT = 72           # 제목 두 줄 + 채널 한 줄이 들어가는 높이 (배율 적용 전)
ROW_GAP = 4
RIGHT_GUTTER = 6          # 스크롤바와 행 사이
RENDER_CHUNK = 2          # 한 번에 그리는 행 수. 처음 보는 글자는 한 자에 약 5ms 라 조금씩 그린다
RENDER_DELAY_MS = 12      # 조각 사이 쉬는 시간. 이벤트 루프가 스크롤·입력을 처리할 틈
RESIZE_DEBOUNCE_MS = 40   # 창 크기를 끄는 동안에는 마지막 크기에서 한 번만 다시 배치한다


_ssl_context = None
_ssl_lock = threading.Lock()


def shared_ssl_context():
    """썸네일 요청이 함께 쓰는 SSL 설정.

    urlopen 은 요청마다 새 SSL 설정을 만들며 Windows 인증서 저장소를 통째로 읽는다.
    그 작업이 GIL 을 잡고 있어 썸네일 여섯 장을 받는 동안 화면이 0.4초씩 멈췄다.
    """
    global _ssl_context
    with _ssl_lock:
        if _ssl_context is None:
            _ssl_context = ssl.create_default_context()
        return _ssl_context


def fit_thumbnail(image, size):
    """비율이 달라도 찌그러뜨리지 않고 가운데를 잘라 크기를 맞춘다."""
    return ImageOps.fit(image.convert("RGB"), size, Image.Resampling.LANCZOS)


def char_units(ch):
    """글자 하나의 대략적인 폭 (한글 한 글자 = 1).

    정확한 폭은 Tk 에 물어야(font.measure) 하지만, 실제 제목에는 기호·다국어 글자가 섞여
    Windows 가 대체 글꼴을 찾느라 한 번에 수 ms 씩 걸린다. 100행이면 첫 화면이 0.4초 멈췄다.
    줄바꿈 자체는 캔버스가 하므로 여기서는 '두 줄을 넘길지' 만 넉넉히 가늠하면 된다.
    """
    code = ord(ch)
    if code >= 0x1100 and not (0x2000 <= code < 0x2E80):
        return 1.0          # 한글·한자·가나 등 전각
    return 0.56             # 라틴·숫자·기호


def clip_to_lines(text, width_px, em_px, max_lines=2):
    """폭 width_px 에 max_lines 줄 안에 들어가도록 끝을 '…' 로 자른다 (추정)."""
    if width_px <= 0 or not text:
        return text or ""
    # 줄 끝에서 단어가 넘어가며 생기는 빈칸을 감안해 한 줄에 90% 만 채운다고 본다
    budget = max_lines * width_px * 0.9 / em_px
    used = 0.0
    for i, ch in enumerate(text):
        used += char_units(ch)
        if used > budget:
            return text[:max(i - 1, 1)].rstrip() + "…"
    return text


class RowItems:
    """한 행을 이루는 캔버스 항목 묶음. 목록에서 위젯처럼 destroy() 로 지운다."""

    def __init__(self, canvas, tag):
        self.canvas = canvas
        self.tag = tag

    def destroy(self):
        try:
            self.canvas.delete(self.tag)
        except Exception:
            pass


class ScrollableSearchFrame(ctk.CTkFrame):
    """유튜브 검색 결과를 보여주는 스크롤 목록"""
    def __init__(self, master, **kwargs):
        kwargs.setdefault("fg_color", "transparent")
        super().__init__(master, corner_radius=0, **kwargs)
        self.search_widgets = []
        self.search_results_data = [] # 검색결과 저장용
        self.render_job = None        # 점진 렌더링 예약 핸들
        self.row_refs = {}            # 인덱스 -> 행 캔버스 항목 id
        self.is_queued = None         # url -> 대기열에 있는지. 앱이 채워 준다
        self.hide_queued = False
        self.on_change = None         # 선택이 바뀌면 개수를 다시 센다
        self._items = []              # 그릴 원본 결과. 이어 붙이기로 늘어난다
        self._next_row = 0            # 다음에 그릴 행 인덱스
        self._photos = {}             # 인덱스 -> PhotoImage. 참조를 잃으면 이미지가 사라진다
        self._resize_job = None
        self._visible_rows = 0
        self.thumb_executor = ThreadPoolExecutor(max_workers=4) # 썸네일 동시 다운로드 수 제한

        self._scale = ctk.ScalingTracker.get_widget_scaling(self)
        px = self._px
        self._fonts = {
            'title': tkfont.Font(family=FONT_FAMILY, size=-px(12), weight="bold"),
            'meta': tkfont.Font(family=FONT_FAMILY, size=-px(11)),
            'button': tkfont.Font(family=FONT_FAMILY, size=-px(11), weight="bold"),
            'caption': tkfont.Font(family=FONT_FAMILY, size=-px(10)),
        }

        # 배지 폭은 글자가 늘 같으므로 한 번만 잰다
        self._badge_w = self._fonts['caption'].measure("대기열에 있음") + px(12)

        self.grid_rowconfigure(0, weight=1)
        self.grid_columnconfigure(0, weight=1)
        self.canvas = tk.Canvas(self, bg=C_BG, highlightthickness=0, bd=0,
                                yscrollincrement=px(24))
        self.canvas.grid(row=0, column=0, sticky="nsew")
        self.scrollbar = ctk.CTkScrollbar(self, command=self.canvas.yview)
        self.scrollbar.grid(row=0, column=1, sticky="ns")
        self.canvas.configure(yscrollcommand=self.scrollbar.set)
        self._width = 1

        self.canvas.bind("<Configure>", self._on_configure)
        # 휠은 전역으로 받되 포인터가 이 목록 위에 있을 때만 움직인다.
        # add="+" 가 없으면 다른 스크롤 목록(대기열·파일)의 휠 처리를 덮어쓴다.
        self.canvas.bind_all("<MouseWheel>", self._on_wheel, add="+")

    # ------------------------------------------------------------------
    # 배율 · 스크롤 · 크기
    # ------------------------------------------------------------------
    def _px(self, value):
        return int(round(value * self._scale))

    def _on_wheel(self, event):
        try:
            under = self.winfo_containing(event.x_root, event.y_root)
        except Exception:
            return
        if under is not self.canvas or not self.canvas.winfo_ismapped():
            return
        if self.canvas.yview() != (0.0, 1.0):
            self.canvas.yview_scroll(int(-event.delta / 120) * 2, "units")

    def _on_configure(self, event):
        self._width = event.width
        if self._resize_job is not None:
            self.after_cancel(self._resize_job)
        self._resize_job = self.after(RESIZE_DEBOUNCE_MS, self._relayout_x)

    def _relayout_x(self):
        self._resize_job = None
        for idx in self.row_refs:
            self._layout_row_x(idx)
        self._update_scrollregion()

    def _update_scrollregion(self):
        visible = sum(1 for idx in self.row_refs if self._row_visible(idx))
        height = visible * self._px(ROW_HEIGHT + ROW_GAP)
        self.canvas.configure(scrollregion=(0, 0, self._width, max(height, 1)))

    # ------------------------------------------------------------------
    # 썸네일
    # ------------------------------------------------------------------
    def load_thumbnail_async(self, thumb_url, idx, generation):
        """작업 스레드에서 받고 자른다. PhotoImage 는 Tk 객체라 메인 스레드에서 만든다."""
        try:
            if not thumb_url:
                return
            req = urllib.request.Request(
                thumb_url,
                headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
            )
            with urllib.request.urlopen(req, timeout=5, context=shared_ssl_context()) as response:
                data = response.read()
            size = (self._px(THUMB_SIZE[0]), self._px(THUMB_SIZE[1]))
            img = fit_thumbnail(Image.open(BytesIO(data)), size)
            self.after(0, self._set_thumbnail, idx, generation, img)
        except Exception:
            pass   # 자리표시 회색 칸이 그대로 남는다

    def _set_thumbnail(self, idx, generation, img):
        refs = self.row_refs.get(idx)
        if refs is None or generation is not self._items:
            return   # 그사이 새 검색이 시작됐다
        photo = ImageTk.PhotoImage(img)
        self._photos[idx] = photo
        self.canvas.itemconfigure(refs['image'], image=photo)

    # ------------------------------------------------------------------
    # 채우기
    # ------------------------------------------------------------------
    def cancel_render(self):
        """진행 중인 점진 렌더링을 취소한다. 새 검색이 들어오면 반드시 호출해야 한다."""
        if self.render_job is not None:
            try:
                self.after_cancel(self.render_job)
            except Exception:
                pass
            self.render_job = None

    def populate_results(self, results, empty_text=SEARCH_INITIAL_TEXT):
        self.cancel_render()
        for widget in self.search_widgets:
            widget.destroy()
        self.search_widgets.clear()
        self.search_results_data.clear()
        self.row_refs = {}
        self._photos = {}
        self._items = []
        self._next_row = 0
        self._visible_rows = 0
        canvas = getattr(self, 'canvas', None)
        if canvas is not None:
            canvas.yview_moveto(0)
            self._update_scrollregion()

        if not results:
            label = ctk.CTkLabel(self, text=empty_text, font=FONT_ITEM, text_color=C_TEXT_DIM)
            label.place(relx=0.5, y=40, anchor="n")
            self.search_widgets.append(label)
            return

        self._add_data(results)
        # 100건을 한 번에 그리면 UI 가 멈춘다.
        # 한 번에 조금씩 그려 이벤트 루프에 숨 쉴 틈을 준다.
        self._render_chunk(self._items, 0)

    def append_results(self, results):
        """받는 대로 뒤에 이어 붙인다. 앞서 그린 행은 건드리지 않는다."""
        if not results:
            return
        if not self._items:
            self.populate_results(results)
            return
        self._add_data(results)
        if self.render_job is None:
            # 앞 조각을 다 그려 쉬고 있었다면 이어서 그리기 시작한다
            self._render_chunk(self._items, self._next_row)

    def _add_data(self, results):
        # 데이터는 즉시 전부 채운다. 위젯만 나눠 그린다.
        # 그러지 않으면 렌더링이 끝나기 전에 '선택 항목 추가' 를 누른 곡이 누락된다.
        for item in results:
            self._items.append(item)
            self.search_results_data.append({
                'title': item['title'],
                'url': item['url'],
                'duration': item['duration'],
                'uploader': item['uploader'],
                'check_var': ctk.BooleanVar(value=False),
            })

    def _render_chunk(self, results, start, chunk_size=RENDER_CHUNK):
        self.render_job = None

        # 새 검색이 데이터를 비운 뒤 낡은 청크가 돌면 인덱스가 어긋난다.
        # 취소가 한 박자 늦을 수 있으므로 여기서도 확인한다.
        if len(self.search_results_data) != len(results):
            return

        for idx, item in enumerate(results[start:start + chunk_size], start=start):
            try:
                self._render_row(idx, item)
            except Exception:
                # 한 행의 실패로 나머지 결과가 통째로 사라지면 안 된다
                pass

        next_start = start + chunk_size
        self._next_row = min(next_start, len(results))
        if next_start < len(results):
            self.render_job = self.after(
                RENDER_DELAY_MS, self._render_chunk, results, next_start, chunk_size)

    # ------------------------------------------------------------------
    # 한 행
    # ------------------------------------------------------------------
    def _render_row(self, idx, item):
        px = self._px
        c = self.canvas
        tag = f"row{idx}"
        hit = f"hit{idx}"      # 누르면 체크가 바뀌는 부분 (재생 버튼 빼고 전부)
        play_tag = f"play{idx}"
        h = px(ROW_HEIGHT)

        refs = {'tag': tag, 'y': 0}
        refs['bg'] = c.create_rectangle(0, 0, 1, h, fill=C_SURFACE_DEEP, outline=C_SURFACE_DEEP,
                                        tags=(tag, hit))
        cx, cy, cs = px(12), (h - px(CHECK_SIZE)) // 2, px(CHECK_SIZE)
        refs['check'] = c.create_rectangle(cx, cy, cx + cs - 1, cy + cs - 1, outline=C_STEEL,
                                           fill=C_SURFACE_DEEP, tags=(tag, hit))
        s = cs / 18
        refs['tick'] = c.create_line(cx + 4 * s, cy + 9 * s, cx + 7.5 * s, cy + 12.5 * s,
                                     cx + 14 * s, cy + 5.5 * s, fill=C_SURFACE_DEEP,
                                     width=max(2, int(2 * s)), state="hidden", tags=(tag, hit))
        tx, ty = cx + cs + px(10), (h - px(THUMB_SIZE[1])) // 2
        c.create_rectangle(tx, ty, tx + px(THUMB_SIZE[0]) - 1, ty + px(THUMB_SIZE[1]) - 1,
                           fill=C_GRAPHITE, outline=C_GRAPHITE, tags=(tag, hit))
        refs['image'] = c.create_image(tx, ty, anchor="nw", tags=(tag, hit))
        # 재생 시간은 밝은 썸네일 위에서도 읽히도록 검은 바탕을 깐다
        dur = c.create_text(tx + px(THUMB_SIZE[0]) - px(4), ty + px(THUMB_SIZE[1]) - px(3),
                            text=item['duration'], anchor="se", fill=C_PEARL,
                            font=self._fonts['caption'], tags=(tag, hit))
        x1, y1, x2, y2 = c.bbox(dur)
        dur_bg = c.create_rectangle(x1 - px(3), y1, x2 + px(2), y2, fill=C_SURFACE_DEEP,
                                    outline=C_SURFACE_DEEP, tags=(tag, hit))
        c.tag_raise(dur, dur_bg)

        refs['text_x'] = tx + px(THUMB_SIZE[0]) + px(14)
        refs['title_src'] = display_text(item['title'])
        refs['title'] = c.create_text(refs['text_x'], px(12), anchor="nw", text=refs['title_src'],
                                      fill=C_TEXT, font=self._fonts['title'], tags=(tag, hit))
        refs['meta'] = c.create_text(refs['text_x'], h - px(12), anchor="sw",
                                     text=display_text(item['uploader']), fill=C_ASH,
                                     font=self._fonts['meta'], tags=(tag, hit))

        refs['play_bg'] = c.create_rectangle(0, 0, 1, 1, fill=C_SURFACE_DEEP, outline=C_STEEL,
                                             tags=(tag, play_tag))
        refs['play_text'] = c.create_text(0, 0, text="▶ 재생", fill=C_PEARL,
                                          font=self._fonts['button'], tags=(tag, play_tag))
        refs['badge_bg'] = c.create_rectangle(0, 0, 1, 1, fill=C_SURFACE_DEEP, outline=C_GRAPHITE,
                                              state="hidden", tags=(tag, hit))
        refs['badge_text'] = c.create_text(0, 0, text="대기열에 있음", fill=C_ASH,
                                           font=self._fonts['caption'], state="hidden",
                                           tags=(tag, hit))

        c.tag_bind(hit, "<Button-1>", lambda _e, i=idx: self._toggle(i))
        c.tag_bind(play_tag, "<Button-1>", lambda _e, url=item['url']: webbrowser.open(url))
        c.tag_bind(play_tag, "<Enter>", lambda _e, r=refs: self._hover_play(r, True))
        c.tag_bind(play_tag, "<Leave>", lambda _e, r=refs: self._hover_play(r, False))

        self.row_refs[idx] = refs
        self.search_widgets.append(RowItems(c, tag))

        check_var = self.search_results_data[idx]['check_var']
        check_var.trace_add("write", lambda *_a, i=idx: self._apply_row_state(i))

        # 새 행은 늘 맨 뒤에 붙으므로 보이는 행 수만큼 내려 놓는다. 전체를 다시 쌓지 않는다
        if self._row_visible(idx):
            refs['y'] = self._visible_rows * self._px(ROW_HEIGHT + ROW_GAP)
            c.move(tag, 0, refs['y'])
            self._visible_rows += 1
        else:
            c.itemconfigure(tag, state="hidden")
        self._layout_row_x(idx)
        self._apply_row_state(idx)
        self._update_scrollregion()

        self.thumb_executor.submit(self.load_thumbnail_async, item.get('thumbnail'), idx, self._items)

    def _hover_play(self, refs, inside):
        self.canvas.itemconfigure(refs['play_bg'], fill=C_GRAPHITE if inside else C_SURFACE_DEEP)
        self.canvas.configure(cursor="hand2" if inside else "")

    def _layout_row_x(self, idx):
        """창 폭에 따라 달라지는 것: 배경 폭, 재생 버튼·배지 위치, 제목 줄바꿈."""
        refs = self.row_refs[idx]
        px, c, y = self._px, self.canvas, refs['y']
        h = px(ROW_HEIGHT)
        right = self._width - px(RIGHT_GUTTER)
        c.coords(refs['bg'], 0, y, right, y + h)

        bw, bh = px(64), px(26)
        bx2, by = right - px(12), y + (h - bh) // 2
        c.coords(refs['play_bg'], bx2 - bw, by, bx2, by + bh)
        c.coords(refs['play_text'], bx2 - bw / 2, by + bh / 2)

        badge_w = self._badge_w
        gx2 = bx2 - bw - px(8)
        c.coords(refs['badge_bg'], gx2 - badge_w, by + px(3), gx2, by + bh - px(3))
        c.coords(refs['badge_text'], gx2 - badge_w / 2, by + bh / 2)

        # 줄바꿈은 캔버스가 한다(width). 여기서는 두 줄을 넘지 않게 끝만 자른다
        title_w = max(gx2 - badge_w - px(12) - refs['text_x'], px(80))
        c.itemconfigure(refs['title'], width=title_w,
                        text=clip_to_lines(refs['title_src'], title_w, px(12)))

    def _row_visible(self, idx):
        return not (self.hide_queued and self._queued(idx))

    def _relayout_y(self):
        """보이는 행만 순서대로 쌓는다. 숨긴 행은 감추고 뒤 행을 끌어올린다."""
        step = self._px(ROW_HEIGHT + ROW_GAP)
        pos = 0
        # 숨겼던 항목을 되살릴 때 상태를 한꺼번에 normal 로 바꾸면 배지·체크 표시가
        # 감춰야 할 것까지 드러나므로, 각 행의 상태를 다시 칠한다
        for idx in sorted(self.row_refs):
            refs = self.row_refs[idx]
            visible = self._row_visible(idx)
            if visible:
                new_y = pos * step
                if new_y != refs['y']:
                    self.canvas.move(refs['tag'], 0, new_y - refs['y'])
                    refs['y'] = new_y
                pos += 1
            self.canvas.itemconfigure(refs['tag'], state="normal" if visible else "hidden")
            if visible:
                self._apply_row_state(idx)
        self._visible_rows = pos
        self._update_scrollregion()

    def _toggle(self, idx):
        if self._queued(idx):
            return
        var = self.search_results_data[idx]['check_var']
        var.set(not var.get())
        if self.on_change:
            self.on_change()

    def _queued(self, idx):
        if self.is_queued is None:
            return False
        return self.is_queued(self.search_results_data[idx]['url'])

    def _apply_row_state(self, idx):
        """대기열 포함 여부와 체크 상태를 행 모양에 반영한다."""
        refs = self.row_refs.get(idx)
        if not refs:
            return
        data = self.search_results_data[idx]
        queued = self._queued(idx)
        if queued and data['check_var'].get():
            # 이미 담긴 곡은 선택에서 뺀다. 남겨 두면 '이미 대기열에 있음' 안내만 반복된다
            data['check_var'].set(False)   # trace 로 이 함수가 한 번 더 불린다
            return
        selected = data['check_var'].get()
        c = self.canvas
        c.itemconfigure(refs['check'], outline=C_GRAPHITE if queued else C_STEEL,
                        fill=C_PEARL if selected else C_SURFACE_DEEP)
        c.itemconfigure(refs['tick'], state="normal" if selected else "hidden")
        c.itemconfigure(refs['title'], fill=C_TEXT_MUTED if queued else C_TEXT)
        badge_state = "normal" if queued else "hidden"
        c.itemconfigure(refs['badge_bg'], state=badge_state)
        c.itemconfigure(refs['badge_text'], state=badge_state)
        c.itemconfigure(refs['bg'], outline=C_STEEL if selected else C_SURFACE_DEEP)

    def refresh_queued(self):
        """대기열이 바뀌거나 숨기기 옵션이 바뀌면 전체 행을 다시 칠하고 다시 쌓는다."""
        if getattr(self, 'canvas', None) is not None:
            self._relayout_y()
        if self.on_change:
            self.on_change()

    def selected_count(self):
        return sum(1 for item in self.search_results_data if item['check_var'].get())

    def get_selected_items(self):
        selected = []
        for item in self.search_results_data:
            if item['check_var'].get():
                selected.append({
                    'title': item['title'],
                    'url': item['url'],
                    'duration': item['duration'],
                    'uploader': item['uploader']
                })
        return selected
