import os
import time
import sqlite3
import psutil
from datetime import datetime, timedelta
import tkinter as tk
from tkinter import ttk
from tkcalendar import DateEntry
from ctypes import Structure, windll, c_uint, sizeof, byref
import matplotlib.pyplot as plt
import threading

# إعداد قاعدة البيانات
DB_PATH = "device_activity.db"

def setup_database():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS activity_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            device_name TEXT,
            event_type TEXT,
            timestamp DATETIME
        )
    """)
    conn.commit()
    conn.close()

def log_event(device_name, event_type):
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO activity_log (device_name, event_type, timestamp)
        VALUES (?, ?, ?)
    """, (device_name, event_type, timestamp))
    conn.commit()
    conn.close()

class LASTINPUTINFO(Structure):
    _fields_ = [("cbSize", c_uint), ("dwTime", c_uint)]

def get_idle_time():
    lii = LASTINPUTINFO()
    lii.cbSize = sizeof(LASTINPUTINFO)
    windll.user32.GetLastInputInfo(byref(lii))
    millis = windll.kernel32.GetTickCount() - lii.dwTime
    return millis / 1000.0

TARGET_PROGRAMS = ["Oracle", "WINWORD", "POWERPNT", "Photoshop", "vlc", "chrome"]
tracked_programs = set()

def track_applications():
    global tracked_programs
    current_programs = set()
    for p in psutil.process_iter(['name', 'cpu_percent', 'memory_info']):
        try:
            if any(target in p.info['name'] for target in TARGET_PROGRAMS):
                cpu_usage = p.info['cpu_percent']
                if cpu_usage > 0:  # تجاهل البرامج التي تستخدم 0% CPU
                    current_programs.add(p.info['name'])
                    if p.info['name'] not in tracked_programs:
                        memory_usage = p.info['memory_info'].rss // (1024 * 1024)  # تحويل الذاكرة إلى ميجابايت
                        log_event(
                            os.environ.get('COMPUTERNAME', 'جهاز غير معروف'),
                            f"تم تشغيل {p.info['name']} (CPU: {cpu_usage}%, RAM: {memory_usage} MB)"
                        )
        except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
            continue
    tracked_programs = current_programs

def monitor_activity():
    device_name = os.environ.get('COMPUTERNAME', 'جهاز غير معروف')
    log_event(device_name, "تم تشغيل الجهاز")
    idle_detected = False
    last_active_time = datetime.now()

    while True:
        idle_time = get_idle_time()
        current_time = datetime.now()
        if idle_time > 300 and not idle_detected:
            duration = (current_time - last_active_time).seconds // 60
            log_event(device_name, f"الجهاز في وضع السكون (من: {last_active_time.strftime('%H:%M')}, إلى: {current_time.strftime('%H:%M')}, المدة: {duration} دقيقة)")
            idle_detected = True
        elif idle_time <= 300 and idle_detected:
            log_event(device_name, "تم استئناف النشاط")
            idle_detected = False
            last_active_time = current_time
        track_applications()
        time.sleep(60)

def generate_report(device_name=None, start_time=None, end_time=None):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    query = "SELECT * FROM activity_log WHERE 1=1"
    params = []
    if device_name:
        query += " AND device_name = ?"
        params.append(device_name)
    if start_time and end_time:
        query += " AND timestamp BETWEEN ? AND ?"
        params.extend([start_time, end_time])
    query += " ORDER BY timestamp ASC"
    cursor.execute(query, params)
    rows = cursor.fetchall()
    conn.close()
    return rows

def get_device_names():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT DISTINCT device_name FROM activity_log")
    rows = cursor.fetchall()
    conn.close()
    return [row[0] for row in rows]

def update_device_list():
    device_names = get_device_names()
    device_dropdown["values"] = device_names

def show_activity_report():
    start_date = start_date_entry.get_date().strftime("%Y-%m-%d")
    end_date = end_date_entry.get_date().strftime("%Y-%m-%d")
    start_hour = start_hour_entry.get()
    start_minute = start_minute_entry.get()
    end_hour = end_hour_entry.get()
    end_minute = end_minute_entry.get()
    start_time = f"{start_date} {start_hour}:{start_minute}:00"
    end_time = f"{end_date} {end_hour}:{end_minute}:59"
    selected_device = device_dropdown.get()
    clear_table(activity_table)
    records = generate_report(device_name=selected_device, start_time=start_time, end_time=end_time)
    for index, row in enumerate(records):
        event_text = row[2]
        cpu_usage = ""
        memory_usage = ""
        if "CPU:" in event_text and "RAM:" in event_text:
            try:
                cpu_usage = event_text.split("CPU:")[1].split("%")[0].strip() + "%"
                memory_usage = event_text.split("RAM:")[1].split("MB")[0].strip() + " MB"
            except IndexError:
                pass
        tag = 'evenrow'
        if "تم تشغيل الجهاز" in event_text:
            tag = 'startrow'
        elif "وضع السكون" in event_text:
            tag = 'idlerow'
        elif "تم تشغيل" in event_text:
            tag = 'programrow'
        elif "تم استئناف النشاط" in event_text:
            tag = 'resumerow'
        activity_table.insert("", "end", values=(*row, cpu_usage, memory_usage), tags=(tag,))

def clear_table(table):
    for item in table.get_children():
        table.delete(item)

