# health_app.py
from kivy.config import Config
Config.set('graphics', 'width', '1024')

from kivy.logger import Logger
Logger.info("Main: Starting MyApp")

from kivy.utils import platform
import os
import traceback
from datetime import datetime
import sqlite3
import threading
import qrcode
from kivy.storage.jsonstore import JsonStore
from kivy.app import App
from kivy.app import App
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.floatlayout import FloatLayout
from kivy.uix.label import Label
from kivy.uix.textinput import TextInput
from kivy.uix.button import Button
from kivy.uix.image import Image
from kivy.uix.screenmanager import ScreenManager, Screen
from kivy.uix.anchorlayout import AnchorLayout
from kivy.core.window import Window
from kivy.uix.popup import Popup
from kivy.uix.scrollview import ScrollView
from kivy.uix.gridlayout import GridLayout
from kivy.uix.video import Video
from kivy.metrics import dp, sp
from kivy.uix.widget import Widget
from kivy.clock import Clock

# Optional sms_alert: make sure sms_alert.send_sms exists in your project
try:
    from sms_alert import send_sms
except Exception:
    # Fallback stub so app won't crash if sms_alert missing during development
    def send_sms(number, message):
        Logger.info(f"SMS: would send to {number}: {message}")

Window.softinput_mode = "below_target"
db_lock = threading.Lock()


# ---------------------------
# File / storage helpers
# ---------------------------
def get_log_path():
    if platform == 'android':
        # import inside function to avoid import errors on desktop
        from android.storage import app_storage_path
        app_path = app_storage_path()
        log_path = os.path.join(app_path, "myapp_start.log")
    else:
        log_path = os.path.expanduser("~/kivy_projects/my_health_app/myapp_start.log")

    os.makedirs(os.path.dirname(log_path), exist_ok=True)
    return log_path


try:
    log_path = get_log_path()
    with open(log_path, "w", encoding="utf-8") as f:
        f.write("Starting app\n")
except Exception as e:
    print(f"Error writing log file: {e}")


def generate_qr_code(data, filename):
    img = qrcode.make(data)
    if not filename.lower().endswith('.png'):
        filename += '.png'
    # choose storage directory per platform
    if platform == 'android':
        from android.storage import app_storage_path
        save_dir = app_storage_path()
    else:
        save_dir = os.path.expanduser("~/kivy_projects/my_health_app")
    os.makedirs(save_dir, exist_ok=True)
    full_path = os.path.join(save_dir, filename)
    img.save(full_path)
    return full_path

def get_db_path():
    """
    Return a safe writable DB path.
    Prefer App.user_data_dir when the app exists (Android and desktop).
    Falls back to a safe subfolder under the user's home directory.
    """
    # If App is running, use its user_data_dir (Android will have a writable private dir)
    app = App.get_running_app()
    if app and hasattr(app, "user_data_dir") and app.user_data_dir:
        base = app.user_data_dir
    else:
        # Fallback to a per-user folder inside HOME (not root '/data')
        home = os.path.expanduser("~")
        base = os.path.join(home, ".my_health_app")

    try:
        os.makedirs(base, exist_ok=True)
    except Exception as e:
        # Last-resort: try current working directory
        try:
            base = os.getcwd()
            os.makedirs(base, exist_ok=True)
        except Exception:
            # if even this fails, raise the original error so we see it in logs
            raise e

    return os.path.join(base, "health_records.db")


