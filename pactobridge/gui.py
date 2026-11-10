"""Qt widgets on main thread; BLE runs in one asyncio worker loop."""
import asyncio
import json
from pathlib import Path
import threading
import time
from PySide6.QtCore import QThread, QTimer, Signal
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (QApplication, QCheckBox, QComboBox, QFileDialog, QHBoxLayout,
                              QLabel, QMainWindow, QPlainTextEdit, QPushButton,
                              QVBoxLayout, QWidget)
from .app import capture
from .ble import discover
from .cli import capture_path, replay_capture
from .safety import LIVE_CONNECTION_BLOCK_REASON


class Worker(QThread):
    event = Signal(dict)

    def __init__(self, operation, parent=None):
        super().__init__(parent)
        self.operation = operation
        self.loop = None
        self.task = None
        self.stopping = threading.Event()

    def stop(self):
        self.stopping.set()
        if self.loop and self.task:
            try:
                self.loop.call_soon_threadsafe(self.task.cancel)
            except RuntimeError:
                pass

    def run(self):
        async def run_job():
            self.loop = asyncio.get_running_loop()
            self.task = asyncio.current_task()
            if not self.stopping.is_set():
                await self.operation(self.event.emit)
        try:
            asyncio.run(run_job())
        except asyncio.CancelledError:
            pass
        except Exception as exc:
            self.event.emit({"kind": "error", "message": f"{type(exc).__name__}: {exc}"})
        finally:
            self.loop = None
            self.task = None


