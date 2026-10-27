"""Lifecycle of a temporary BlueZ advertisement, independent of HID/GATT.

The normal advertisement remains registered. No raw HCI commands or Android
profile-connect calls are needed to recover from an early connection timeout.
"""


class WakeSession:
    def __init__(self, manager, advertisement, schedule, cancel, report, seconds=8):
        self.manager = manager
        self.advertisement = advertisement
        self.schedule = schedule
        self.cancel = cancel
        self.report = report
        self.seconds = seconds
        self.phase = 'idle'
        self.registered = False
        self.timer = None
        self.closed = False

    def start(self):
        if self.closed or self.phase != 'idle':
            return False
        self.phase = 'registering'
        try:
            self.manager.RegisterAdvertisement(self.advertisement.path, {},
                                              reply_handler=self._ready,
                                              error_handler=self._failed)
        except Exception as error:
            self._failed(error)
        return True

    def _ready(self):
        self.registered = True
        if self.closed:
            self._remove()
            return
        self.phase = 'advertising'
        self.report('Reklama wybudzania BlueZ aktywna; HID pozostaje dostępny.')
        self.timer = self.schedule(self.seconds, self._finish)

    def _failed(self, error):
        self.phase = 'closed' if self.closed else 'idle'
        self.report('Nie udało się uruchomić reklamy wybudzania: ' + str(error))

    def _remove(self):
        if self.registered:
            try:
                self.manager.UnregisterAdvertisement(self.advertisement.path)
            except Exception as error:
                self.report('Błąd usuwania reklamy wybudzania: ' + str(error))
                self.phase = 'error'
                return False
            self.registered = False
        self.phase = 'closed' if self.closed else 'idle'
        return True

    def _finish(self):
        self.timer = None
        if self._remove():
            self.report('Reklama wybudzania zakończona; zwykła reklama i GATT nadal działają.')
        return False

    def released(self):
        self.registered = False
        if self.timer is not None:
            self.cancel(self.timer)
            self.timer = None
        self.phase = 'closed' if self.closed else 'idle'

    def close(self):
        self.closed = True
        if self.timer is not None:
            self.cancel(self.timer)
            self.timer = None
        if self.phase != 'registering':
            self._remove()