def show_summary():
    selected_device = device_dropdown.get()
    records = generate_report(device_name=selected_device)
    total_events = len(records)
    idle_events = [r for r in records if "وضع السكون" in r[2]]
    idle_count = len(idle_events)
    total_idle_time = sum(
        int(r[2].split("المدة: ")[1].split()[0]) for r in idle_events if "المدة" in r[2]
    )
    programs_started = [r[2].split(" ")[-1] for r in records if "تم تشغيل" in r[2]]
    programs_usage = {program: programs_started.count(program) for program in set(programs_started)}

    summary_label.config(
        text=f"إجمالي الأحداث: {total_events}, أحداث السكون: {idle_count}, إجمالي وقت السكون: {total_idle_time} دقيقة\n"
             f"البرامج الأكثر استخدامًا: {', '.join(f'{k} ({v} مرة)' for k, v in programs_usage.items())}"
    )

def refresh_activity_log():
    update_device_list()
    show_activity_report()

def clear_database():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("DELETE FROM activity_log")
    conn.commit()
    conn.close()
    update_device_list()
    clear_table(activity_table)
    summary_label.config(text="تم مسح قاعدة البيانات")

app = tk.Tk()
app.title("الصندوق الأسود")
app.geometry("1400x800")

tab_control = ttk.Notebook(app)
activity_tab = ttk.Frame(tab_control)
tab_control.add(activity_tab, text="سجل النشاط")

activity_label = tk.Label(activity_tab, text="سجل النشاط", font=("Arial", 14))
activity_label.pack()

filter_frame = tk.Frame(activity_tab)
filter_frame.pack(pady=5)

device_label = tk.Label(filter_frame, text="الجهاز:")
device_label.grid(row=0, column=0, padx=5)
device_dropdown = ttk.Combobox(filter_frame, state="readonly", width=20)
device_dropdown.grid(row=0, column=1, padx=5)

start_date_label = tk.Label(filter_frame, text="تاريخ البداية:")
start_date_label.grid(row=0, column=2, padx=5)
start_date_entry = DateEntry(filter_frame, width=15, background="darkblue", foreground="white", borderwidth=2)
start_date_entry.grid(row=0, column=3, padx=5)

start_time_label = tk.Label(filter_frame, text="وقت البداية (ساعة:دقيقة):")
start_time_label.grid(row=1, column=2, padx=5)
start_hour_entry = ttk.Combobox(filter_frame, width=5, values=[f"{i:02}" for i in range(24)])
start_hour_entry.grid(row=1, column=3, padx=5)
start_hour_entry.set("00")
start_minute_entry = ttk.Combobox(filter_frame, width=5, values=[f"{i:02}" for i in range(60)])
start_minute_entry.grid(row=1, column=4, padx=5)
start_minute_entry.set("00")

end_date_label = tk.Label(filter_frame, text="تاريخ النهاية:")
end_date_label.grid(row=0, column=4, padx=5)
end_date_entry = DateEntry(filter_frame, width=15, background="darkblue", foreground="white", borderwidth=2)
end_date_entry.grid(row=0, column=5, padx=5)

end_time_label = tk.Label(filter_frame, text="وقت النهاية (ساعة:دقيقة):")
end_time_label.grid(row=1, column=4, padx=5)
end_hour_entry = ttk.Combobox(filter_frame, width=5, values=[f"{i:02}" for i in range(24)])
end_hour_entry.grid(row=1, column=5, padx=5)
end_hour_entry.set("23")
end_minute_entry = ttk.Combobox(filter_frame, width=5, values=[f"{i:02}" for i in range(60)])
end_minute_entry.grid(row=1, column=6, padx=5)
end_minute_entry.set("59")

filter_button = tk.Button(filter_frame, text="تطبيق الفلتر", command=show_activity_report)
filter_button.grid(row=2, column=0, columnspan=2, pady=10)

summary_button = tk.Button(filter_frame, text="عرض الملخص", command=show_summary)
summary_button.grid(row=2, column=2, pady=10)

refresh_button = tk.Button(filter_frame, text="تحديث", command=refresh_activity_log)
refresh_button.grid(row=2, column=3, pady=10)

clear_db_button = tk.Button(filter_frame, text="مسح قاعدة البيانات", command=clear_database)
clear_db_button.grid(row=2, column=4, pady=10)

summary_label = tk.Label(activity_tab, text="", font=("Arial", 12))
summary_label.pack(pady=5)

activity_table = ttk.Treeview(activity_tab, columns=("ID", "الجهاز", "الحدث", "الوقت"), show="headings")
activity_table.heading("ID", text="ID")
activity_table.heading("الجهاز", text="الجهاز")
activity_table.heading("الحدث", text="الحدث")
activity_table.heading("الوقت", text="الوقت")
activity_table.pack(fill="both", expand=True)

activity_table.tag_configure('evenrow', background='#E8E8E8')
activity_table.tag_configure('startrow', background='#FFD700')
activity_table.tag_configure('idlerow', background='#ADD8E6')
activity_table.tag_configure('programrow', background='#98FB98')
activity_table.tag_configure('resumerow', background='#DDA0DD')

tab_control.pack(expand=1, fill="both")

setup_database()
update_device_list()

threading.Thread(target=monitor_activity, daemon=True).start()

app.mainloop()