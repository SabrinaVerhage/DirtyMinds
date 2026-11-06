"""Simple four-pump bench test using Dirty Minds' existing serial client."""
import queue
import sys
import threading
from pathlib import Path
import tkinter as tk
from tkinter import ttk

PROJECT = Path(__file__).resolve().parent
sys.path.insert(0, str(PROJECT))
from dirtyminds.pumps import PumpClient, PumpCancelled, PumpError
from serial import Serial
from serial.tools import list_ports

root = tk.Tk()
root.title('Dirty Minds - pump test')
root.resizable(False, False)
events = queue.Queue()
cancel = threading.Event()
port = tk.StringVar()
status = tk.StringVar(value='Select the Uno port. Pumps run for 3 seconds.')
busy = False
closing = False

frame = ttk.Frame(root, padding=18)
frame.grid(sticky='nsew')
ttk.Label(frame, text='Uno pump test', font=('Segoe UI', 16, 'bold')).grid(row=0, column=0, columnspan=4, sticky='w')
ttk.Label(frame, text='Each button runs one pump for 3 seconds. Use water and keep\nthe motor power switch within reach.').grid(row=1, column=0, columnspan=4, sticky='w', pady=(8, 10))
ttk.Label(frame, text='Uno USB port:').grid(row=2, column=0, sticky='w')
ports = ttk.Combobox(frame, textvariable=port, state='readonly', width=20)
ports.grid(row=2, column=1, columnspan=2, sticky='ew')
def refresh():
    values = [p.device for p in list_ports.comports()]
    ports['values'] = values
    if port.get() not in values:
        port.set(values[0] if len(values) == 1 else '')
refresh_button = ttk.Button(frame, text='Refresh', command=refresh)
refresh_button.grid(row=2, column=3, padx=(8, 0))
buttons = []

def worker(selected_port, durations):
    try:
        with Serial(selected_port, baudrate=115200, timeout=.05, write_timeout=.5) as connection:
            client = PumpClient(connection)
            client.hello(cancelled=cancel)
            client.run(durations, cancelled=cancel, report=lambda line: events.put(('report', line)))
        events.put(('done', 'Finished. Pumps are off.'))
    except PumpCancelled:
        events.put(('done', 'Stop requested. Check that the pump is off.'))
    except Exception as exc:
        events.put(('done', f'Could not complete: {exc}. Check the pump is off.'))

def start(durations):
    global busy
    if busy:
        return
    if not port.get():
        status.set('Choose the Uno USB port first.')
        return
    busy = True
    cancel.clear()
    for button in buttons:
        button.configure(state='disabled')
    ports.configure(state='disabled')
    refresh_button.configure(state='disabled')
    status.set('Connecting to the Uno...')
    threading.Thread(target=worker, args=(port.get(), durations), daemon=True).start()

for i in range(4):
    durations = [0] * 4
    durations[i] = 3000
    button = ttk.Button(frame, text=f'Pump {i+1}', command=lambda d=durations: start(d))
    button.grid(row=3, column=i, padx=3, pady=(14, 4), sticky='ew')
    buttons.append(button)
all_button = ttk.Button(frame, text='Test all in order', command=lambda: start([3000] * 4))
all_button.grid(row=4, column=0, columnspan=2, padx=3, pady=4, sticky='ew')
buttons.append(all_button)
def stop():
    cancel.set()
    if busy:
        status.set('Stop requested. Check that the pump is off.')
ttk.Button(frame, text='STOP', command=stop).grid(row=4, column=2, columnspan=2, padx=3, pady=4, sticky='ew')
ttk.Label(frame, textvariable=status, wraplength=420).grid(row=5, column=0, columnspan=4, sticky='w', pady=(12, 0))

def poll():
    global busy
    try:
        while True:
            kind, msg = events.get_nowait()
            if kind == 'report' and msg.startswith('START pump='):
                status.set('Running pump ' + msg.split('pump=')[1].split()[0] + '...')
            elif kind == 'done':
                busy = False
                status.set(msg)
                for button in buttons:
                    button.configure(state='normal')
                ports.configure(state='readonly')
                refresh_button.configure(state='normal')
    except queue.Empty:
        pass
    if closing and not busy:
        root.destroy()
    else:
        root.after(50, poll)
def close():
    global closing
    closing = True
    stop()
root.protocol('WM_DELETE_WINDOW', close)
refresh()
poll()
root.mainloop()