class Window(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setFont(QFont("Segoe UI", 10))
        self.setWindowTitle("PactoBridge — ZIPRO Pacto")
        self.resize(850, 580)
        self.setStyleSheet("QWidget { font-size: 14px; } QPushButton { padding: 9px; } "
                           "QComboBox { padding: 6px; } QLabel { padding: 3px; }")
        self.worker = None
        self.closing = False
        root = QWidget()
        self.setCentralWidget(root)
        layout = QVBoxLayout(root)
        self.status = QLabel("Gotowe do odtwarzania nagrań. Połączenia live są zablokowane.")
        layout.addWidget(self.status)
        self.speed = QLabel("Brak bieżącej prędkości")
        self.speed.setStyleSheet("font-size: 38px; font-weight: bold; color: #11998e;")
        self.last_speed = None
        self.freshness_timer = QTimer(self)
        self.freshness_timer.timeout.connect(self.check_freshness)
        self.freshness_timer.start(250)
        layout.addWidget(self.speed)
        self.devices = QComboBox()
        self.devices.addItem("Automatycznie wybierz iConsole+0106", None)
        layout.addWidget(self.devices)
        self.mode = QComboBox()
        self.mode.addItems(["Nasłuch BLE (zablokowany)", "Odczyt Pacto (zablokowany)"])
        self.mode.setEnabled(False)
        layout.addWidget(self.mode)
        self.advertise = QCheckBox("Udostępnij prędkość w Zwift (zablokowane)")
        self.advertise.setEnabled(False)
        layout.addWidget(self.advertise)
        buttons = QHBoxLayout()
        self.scan = QPushButton("Szukaj urządzeń")
        self.connect = QPushButton("Połącz i nagrywaj")
        self.connect.setEnabled(False)
        self.connect.setToolTip(LIVE_CONNECTION_BLOCK_REASON)
        self.stop = QPushButton("Zatrzymaj odtwarzanie / skan")
        self.open = QPushButton("Otwórz nagranie")
        self.demo = QPushButton("Odtwórz ostatni trening Pacto")
        self.stop.setEnabled(False)
        for button in (self.scan, self.connect, self.stop, self.open):
            buttons.addWidget(button)
        layout.addLayout(buttons)
        layout.addWidget(self.demo)
        self.replay_rate = QComboBox()
        self.replay_rate.addItem("Odtwarzanie ×10", 10.0)
        self.replay_rate.addItem("Czas rzeczywisty", 1.0)
        self.replay_rate.addItem("Analiza natychmiastowa", 0.0)
        layout.addWidget(self.replay_rate)
        self.decoder = QComboBox()
        self.decoder.addItems(["raw", "pacto", "fitshow-v1-candidate"])
        self.decoder.setCurrentText("pacto")
        layout.addWidget(QLabel("Dekoder nagrania (offline):"))
        layout.addWidget(self.decoder)
        warning = QLabel("Tryb offline: odtwarza dane zapisane przez iConsole+. Nie steruje bieżnią "
                         "i nie nadaje do Zwift. Połączenie live wymaga jeszcze weryfikacji "
                         "pełnej sesji i działania fizycznych przycisków w PactoBridge.")
        warning.setWordWrap(True)
        layout.addWidget(warning)
        self.output = QPlainTextEdit()
        self.output.setReadOnly(True)
        self.output.setMaximumBlockCount(1500)
        layout.addWidget(self.output)
        self.scan.clicked.connect(self.start_scan)
        self.connect.clicked.connect(self.start_capture)
        self.open.clicked.connect(self.start_replay)
        self.demo.clicked.connect(self.start_demo)
        self.stop.clicked.connect(self.stop_worker)

    def start_job(self, job):
        self.worker = Worker(job, self)
        self.worker.event.connect(self.receive)
        self.worker.finished.connect(self.finished)
        for button in (self.scan, self.connect, self.open, self.demo):
            button.setEnabled(False)
        self.devices.setEnabled(False)
        self.decoder.setEnabled(False)
        self.replay_rate.setEnabled(False)
        self.mode.setEnabled(False)
        self.advertise.setEnabled(False)
        self.last_speed = None
        self.check_freshness()
        self.stop.setEnabled(True)
        self.worker.start()

    def stop_worker(self):
        if self.worker:
            self.status.setText("Zatrzymywanie zadania…")
            self.stop.setEnabled(False)
            self.worker.stop()

    def finished(self):
        self.worker.deleteLater()
        self.worker = None
        self.stop.setEnabled(False)
        self.devices.setEnabled(True)
        self.decoder.setEnabled(True)
        self.replay_rate.setEnabled(True)
        self.mode.setEnabled(False)
        self.advertise.setEnabled(False)
        self.last_speed = None
        self.check_freshness()
        for button in (self.scan, self.open, self.demo):
            button.setEnabled(True)
        self.connect.setEnabled(False)
        if not self.status.text().startswith("Error:"):
            self.status.setText("Zadanie zakończone. Nagranie offline nie steruje bieżnią.")
        if self.closing:
            self.close()

    def start_scan(self):
        async def job(emit):
            emit({"kind": "status", "state": "scanning"})
            rows = await discover()
            emit({"kind": "devices", "items": [
                {"name": adv.local_name or d.name or "(unnamed)", "address": d.address,
                 "rssi": adv.rssi} for d, adv in rows]})
        self.start_job(job)

    def start_capture(self):
        path = capture_path()
        address = self.devices.currentData()
        self.output.appendPlainText(f"Saving raw capture: {path.resolve()}")
        active = self.mode.currentIndex() == 1
        advertise = active and self.advertise.isChecked()
        self.start_job(lambda emit: capture(path, emit, address=address,
                                           polling="pacto-status" if active else None,
                                           decoder_name="pacto" if active else "raw",
                                           advertise=advertise))

    def start_replay(self):
        path, _ = QFileDialog.getOpenFileName(self, "Open capture", "captures", "Captures (*.jsonl)")
        if path:
            decoder = self.decoder.currentText()
            rate = self.replay_rate.currentData()
            self.start_job(lambda emit: replay_capture(Path(path), emit, decoder, rate))

    def start_demo(self):
        project = Path(__file__).resolve().parent.parent
        paths = sorted((project / "captures" / "android").glob("controls-*/pacto-workout.jsonl"))
        if not paths:
            self.status.setText("Brak nagrania treningu. Wybierz plik przez Otwórz nagranie.")
            return
        path = paths[-1]
        self.output.clear()
        self.output.appendPlainText(f"Nagranie offline: {path}")
        rate = self.replay_rate.currentData()
        self.start_job(lambda emit: replay_capture(path, emit, "pacto", rate))

    def receive(self, row):
        if row["kind"] == "devices":
            self.devices.clear()
            self.devices.addItem("Automatycznie wybierz iConsole+0106", None)
            for item in row["items"]:
                self.devices.addItem(f'{item["name"]} | {item["address"]} | {item["rssi"]} dBm', item["address"])
        elif row["kind"] == "status":
            self.status.setText(row.get("message", row["state"]))
        elif row["kind"] == "error":
            self.status.setText("Error: " + row["message"])
        elif row["kind"] == "speed" and row.get("verified"):
            self.last_speed = time.monotonic()
            prefix = "Nagranie" if row.get("source") == "offline replay" else "Prędkość bieżni"
            self.speed.setText(f'{prefix}: {row["kmh"]:.1f} km/h')
        elif row["kind"] == "speed_unavailable":
            self.last_speed = None
            self.check_freshness()
        self.output.appendPlainText(json.dumps(row))

    def check_freshness(self):
        if self.last_speed is None or time.monotonic() - self.last_speed >= 3:
            self.speed.setText("Brak bieżącej prędkości")

    def closeEvent(self, event):
        if self.worker and self.worker.isRunning():
            self.closing = True
            self.stop_worker()
            event.ignore()
        else:
            event.accept()


def launch():
    app = QApplication([])
    window = Window()
    window.show()
    app.exec()