# --- create_db() function (no top-level call) ---
def create_db():
    db_path = get_db_path()
    # Ensure parent dir exists
    db_dir = os.path.dirname(db_path)
    if db_dir and not os.path.exists(db_dir):
        os.makedirs(db_dir, exist_ok=True)

    # Create table(s) safely
    try:
        with sqlite3.connect(db_path, timeout=10) as conn:
            cursor = conn.cursor()
            # Use WAL mode for better concurrency on Android
            cursor.execute("PRAGMA journal_mode=WAL;")

            # Create table if it does not exist
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS patients (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT,
                    age INTEGER,
                    gender TEXT,
                    contact TEXT,
                    address TEXT,
                    conditions TEXT,
                    medications TEXT,
                    doctor_name TEXT,
                    last_visit TEXT,
                    notes TEXT
                )
            ''')
            conn.commit()
    except Exception:
        # Write a helpful error_log inside the app data dir (if available)
        try:
            base = App.get_running_app().user_data_dir if App.get_running_app() else os.path.expanduser("~/.my_health_app")
            os.makedirs(base, exist_ok=True)
            with open(os.path.join(base, "error_log.txt"), "a", encoding="utf-8") as f:
                f.write("create_db() exception:\n")
                f.write(traceback.format_exc())
        except Exception:
            # If logging also fails, just re-raise the original exception
            raise
def get_store():
    # Use App.user_data_dir once app is running; else fallback to home folder
    app = App.get_running_app()
    base = app.user_data_dir if (app and hasattr(app, "user_data_dir")) else os.path.expanduser("~/.my_health_app")
    os.makedirs(base, exist_ok=True)
    return JsonStore(os.path.join(base, "user_store.json"))
from kivy.uix.screenmanager import Screen
from kivy.uix.floatlayout import FloatLayout
from kivy.uix.image import Image
from kivy.uix.video import Video
from kivy.clock import Clock
from kivy.core.window import Window

# Use the uploaded file path (or change to 'data/presplash.png' after moving file)
DEFAULT_POSTER = "kivy_projects\my_health_app\splash.jpg"
class SplashScreen(Screen):
    def __init__(self, next_screen='login', video_source='splash.mp4',
                 poster_image=DEFAULT_POSTER, **kwargs):
        super().__init__(**kwargs)
        self.next_screen = next_screen
        self.video_source = video_source
        self.poster_image = poster_image

        self._timeout_ev = None
        self._video_started = False

        # FloatLayout so we can layer poster (bottom) and video on top
        self._layout = FloatLayout()

        # Fullscreen poster image (fills screen)
        if self.poster_image:
            self._poster = Image(
                source=self.poster_image,
                allow_stretch=True,
                keep_ratio=False,   # FULL SCREEN
                size_hint=(1, 1),
                pos_hint={"x": 0, "y": 0},
            )
            self._layout.add_widget(self._poster)
        else:
            self._poster = None

        # Fullscreen video (on top of poster)
        self.video = Video(
            source=self.video_source,
            state='stop',
            options={'eos': 'stop'},
            allow_stretch=True,
            keep_ratio=False,
            size_hint=(1, 1),
            pos_hint={"x": 0, "y": 0},
        )
        # Do not add video immediately if poster is shown; we'll replace it shortly
        # but adding it on top works too — we will control visibility
        self._layout.add_widget(self.video)

        # Bind events
        self.video.bind(on_eos=self._on_video_end)
        Window.bind(on_touch_down=self._on_touch)

        # Add layout to the screen
        self.add_widget(self._layout)

        # Start the video after a tiny delay so Android/ffpyplayer has time to initialize
        Clock.schedule_once(self._delayed_start, 0.05)

    def _delayed_start(self, dt):
        # show video (it is already in layout) and start playback
        try:
            # ensure poster remains visible until video draws; video will cover it
            self.video.state = 'play'
            self._video_started = True
            # safety timeout in case on_eos doesn't fire (set to reasonable max like 10s)
            self._timeout_ev = Clock.schedule_once(self._on_video_timeout, 10.0)
        except Exception as e:
            # fallback to immediate transition
            print("Splash video start failed:", e)
            self.go_next()

    def _on_video_end(self, instance, *args):
        # cancel timeout and transition
        if self._timeout_ev:
            self._timeout_ev.cancel()
            self._timeout_ev = None
        self.go_next()

    def _on_video_timeout(self, dt):
        # stop and proceed if video stuck
        try:
            self.video.state = 'stop'
        except Exception:
            pass
        self.go_next()

    def _on_touch(self, window, touch):
        # skip splash on any touch
        # unbind so multiple touches don't queue multiple transitions
        try:
            Window.unbind(on_touch_down=self._on_touch)
        except Exception:
            pass
        try:
            self.video.state = 'stop'
        except Exception:
            pass
        self.go_next()
        return False  # allow other handlers too

    def go_next(self):
        # cleanup bindings and switch screen
        try:
            Window.unbind(on_touch_down=self._on_touch)
        except Exception:
            pass
        try:
            if self._timeout_ev:
                self._timeout_ev.cancel()
                self._timeout_ev = None
        except Exception:
            pass

        if self.manager:
            try:
                self.manager.current = self.next_screen
            except Exception:
                pass
        else:
            # if no manager yet, try shortly
            Clock.schedule_once(lambda dt: self._delayed_switch(), 0.05)

    def _delayed_switch(self):
        if self.manager:
            self.manager.current = self.next_screen

    # Optionally stop video when the screen is removed
    def on_leave(self, *args):
        try:
            self.video.state = 'stop'
        except Exception:
            pass
        try:
            Window.unbind(on_touch_down=self._on_touch)
        except Exception:
            pass

# ---------------------------
# Background video wrapper
# ---------------------------
class Background(FloatLayout):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        # Keep video inside background; disable if not needed
        self.video = Video(
            source="hhhh.mp4",
            state='play',
            options={'eos': 'loop'},
            allow_stretch=True,
            keep_ratio=False,
            size_hint=(1, 1),
            pos_hint={'x': 0, 'y': 0}
        )
        # Setting disabled True prevents touch but still plays. If video not desired set state='stop'
        # If your video is large or causes issues on mobile, set state='stop' or remove this widget
        self.add_widget(self.video)
        self.bind(size=self._update_video_size, pos=self._update_video_size)

    def _update_video_size(self, *args):
        self.video.size = self.size
        self.video.pos = self.pos


# ---------------------------
# LoginScreen
# ---------------------------
class LoginScreen(Screen):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)

        bg = Background()

        layout = BoxLayout(
            orientation='vertical',
            spacing=dp(15),
            padding=dp(12),
            size_hint=(0.8, 0.8),
            pos_hint={'center_x': 0.5, 'center_y': 0.5},
        )

        layout.add_widget(Label(
            text='[b]Virtual Health Record Login[/b]',
            markup=True,
            font_size=sp(28),
            color=(1, 1, 1, 1),
            size_hint_y=None,
            height=dp(50),
        ))

        self.username = TextInput(
            hint_text='Username',
            multiline=False,
            size_hint=(1, None),
            height=dp(40),
            font_size=sp(18),
        )
        layout.add_widget(self.username)

        self.password = TextInput(
            hint_text='Password',
            password=True,
            multiline=False,
            size_hint=(1, None),
            height=dp(40),
        )
        layout.add_widget(self.password)

        login_btn = Button(
            text='Login',
            size_hint=(0.3, None),
            height=dp(50),
            background_color=(0.1, 0.5, 0.8, 1),
            color=(1, 1, 1, 1),
            font_size=sp(16),
            pos_hint={'center_x': 0.85}
        )
        login_btn.bind(on_press=self.authenticate)
        layout.add_widget(login_btn)

        self.message = Label(
            text='',
            color=(1, 0.3, 0.3, 1),
            font_size=sp(14),
            size_hint_y=None,
            height=dp(30),
        )
        layout.add_widget(self.message)
        layout.add_widget(Widget(size_hint_y=None, height=dp(200)))

        bg.add_widget(layout)
        self.add_widget(bg)

    def authenticate(self, instance):
        users = {
            'K':{'password': '17', 'role': 'nurse'},
            'k':{'password': '18', 'role': 'doctor'}
        }
        uname = self.username.text.strip()
        pwd = self.password.text.strip()
        user = users.get(uname)

        if user and user['password'] == pwd:
            # persist login
            try:
                store = get_store()
                store.put('user', username=uname, role=user['role'])
            except Exception as e:
                print("Warning: could not save login:", e)

            self.message.text = ''
            self.manager.get_screen('main').load_user(uname, user['role'])
            self.manager.current = 'main'
        else:
            self.message.text = 'Invalid username or password!'


    def on_touch_down(self, touch):
        Logger.debug(f"LoginScreen touched at {touch.pos}")
        return super().on_touch_down(touch)
# ---------------------------
# MainScreen
# ---------------------------
class MainScreen(Screen):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.username = ""
        self.role = ""

        layout = BoxLayout(
            orientation='vertical',
            spacing=dp(20),
            padding=[dp(20), dp(40)],
            size_hint=(1, None),
            pos_hint={'center_x': 0.5, 'center_y': 0.5},
        )
        layout.bind(minimum_height=layout.setter('height'))

        # USER LABEL
        self.user_label = Label(
            text='',
            font_size=sp(20),
            markup=True,
            halign="center",
            valign="middle",
            size_hint=(1, None),
            height=dp(40),
            color=(1, 1, 1, 1),
        )
        layout.add_widget(self.user_label)

        def create_button(text, bg_color, screen_name):
            btn = Button(
                text=text,
                size_hint=(1, None),
                height=dp(55),
                background_color=bg_color,
                color=(1, 1, 1, 1),
                font_size=sp(16),
            )
            btn.bind(on_press=lambda x: setattr(self.manager, 'current', screen_name))
            return btn

        layout.add_widget(create_button('View Health Record', (0.2, 0.6, 0.3, 1), 'record'))
        layout.add_widget(create_button('Emergency Access Override', (0.8, 0.2, 0.2, 1), 'emergency'))
        layout.add_widget(create_button('Settings', (0.3, 0.3, 0.5, 1), 'settings'))

        helpline_btn = Button(
            text='Helpline No',
            size_hint=(1, None),
            height=dp(55),
            background_color=(0.1, 0.4, 0.6, 1),
            color=(1, 1, 1, 1),
            font_size=sp(16)
        )
        helpline_btn.bind(on_press=self.show_helpline_info)
        layout.add_widget(helpline_btn)

        layout.add_widget(Widget(size_hint_y=None, height=dp(50)))

        bg = Background()
        bg.add_widget(layout)
        self.add_widget(bg)

    def load_user(self, username, role):
        self.username = username
        self.role = role
        self.user_label.text = f"[b]Logged in as: {username} ({role})[/b]"
        # propagate to screens if present
        for name in ('record', 'emergency', 'settings'):
            if self.manager and self.manager.has_screen(name):
                screen = self.manager.get_screen(name)
                if hasattr(screen, 'set_user'):
                    screen.set_user(username)

    def open_settings(self, instance):
        self.manager.current = 'settings'

    def show_helpline_info(self, instance):
        content = GridLayout(cols=1, spacing=dp(15), size_hint_y=None)
        content.bind(minimum_height=content.setter('height'))

        helplines = [
            ("",""),
            ("Mumbai", "Breach Candy Hospital - 022-23667979"),
            ("Delhi", "AIIMS - 011-26588500"),
            ("Bangalore", "Manipal Hospital - 080-22221111"),
            ("Kolkata", "Fortis Hospital - 033-66276600"),
            ("Chennai", "Apollo Hospital - 044-28293333"),
            ("Pune", "Ruby Hall Clinic - 020-26163391"),
        ]

        for place, info in helplines:
            label = Label(
                text=f"[b]{place}:[/b] {info}",
                markup=True,
                font_size=sp(14),
                size_hint_y=None,
                height=dp(30),
                halign='left',
                valign='middle',
                color=(1, 1, 1, 1),
            )
            label.bind(size=lambda inst, val: setattr(inst, 'text_size', (val[0], None)))
            content.add_widget(label)

        scroll = ScrollView(size_hint=(1, None), height=dp(220))
        scroll.add_widget(content)

        popup_layout = BoxLayout(orientation='vertical', padding=dp(8), spacing=dp(8))
        popup_layout.add_widget(scroll)

        close_btn = Button(text='Close', size_hint_y=None, height=dp(44))
        popup_layout.add_widget(close_btn)

        popup = Popup(
            title='Hospital Helpline Numbers',
            content=popup_layout,
            size_hint=(None, None),
            size=(dp(340), dp(320)),
            auto_dismiss=False,
        )
        close_btn.bind(on_press=popup.dismiss)
        popup.open()


# ---------------------------
# PatientListScreen (single correct version)
# ---------------------------
class PatientListScreen(Screen):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        layout = BoxLayout(orientation='vertical', padding=dp(15), spacing=dp(10))
        top_buttons = BoxLayout(orientation='horizontal', size_hint_y=None, height=dp(50))
        back_btn = Button(
            text='Back',
            size_hint=(None, 1),
            width=dp(100),
            background_color=(0.3, 0.3, 0.6, 1),
            color=(1, 1, 1, 1)
        )
        back_btn.bind(on_press=lambda x: setattr(self.manager, 'current', 'main'))
        top_buttons.add_widget(back_btn)
        top_buttons.add_widget(Label(size_hint_x=1))
        add_btn = Button(
            text='Add Patient',
            size_hint=(None, 1),
            width=dp(150),
            background_color=(0.2, 0.6, 0.8, 1),
            color=(1, 1, 1, 1)
        )
        add_btn.bind(on_press=self.open_add_patient_form)
        top_buttons.add_widget(add_btn)

        layout.add_widget(top_buttons)

        # --- Patient List Area ---
        self.patient_list_layout = GridLayout(cols=1, spacing=10, size_hint_y=None)
        self.patient_list_layout.bind(minimum_height=self.patient_list_layout.setter('height'))

        scroll_view = ScrollView()
        scroll_view.add_widget(self.patient_list_layout)
        layout.add_widget(scroll_view)

        bg = Background()
        bg.add_widget(layout)
        self.add_widget(bg)

    def on_enter(self):
        self.load_patients()

    def set_user(self, username):
        self.username = username
        self.load_patients()

    def load_patients(self):
        self.patient_list_layout.clear_widgets()
        db_path = get_db_path()
        try:
            with db_lock:
                conn = sqlite3.connect(db_path, timeout=10, check_same_thread=False)
                cursor = conn.cursor()
                try:
                    cursor.execute('SELECT id, name FROM patients ORDER BY name')
                    patients = cursor.fetchall()
                finally:
                    cursor.close()
                    conn.close()
        except Exception as e:
            Logger.error(f"PatientList: DB error: {e}")
            return

        if not patients:
            container = FloatLayout(size_hint_y=None, height=dp(200))
            no_patient_label = Label(
                text="No patients found. Click 'Add Patient' to begin.",
                color=(1, 1, 1, 1),
                size_hint=(None, None),
                size=(dp(400), dp(30)),
                pos_hint={'center_x': 0.5, 'center_y': 0.5},
            )
            container.add_widget(no_patient_label)
            self.patient_list_layout.add_widget(container)
            return

        for pid, pname in patients:
            btn = Button(
                text=pname,
                size_hint_y=None,
                height=dp(60),
                background_color=(0.2, 0.4, 0.6, 1),
                color=(1, 1, 1, 1),
            )
            # bind with default arg to capture pid
            btn.bind(on_press=lambda inst, _pid=pid: self.go_to_details(_pid))
            self.patient_list_layout.add_widget(btn)

    def go_to_details(self, patient_id):
        if self.manager and self.manager.has_screen('patient_details'):
            details_screen = self.manager.get_screen('patient_details')
            if hasattr(details_screen, 'load_patient_data'):
                details_screen.load_patient_data(patient_id)
            self.manager.transition.direction = 'left'
            self.manager.current = 'patient_details'

    def open_add_patient_form(self, instance):
        popup = AddPatientPopup(parent_screen=self)
        popup.open()


# ---------------------------
# PatientDetailsScreen
# ---------------------------
class PatientDetailsScreen(Screen):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.patient_id = None

        main_layout = BoxLayout(
            orientation='vertical',
            padding=dp(15),
            spacing=dp(15),
        )

        top_bar = BoxLayout(size_hint_y=None, height=dp(50))
        back_to_list_btn = Button(
            text='< Back to List',
            size_hint_x=None, width=dp(120),
            background_color=(0.3, 0.3, 0.6, 1)
        )
        back_to_list_btn.bind(on_press=self.go_back)
        top_bar.add_widget(back_to_list_btn)
        top_bar.add_widget(Label())
        main_layout.add_widget(top_bar)

        self.details_label = Label(
            text='Select a patient to view details',
            size_hint_y=None, height=dp(50),
            color=(1, 1, 1, 1),
            font_size=sp(24),
            halign='left', valign='middle'
        )
        self.details_label.bind(size=self.details_label.setter('text_size'))
        main_layout.add_widget(self.details_label)

        self.details_grid = GridLayout(cols=1, spacing=10, size_hint_y=None)
        self.details_grid.bind(minimum_height=self.details_grid.setter('height'))

        self.details_scroll = ScrollView()
        self.details_scroll.add_widget(self.details_grid)
        main_layout.add_widget(self.details_scroll)

        self.delete_btn = Button(
            text='Delete Patient',
            size_hint_y=None, height=dp(50),
            background_color=(0.8, 0.2, 0.2, 1),
            disabled=True
        )
        self.delete_btn.bind(on_press=self.delete_patient)
        main_layout.add_widget(self.delete_btn)

        bg = Background()
        bg.add_widget(main_layout)
        self.add_widget(bg)

    def clear_details(self):
        self.details_label.text = 'Select a patient to view details'
        self.details_label.font_size = sp(18)
        self.details_grid.clear_widgets()
        self.delete_btn.disabled = True
        self.patient_id = None

    def load_patient_data(self, patient_id):
        self.patient_id = patient_id
        self.details_grid.clear_widgets()

        db_path = get_db_path()
        try:
            with db_lock:
                conn = sqlite3.connect(db_path, timeout=10, check_same_thread=False)
                cursor = conn.cursor()
                try:
                    cursor.execute('SELECT * FROM patients WHERE id = ?', (patient_id,))
                    patient = cursor.fetchone()
                finally:
                    cursor.close()
                    conn.close()
        except Exception as e:
            Logger.error(f"PatientDetails: DB error {e}")
            self.details_label.text = "Error loading patient."
            return

        if not patient:
            self.details_label.text = "Patient details not found."
            self.delete_btn.disabled = True
            return

        self.details_label.text = f"Details for: {patient[1]}"
        self.delete_btn.disabled = False

        details = [
            ("ID", patient[0]),
            ("Name", patient[1]),
            ("Age", patient[2]),
            ("Gender", patient[3]),
            ("Contact", patient[4]),
            ("Address", patient[5]),
            ("Conditions", patient[6]),
            ("Medications", patient[7]),
            ("Doctor Name", patient[8]),
            ("Last Visit", patient[9]),
            ("Notes", patient[10]),
        ]

        table = GridLayout(
            cols=3,
            spacing=[dp(5), dp(10)],
            size_hint_y=None,
            row_force_default=True,
            row_default_height=dp(40),
        )

        table.bind(minimum_height=table.setter('height'))

        for field, value in details:
            field_label = Label(
                text=field,
                size_hint_x=None,
                width=dp(150),
                font_size=sp(16),
                halign='right',
                valign='middle',
                color=(0.9, 0.9, 0.9, 1),
            )
            field_label.bind(size=field_label.setter('text_size'))

            colon_label = Label(
                text=":",
                size_hint_x=None,
                width=dp(20),
                font_size=sp(16),
                halign='center',
                valign='middle',
                color=(1, 1, 1, 1),
            )
            colon_label.bind(size=colon_label.setter('text_size'))

            value_label = Label(
                text=str(value or "N/A"),
                size_hint_x=1,
                font_size=sp(16),
                halign='left',
                valign='middle',
                color=(1, 1, 1, 1),
            )
            # ensure wrapping
            value_label.bind(size=lambda i, s: setattr(i, 'text_size', (s[0], None)))

            table.add_widget(field_label)
            table.add_widget(colon_label)
            table.add_widget(value_label)

        self.details_grid.add_widget(table)
        self.details_grid.add_widget(Label(size_hint_y=None, height=dp(20)))
        action_buttons_container = BoxLayout(
            orientation='horizontal',
            size_hint_y=None,
            height=dp(50),
            spacing=dp(10)
        )

        qr_data = f"ID: {patient[0]}, Name: {patient[1]}, Contact: {patient[4]}"
        filename = generate_qr_code(qr_data, f"{patient[1].replace(' ', '_')}_qr.png")

        def show_qr_popup(fn):
            popup = Popup(
                title="Patient QR Code",
                content=Image(source=fn, allow_stretch=True, keep_ratio=True),
                size_hint=(None, None),
                size=(dp(350), dp(350)),
            )
            popup.open()

        qr_button = Button(
            text="Generate QR Code",
            size_hint_y=1,
            background_color=(0.6, 0.4, 0.2, 1),
            color=(1, 1, 1, 1),
        )
        qr_button.bind(on_press=lambda x: show_qr_popup(filename))
        action_buttons_container.add_widget(qr_button)

        sms_button = Button(
            text="Send SMS Alert",
            size_hint_y=1,
            background_color=(0.2, 0.7, 0.2, 1),
            color=(1, 1, 1, 1),
        )
        sms_button.bind(on_press=lambda x: send_sms(patient[4], f"Dear {patient[1]}, your health record is saved."))
        action_buttons_container.add_widget(sms_button)

        self.details_grid.add_widget(action_buttons_container)

    def delete_patient(self, instance):
        if not self.patient_id:
            return
        db_path = get_db_path()
        try:
            with db_lock:
                conn = sqlite3.connect(db_path, timeout=10, check_same_thread=False)
                cursor = conn.cursor()
                try:
                    cursor.execute('DELETE FROM patients WHERE id = ?', (self.patient_id,))
                    conn.commit()
                finally:
                    cursor.close()
                    conn.close()
        except Exception as e:
            Logger.error(f"PatientDetails: delete error {e}")

        self.patient_id = None
        self.go_back(None)

    def go_back(self, instance):
        self.manager.transition.direction = 'right'
        self.manager.current = 'record'


# ---------------------------
# AddPatientPopup
# ---------------------------
class AddPatientPopup(Popup):
    def __init__(self, parent_screen=None, **kwargs):
        super().__init__(**kwargs)
        self.parent_screen = parent_screen
        self.title = "Add New Patient"
        self.size_hint = (None, None)
        self.size = (dp(360), dp(560))
        self.auto_dismiss = False
        self.pos_hint = {'center_x': 0.5, 'center_y': 0.5}

        form_grid = GridLayout(cols=2, spacing=dp(8), padding=dp(10), size_hint_y=None)
        form_grid.bind(minimum_height=form_grid.setter('height'))
        self.fields = {}

        labels = [
            "Name", "Age", "Gender", "Contact", "Address",
            "Conditions", "Medications", "Doctor Name", "Last Visit (YYYY-MM-DD)", "Notes"
        ]

        for label_text in labels:
            lbl = Label(text=label_text, color=(1, 1, 1, 1), size_hint_y=None, height=dp(30))
            form_grid.add_widget(lbl)

            if label_text == "Notes":
                ti = TextInput(multiline=True, size_hint_y=None, height=dp(100))
            else:
                ti = TextInput(multiline=False, size_hint_y=None, height=dp(40))
            form_grid.add_widget(ti)
            self.fields[label_text] = ti

        scroll = ScrollView(size_hint=(1, 1))
        scroll.add_widget(form_grid)

        btn_layout = BoxLayout(size_hint_y=None, height=dp(52), spacing=dp(10), padding=[dp(8)]*4)
        add_btn = Button(
            text='Add',
            background_color=(0.2, 0.7, 0.2, 1),
            color=(1, 1, 1, 1),
            font_size=sp(16),
            size_hint_x=0.5,
            size_hint_y=None,
            height=dp(44)
        )
        add_btn.bind(on_press=self.add_patient)

        cancel_btn = Button(
            text='Cancel',
            background_color=(0.7, 0.2, 0.2, 1),
            color=(1, 1, 1, 1),
            font_size=sp(16),
            size_hint_x=0.5,
            size_hint_y=None,
            height=dp(44)
        )
        cancel_btn.bind(on_press=lambda *a: self.dismiss())

        btn_layout.add_widget(add_btn)
        btn_layout.add_widget(cancel_btn)

        main_layout = BoxLayout(orientation='vertical')
        main_layout.add_widget(scroll)
        main_layout.add_widget(btn_layout)
        main_layout.add_widget(Widget(size_hint_y=None, height=dp(6)))

        try:
            bg = Background()
            bg.add_widget(main_layout)
            self.content = bg
        except Exception:
            self.content = main_layout

    def show_error(self, message, title="Error"):
        try:
            popup = Popup(
                title=title,
                content=Label(text=message),
                size_hint=(None, None),
                size=(dp(300), dp(160))
            )
            popup.open()
        except Exception:
            self._write_error_log(f"{title}: {message}")

    def _write_error_log(self, msg):
        try:
            app = App.get_running_app()
            base = app.user_data_dir if app else os.getcwd()
        except Exception:
            base = os.getcwd()
        try:
            os.makedirs(base, exist_ok=True)
            path = os.path.join(base, "error_log.txt")
            with open(path, "a", encoding="utf-8") as f:
                f.write(msg + "\n\n")
        except Exception:
            pass

    def add_patient(self, instance):
        try:
            expected_keys = [
                "Name", "Age", "Gender", "Contact", "Address",
                "Conditions", "Medications", "Doctor Name",
                "Last Visit (YYYY-MM-DD)", "Notes"
            ]
            data = {}
            for key in expected_keys:
                widget = self.fields.get(key)
                val = ""
                try:
                    val = widget.text.strip() if widget is not None and hasattr(widget, 'text') else ""
                except Exception:
                    val = ""
                data[key] = val

            # Basic validation
            if not data["Name"]:
                self.show_error("Name is required.\nEnter your good name please.", title="Validation")
                return
            if not data['Age']:
                self.show_error("Age is required.", title="Validation")
                return
            if not data['Contact']:
                self.show_error("Contact is important, fill it.", title="Validation")
                return
            if not data['Last Visit (YYYY-MM-DD)']:
                self.show_error("Last visit is required.", title="Validation")
                return

            # Validate date format
            try:
                datetime.strptime(data["Last Visit (YYYY-MM-DD)"], '%Y-%m-%d')
            except Exception:
                self.show_error("Last Visit date must be YYYY-MM-DD", title="Validation")
                return

            # Get DB path
            try:
                db_path = get_db_path()
            except Exception:
                app = App.get_running_app()
                base = app.user_data_dir if app else os.getcwd()
                db_path = os.path.join(base, "health_records.db")

            # Ensure parent dir exists
            db_dir = os.path.dirname(db_path)
            if db_dir and not os.path.exists(db_dir):
                os.makedirs(db_dir, exist_ok=True)

            # --- ensure table exists before inserting ---
            def ensure_table_exists(path):
                try:
                    with sqlite3.connect(path) as c:
                        cur = c.cursor()
                        cur.execute("""
                            CREATE TABLE IF NOT EXISTS patients (
                                id INTEGER PRIMARY KEY AUTOINCREMENT,
                                name TEXT,
                                age INTEGER,
                                gender TEXT,
                                contact TEXT,
                                address TEXT,
                                conditions TEXT,
                                medications TEXT,
                                doctor_name TEXT,
                                last_visit TEXT,
                                notes TEXT
                            )
                        """)
                        c.commit()
                except Exception:
                    # Log but don't crash here
                    try:
                        tb = traceback.format_exc()
                        app = App.get_running_app()
                        base = app.user_data_dir if app else os.path.expanduser("~/.my_health_app")
                        os.makedirs(base, exist_ok=True)
                        with open(os.path.join(base, "error_log.txt"), "a", encoding="utf-8") as lf:
                            lf.write("\n\n--- ensure_table_exists() EXCEPTION at " + datetime.now().isoformat() + " ---\n")
                            lf.write(tb)
                    except Exception:
                        pass

            ensure_table_exists(db_path)

            # Insert into DB with lock
            lock = globals().get('db_lock')
            if lock is None:
                import threading
                lock = threading.Lock()

            with lock:
                conn = None
                cursor = None
                try:
                    conn = sqlite3.connect(db_path, timeout=10, check_same_thread=False)
                    cursor = conn.cursor()
                    cursor.execute('''
                        INSERT INTO patients (
                            name, age, gender, contact, address,
                            conditions, medications, doctor_name, last_visit, notes
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ''', (
                        data["Name"], data["Age"], data["Gender"], data["Contact"], data["Address"],
                        data["Conditions"], data["Medications"], data["Doctor Name"],
                        data["Last Visit (YYYY-MM-DD)"], data["Notes"]
                    ))
                    conn.commit()
                except Exception as db_e:
                    # full traceback
                    tb = traceback.format_exc()
                    # write verbose log
                    try:
                        app = App.get_running_app()
                        base = app.user_data_dir if app else os.path.expanduser("~/.my_health_app")
                        os.makedirs(base, exist_ok=True)
                        logpath = os.path.join(base, "error_log.txt")
                        with open(logpath, "a", encoding="utf-8") as lf:
                            lf.write("\n\n--- DB EXCEPTION at " + datetime.now().isoformat() + " ---\n")
                            lf.write(tb)
                    except Exception:
                        pass

                    # show popup with the exception message (dev only)
                    self.show_error(f"Database error occurred:\n{str(db_e)}\n\nSee error_log.txt for full traceback.", title="DB Error")
                    return
                finally:
                    try:
                        if cursor:
                            cursor.close()
                    except Exception:
                        pass
                    try:
                        if conn:
                            conn.close()
                    except Exception:
                        pass

            # Refresh parent screen list if available
            try:
                if hasattr(self, "parent_screen") and self.parent_screen and hasattr(self.parent_screen, 'load_patients'):
                    self.parent_screen.load_patients()
            except Exception:
                self._write_error_log("REFRESH ERROR:\n" + traceback.format_exc())

            # Success + dismiss
            self.show_error("Patient added successfully.", title="Success")
            try:
                self.dismiss()
            except Exception:
                pass

        except Exception:
            tb = traceback.format_exc()
            self._write_error_log("UNEXPECTED ERROR:\n" + tb)
            self.show_error("An unexpected error occurred. See error_log.txt in app data.", title="Crash")



# ---------------------------
# EmergencyAccessScreen
# ---------------------------
class EmergencyAccessScreen(Screen):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        bg = Background()
        layout = FloatLayout()

        back_btn = Button(
            text='Back',
            size_hint=(None, None),
            size=(dp(100), dp(40)),
            pos_hint={'x': 0, 'top': 1},
            background_color=(0.3, 0.3, 0.6, 1),
            color=(1, 1, 1, 1),
        )
        back_btn.bind(on_press=lambda x: setattr(self.manager, 'current', 'main'))
        layout.add_widget(back_btn)

        label = Label(
            text="Emergency Alert Activated",
            font_size=sp(20),
            color=(1, 1, 1, 1),
            size_hint=(None, None),
            size=(dp(300), dp(50)),
            pos_hint={'center_x': 0.5, 'center_y': 0.6}
        )
        layout.add_widget(label)

        notify_btn = Button(
            text="Notify Emergency Contact",
            size_hint=(None, None),
            size=(dp(220), dp(50)),
            pos_hint={'center_x': 0.5, 'center_y': 0.45},
            background_color=(0.8, 0.1, 0.1, 1),
            color=(1, 1, 1, 1),
        )
        notify_btn.bind(on_press=self.send_emergency_sms)
        layout.add_widget(notify_btn)

        bg.add_widget(layout)
        self.add_widget(bg)

    def set_user(self, username):
        self.username = username

    def send_emergency_sms(self, instance):
        message = f"Emergency access triggered by {getattr(self, 'username', 'unknown')}."
        send_sms("+919876543210", message)


# ---------------------------
# SettingsScreen
# ---------------------------
class SettingsScreen(Screen):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        bg = Background()  # assumes Background exists in your project and provides the same smoky background

        # Use an AnchorLayout so content stays centered horizontally like the main screen
        outer = AnchorLayout()

        # Scroll container so the panel scrolls on small devices
        scroll = ScrollView(size_hint=(0.95, 0.9))

        # Inner vertical column to hold header + buttons
        container = BoxLayout(
            orientation='vertical',
            spacing=dp(20),
            padding=[dp(20), dp(40), dp(20), dp(40)],
            size_hint=(1, None),
        )
        container.bind(minimum_height=container.setter('height'))

        # Optional top decorative image to match main screen vibe (centered)
        image_path = '/mnt/data/9141bf70-5ba3-44bd-8be8-ea96edaac72d.png'
        if os.path.exists(image_path):
            img_anchor = AnchorLayout(size_hint=(1, None), height=dp(140))
            img = Image(source=image_path, size_hint=(None, None), size=(dp(420), dp(120)), allow_stretch=True, keep_ratio=True)
            img_anchor.add_widget(img)
            container.add_widget(img_anchor)
        else:
            # small spacer if image missing
            container.add_widget(Widget(size_hint_y=None, height=dp(6)))

        # Header - same visual weight as main screen
        header = Label(
            text='[b]Settings[/b]',
            markup=True,
            font_size=sp(24),
            size_hint=(1, None),
            height=dp(60),
            halign='center',
            valign='middle',
            color=(1, 1, 1, 1),
        )
        header.bind(size=lambda inst, val: setattr(inst, 'text_size', (val[0], None)))
        container.add_widget(header)

        # Helper to create main-like buttons (full width, same heights)
        def main_style_btn(text, bg_color, handler=None):
            b = Button(
                text=text,
                size_hint=(1, None),
                height=dp(60),
                background_color=bg_color,
                color=(1, 1, 1, 1),
                font_size=sp(18),
            )
            if handler:
                b.bind(on_press=handler)
            return b

        btn_app_version = main_style_btn('App Version', (0.07, 0.35, 0.45, 1), self.show_app_version)
        btn_about_app = main_style_btn('About This App', (0.07, 0.25, 0.35, 1), self.show_about_app)
        btn_logout = main_style_btn('Logout', (0.6, 0.12, 0.12, 1), self.logout)
        btn_back = main_style_btn('Back to Menu', (0.18, 0.18, 0.33, 1), self.back_to_menu)

        # Add small elevation effect using spacing widgets above and below each button
        for w in (btn_app_version, btn_about_app, btn_logout, btn_back):
            # a surrounding BoxLayout to give visual breathing room (like the main screen)
            wrapper = BoxLayout(size_hint=(1, None), height=w.height)
            wrapper.add_widget(w)
            container.add_widget(wrapper)

        # flexible spacer
        container.add_widget(Widget(size_hint_y=None, height=dp(30)))

        scroll.add_widget(container)
        outer.add_widget(scroll)
        bg.add_widget(outer)
        self.add_widget(bg)
    def logout(self, instance):
        try:
            store = get_store()
            if store.exists('user'):
                store.delete('user')
        except Exception:
            pass
        self.manager.current = 'login'

    def show_app_version(self, instance):
        content = BoxLayout(orientation='vertical', padding=10, spacing=10)
        content.add_widget(Label(text='App Version: 1.0.0', font_size=18, color=(1, 1, 1, 1)))
        close_btn = Button(text='Close', size_hint_y=None, height=40)
        content.add_widget(close_btn)

        popup = Popup(
            title='App Version',
            content=content,
            size_hint=(None, None),
            size=(dp(500), dp(400)),
            auto_dismiss=False,
        )
        close_btn.bind(on_press=popup.dismiss)
        popup.open()

    def show_about_app(self, instance):
        content = BoxLayout(orientation='vertical', padding=10, spacing=10)
        about_text = (
            "Virtual Health Record App"
            "This app allows doctors to securely access and manage patient health records."
            "Version 1.0.0"
        )
        content.add_widget(Label(text=about_text, font_size=16, color=(1, 1, 1, 1)))
        close_btn = Button(text='Close', size_hint_y=None, height=40)
        content.add_widget(close_btn)

        popup = Popup(
            title='About This App',
            content=content,
            size_hint=(None, None),
            size=(dp(500), dp(400)),
            auto_dismiss=False,
        )
        close_btn.bind(on_press=popup.dismiss)
        popup.open()

    def logout(self, instance):
        # perform any logout cleanup here
        self.manager.current = 'login'

    def back_to_menu(self, instance):
        self.manager.current = 'main'

    def set_user(self, username):
        self.username = username

# ---------------------------
# Android UI hide helper (optional)
# ---------------------------
if platform == 'android':
    try:
        from android.runnable import run_on_ui_thread
        from jnius import autoclass

        @run_on_ui_thread
        def hide_android_ui():
            View = autoclass('android.view.View')
            PythonActivity = autoclass('org.kivy.android.PythonActivity')
            window = PythonActivity.mActivity.getWindow()
            decorView = window.getDecorView()
            decorView.setSystemUiVisibility(
                View.SYSTEM_UI_FLAG_FULLSCREEN
                | View.SYSTEM_UI_FLAG_HIDE_NAVIGATION
                | View.SYSTEM_UI_FLAG_IMMERSIVE_STICKY
            )
    except Exception:
        hide_android_ui = lambda *a, **k: None


# ---------------------------
# App main class
# ---------------------------

class Health(App):
    def build(self):
        # Create screens
        sm = ScreenManager()
        sm.add_widget(LoginScreen(name='login'))
        sm.add_widget(MainScreen(name='main'))
        sm.add_widget(PatientListScreen(name='record'))
        sm.add_widget(PatientDetailsScreen(name='patient_details'))
        sm.add_widget(EmergencyAccessScreen(name='emergency'))
        sm.add_widget(SettingsScreen(name='settings'))

        # ---- Decide splash target synchronously (NO Clock delay) ----
        # Determine if a saved session exists right now so we can set the splash target.
        try:
            # Use App.user_data_dir (available on build()) or fallback to home
            base = self.user_data_dir if hasattr(self, 'user_data_dir') and self.user_data_dir \
                   else os.path.expanduser("~/.my_health_app")
            os.makedirs(base, exist_ok=True)
            store_path = os.path.join(base, "user_store.json")
            store = JsonStore(store_path)
            if store.exists('user'):
                splash_target = 'main'
            else:
                splash_target = 'login'
        except Exception:
            splash_target = 'login'

        # Add the SplashScreen first and give it the correct next_screen target
        sm.add_widget(
            SplashScreen(
                name='splash',
                next_screen=splash_target,
                video_source='splash.mp4',
                poster_image="kivy_projects\my_health_app\splash.jpg"   # ensure this file is included in your apk
            )
        )

        # Make sure splash is the first visible screen
        sm.current = 'splash'

        # Ensure DB/tables exist now that App exists and user_data_dir is available
        try:
            create_db()
        except Exception as e:
            # Write a helpful error_log inside the app data dir (if possible)
            try:
                base = self.user_data_dir if hasattr(self, 'user_data_dir') and self.user_data_dir else os.path.expanduser("~/.my_health_app")
                os.makedirs(base, exist_ok=True)
                with open(os.path.join(base, "error_log.txt"), "a", encoding="utf-8") as f:
                    f.write("create_db() error in build():\n")
                    f.write(traceback.format_exc())
            except Exception:
                pass

        # Hide system UI on Android if requested
        if platform == 'android':
            Clock.schedule_once(lambda dt: hide_android_ui(), 0.5)

        return sm

    # keep on_pause / on_resume as you already have
    def on_pause(self):
        return True

    def on_resume(self):
        try:
            sm = self.root
            store = get_store()
            if store.exists('user') and sm:
                u = store.get('user')
                if hasattr(sm.get_screen('main'), 'load_user'):
                    sm.get_screen('main').load_user(u['username'], u['role'])
        except Exception:
            pass

    # you can keep _restore_session if you like, but DO NOT schedule it in build()
    def _restore_session(self, sm):
        try:
            store = get_store()
            if store.exists('user'):
                u = store.get('user')
                username = u.get('username')
                role = u.get('role')
                if hasattr(sm.get_screen('main'), 'load_user'):
                    sm.get_screen('main').load_user(username, role)
                    sm.current = 'main'
        except Exception as e:
            print("Session restore failed:", e)

if __name__ == '__main__': 
    Health().run()